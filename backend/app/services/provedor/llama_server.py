"""Cliente llama-server (llama.cpp), direto ou atrás do llama-swap.

Alternativa ao `ClienteOllama` para as medições: o
servidor devolve `timings` (tokens/s de prefill e de geração) e o ambiente fica
fixado em flags de linha de comando, não em defaults do Ollama. Não conhece a
linha `ProvedorLLM`: recebe `base_url` e `modelo` já resolvidos.

O contexto (`-c`) e as camadas na GPU (`-ngl`) são do processo do servidor, não
da requisição — por isso `cfg.num_ctx` não vai no corpo. O llama-swap escolhe
qual processo atende pelo campo `model`.
"""

from __future__ import annotations

import logging

import httpx
from pydantic import ValidationError

from backend.app.exceptions import (
    FalhaTransporteLLMException,
    RespostaLLMInvalidaException,
)
from backend.app.services.provedor.ollama import cliente_http
from backend.app.services.provedor.tipos import (
    ConfigLLM,
    RequisicaoLLM,
    RespostaLLM,
    UsoTokens,
)

# Logger próprio: as medições se filtram por nome sem pegar o resto da API.
_metricas = logging.getLogger("docencia.llm.metricas")


class ClienteLlamaServer:
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
        teto = (
            requisicao.max_tokens
            if requisicao.max_tokens is not None
            else self.cfg.max_tokens_padrao
        )
        corpo = {
            "model": self.modelo,
            "messages": [
                {"role": "system", "content": requisicao.sistema},
                {"role": "user", "content": requisicao.usuario},
            ],
            # Decodificação restrita por gramática gerada do schema.
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": requisicao.formato.__name__,
                    "schema": requisicao.formato.model_json_schema(),
                },
            },
            "stream": False,
            # Equivale ao think:false do Ollama: raciocínio não agrega em saída
            # estruturada e conta contra o teto de tokens.
            "chat_template_kwargs": {"enable_thinking": False},
            "temperature": (
                requisicao.temperatura
                if requisicao.temperatura is not None
                else self.cfg.temperatura_padrao
            ),
            "max_tokens": teto,
        }

        try:
            resposta = self._cliente.post("/v1/chat/completions", json=corpo)
        except httpx.HTTPError as exc:
            raise FalhaTransporteLLMException(type(exc).__name__) from exc

        if resposta.status_code >= 400:
            raise FalhaTransporteLLMException(f"HTTP {resposta.status_code}")

        dados = resposta.json()
        escolhas = dados.get("choices") or []
        escolha = escolhas[0] if escolhas else {}

        if escolha.get("finish_reason") == "length":
            raise RespostaLLMInvalidaException(
                f"resposta cortada pelo limite de {teto} "
                "tokens de saída — aumente o teto da chamada (GERACAO_MAX_TOKENS, "
                "CRITICO_MAX_TOKENS ou AUDITORIA_MAX_TOKENS) ou reduza o prompt"
            )

        conteudo_bruto = (escolha.get("message") or {}).get("content")
        if not isinstance(conteudo_bruto, str):
            raise RespostaLLMInvalidaException("resposta sem message.content")

        try:
            conteudo = requisicao.formato.model_validate_json(conteudo_bruto)
        except ValidationError as exc:
            erros = exc.errors()
            if erros and erros[0]["type"] == "json_invalid":
                raise RespostaLLMInvalidaException("conteúdo não é JSON") from exc
            raise RespostaLLMInvalidaException(
                f"{exc.error_count()} campo(s) fora do schema"
            ) from exc

        uso = dados.get("usage") or {}
        timings = dados.get("timings")
        if timings:
            _metricas.info(
                "timings do llama-server",
                extra={"modelo": self.modelo, "timings": timings},
            )

        return RespostaLLM(
            conteudo=conteudo,
            uso=UsoTokens(
                entrada=int(uso.get("prompt_tokens") or 0),
                saida=int(uso.get("completion_tokens") or 0),
            ),
            provedor_id=self.provedor_id,
            modelo=self.modelo,
        )
