"""O Protocol que isola o motor de inferência do resto do sistema."""

from typing import Protocol

from backend.app.services.provedor.tipos import RequisicaoLLM, RespostaLLM


class ClienteLLM(Protocol):
    def gerar(self, requisicao: RequisicaoLLM) -> RespostaLLM: ...
