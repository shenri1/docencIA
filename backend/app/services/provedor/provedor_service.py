"""Cadeia de provedores, retentativa e fallback.

Não conhece HTTP: fala com `ClienteLLM`. A fábrica de cliente é injetada, e é
isso que permite testar cadeia inteira com clientes que falham sob comando.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import settings
from backend.app.domain import TipoEventoAuditoria
from backend.app.exceptions import (
    FalhaProvedorLLMException,
    FalhaTransporteLLMException,
    NenhumProvedorAtivoException,
)
from backend.app.models.identidade import SessaoGeracao
from backend.app.models.prompt_provedor import ProvedorLLM
from backend.app.services.log_auditoria import registrar_evento
from backend.app.services.provedor.consumo import (
    RegistradorConsumo,
    RegistradorConsumoDb,
)
from backend.app.services.provedor.contrato import ClienteLLM
from backend.app.services.provedor.llama_server import ClienteLlamaServer
from backend.app.services.provedor.ollama import ClienteOllama
from backend.app.services.provedor.tipos import ConfigLLM, RequisicaoLLM, RespostaLLM

_BACKOFF_BASE_S = 0.5

FabricaCliente = Callable[[ProvedorLLM], ClienteLLM]


def criar_cliente(provedor: ProvedorLLM) -> ClienteLLM:
    cfg = ConfigLLM.das_settings()
    classe = (
        ClienteLlamaServer if settings.llm_protocolo == "llama-server" else ClienteOllama
    )
    return classe(
        provedor_id=provedor.id,
        modelo=provedor.modelo,
        # endpoint NULL significa "usar a configuração do ambiente", o que
        # deixa a mesma linha de banco correta em local e no Compose.
        base_url=provedor.endpoint or cfg.base_url,
        cfg=cfg,
    )


def _falhas(motivos: list[tuple[str, str]]) -> list[dict[str, str]]:
    """Provedor por nome, nunca por endpoint nem por referência de chave
O motivo é o `mensagem` do transporte: nome da exceção ou
    `HTTP <status>`."""
    return [{"provedor": nome, "motivo": motivo} for nome, motivo in motivos]


class ProvedorLLMService:
    def __init__(
        self,
        db: Session,
        registrador: RegistradorConsumo,
        fabrica: FabricaCliente,
        tentativas: int | None = None,
    ) -> None:
        self._db = db
        self._registrador = registrador
        self._fabrica = fabrica
        self._tentativas = (
            tentativas
            if tentativas is not None
            else settings.llm_tentativas_por_provedor
        )

    def gerar(self, sessao_id: int, requisicao: RequisicaoLLM) -> RespostaLLM:
        cadeia = list(
            self._db.scalars(
                select(ProvedorLLM)
                .where(ProvedorLLM.ativo.is_(True))
                .order_by(ProvedorLLM.prioridade, ProvedorLLM.id)
            )
        )
        if not cadeia:
            raise NenhumProvedorAtivoException()

        motivos: list[tuple[str, str]] = []
        for provedor in cadeia:
            cliente = self._fabrica(provedor)
            ultimo = "nenhuma tentativa executada"
            for tentativa in range(self._tentativas):
                try:
                    resposta = cliente.gerar(requisicao)
                except FalhaTransporteLLMException as exc:
                    ultimo = exc.mensagem
                    if tentativa < self._tentativas - 1:
                        time.sleep(_BACKOFF_BASE_S * 2**tentativa)
                    continue
                # RespostaLLMInvalidaException sobe daqui sem ser capturada:
                # resposta que chega e viola o schema não é indisponibilidade,
                # e escalar a cadeia mascararia defeito do prompt mestre.
                if motivos:
                    # Um provedor anterior se esgotou: é a "troca de provedor"
                    # Entra no commit do registrador de consumo.
                    self._registrar_evento(
                        sessao_id,
                        TipoEventoAuditoria.FALLBACK_PROVEDOR,
                        {"provedor_usado": provedor.nome, "falhas": _falhas(motivos)},
                    )
                self._registrador.registrar(sessao_id, provedor, resposta.uso)
                return resposta
            motivos.append((provedor.nome, ultimo))

        self._registrar_evento(
            sessao_id, TipoEventoAuditoria.FALHA_PROVEDOR, {"falhas": _falhas(motivos)}
        )
        # Commit antes do raise: o rollback do erro apagaria o registro da falha.
        self._db.commit()
        raise FalhaProvedorLLMException(motivos)

    def _registrar_evento(
        self, sessao_id: int, tipo: TipoEventoAuditoria, payload: dict
    ) -> None:
        # Estamos, tipicamente, no caminho de erro: a falha real do provedor
        # não pode ser trocada por AttributeError se a sessão sumiu.
        sessao = self._db.get(SessaoGeracao, sessao_id)
        docente_id = sessao.docente_id if sessao is not None else None
        registrar_evento(
            self._db, tipo, f"sessoes_geracao:{sessao_id}", docente_id, payload
        )


def criar_provedor_service(db: Session) -> ProvedorLLMService:
    """Fábrica de produção. Não é dependência FastAPI de propósito: manter
    `fastapi` fora de `services/` preserva a camada testável sem app."""
    return ProvedorLLMService(
        db=db,
        registrador=RegistradorConsumoDb(db),
        fabrica=criar_cliente,
    )
