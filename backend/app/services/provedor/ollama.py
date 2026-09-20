"""Cliente Ollama — a única implementação de `ClienteLLM` nesta etapa.

Não conhece a linha `ProvedorLLM`: recebe `base_url` e `modelo` já
resolvidos. É isso que o mantém testável com `httpx.MockTransport`, sem
sessão de banco.
"""

from __future__ import annotations

import atexit

import httpx
from pydantic import ValidationError

from backend.app.exceptions import (
    FalhaTransporteLLMException,
    RespostaLLMInvalidaException,
)
from backend.app.services.provedor.tipos import (
    ConfigLLM,
    RequisicaoLLM,
    RespostaLLM,
    UsoTokens,
)

# Um cliente por (URL, timeout), reusado entre chamadas. Criar um httpx.Client
# por requisição vaza pool de conexões e descritores de arquivo. O timeout faz
# parte da chave: dois provedores na mesma URL com timeouts diferentes não
# podem compartilhar cliente — o segundo herdaria o timeout do primeiro.
_clientes: dict[tuple[str, float], httpx.Client] = {}


def _fechar_clientes() -> None:
    for cliente in _clientes.values():
        cliente.close()
    _clientes.clear()


# Em processo de vida longa o pool fica aberto de propósito; no desligamento
# (e no fim dos testes) fecha os clientes para não vazar fds nem soltar
# ResourceWarning.
atexit.register(_fechar_clientes)


def cliente_http(base_url: str, timeout_s: float) -> httpx.Client:
    chave = (base_url, timeout_s)
    if chave not in _clientes:
        _clientes[chave] = httpx.Client(base_url=base_url, timeout=timeout_s)
    return _clientes[chave]


class ClienteOllama:
    def __init__(
        self,
        provedor_id: int,
        modelo: str,
        base_url: str,
        cfg: ConfigLLM,
        cliente: httpx.Client | None = None,
    ) -> None:
        self.provedor_id = provedor_id
        self.modelo = modelo
        self.cfg = cfg
        self._cliente = cliente or cliente_http(base_url, cfg.timeout_s)

    def gerar(self, requisicao: RequisicaoLLM) -> RespostaLLM:
        corpo = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": requisicao.sistema},
                {"role": "user", "content": requisicao.usuario},
            ],
            # Decodificação restrita: o modelo só consegue emitir JSON que
            # casa com o schema.
            "format": requisicao.formato.model_json_schema(),
            "stream": False,
            # qwen3 é raciocínio híbrido e pensa por padrão: gera ~6× mais
            # tokens de "thinking" que são descartados E contam contra
            # num_predict. Para saída estruturada (JSON com schema) o
            # raciocínio não agrega — desligado de propósito, não herdado do
            # default. Medido: default 1077 eval_count vs think:false 174.
            "think": False,
            "options": {
                # Sempre explícito: o default do Ollama é 4096 e ele trunca o
                # prompt em silêncio para caber.
                "num_ctx": self.cfg.num_ctx,
                "temperature": (
                    requisicao.temperatura
                    if requisicao.temperatura is not None
                    else self.cfg.temperatura_padrao
                ),
                "num_predict": (
                    requisicao.max_tokens
                    if requisicao.max_tokens is not None
                    else self.cfg.max_tokens_padrao
                ),
            },
        }

        try:
            resposta = self._cliente.post("/api/chat", json=corpo)
        except httpx.HTTPError as exc:
            raise FalhaTransporteLLMException(type(exc).__name__) from exc

        # Qualquer não-2xx é indisponibilidade deste provedor — inclusive 404,
        # que significa modelo não instalado aqui e que outro pode ter.
        if resposta.status_code >= 400:
            raise FalhaTransporteLLMException(f"HTTP {resposta.status_code}")

        dados = resposta.json()
        if dados.get("done_reason") == "length":
            raise RespostaLLMInvalidaException(
                "resposta cortada pelo limite de tokens de saída — "
                "aumente LLM_MAX_TOKENS_PADRAO ou reduza o prompt"
            )

        conteudo_bruto = (dados.get("message") or {}).get("content")
        if not isinstance(conteudo_bruto, str):
            raise RespostaLLMInvalidaException("resposta sem message.content")

        try:
            conteudo = requisicao.formato.model_validate_json(conteudo_bruto)
        except ValidationError as exc:
            # Pydantic v2 reporta JSON malformado como ValidationError (não
            # ValueError): discriminar pelo tipo do primeiro erro para dar o
            # diagnóstico certo em vez de "N campo(s) fora do schema".
            erros = exc.errors()
            if erros and erros[0]["type"] == "json_invalid":
                raise RespostaLLMInvalidaException("conteúdo não é JSON") from exc
            raise RespostaLLMInvalidaException(
                f"{exc.error_count()} campo(s) fora do schema"
            ) from exc

        return RespostaLLM(
            conteudo=conteudo,
            uso=UsoTokens(
                # Campo ausente vira zero: perder a geração por causa de
                # contagem seria pior que registrar consumo incompleto.
                entrada=int(dados.get("prompt_eval_count") or 0),
                saida=int(dados.get("eval_count") or 0),
            ),
            provedor_id=self.provedor_id,
            modelo=self.modelo,
        )
