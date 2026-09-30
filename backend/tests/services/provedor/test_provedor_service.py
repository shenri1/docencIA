from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from backend.app.domain import TipoProvedorLLM
from backend.app.exceptions import (
    FalhaProvedorLLMException,
    FalhaTransporteLLMException,
    NenhumProvedorAtivoException,
    RespostaLLMInvalidaException,
)
from backend.app.models.prompt_provedor import ProvedorLLM
from backend.app.services.provedor import provedor_service as mod
from backend.app.services.provedor.consumo import RegistradorConsumoFake
from backend.app.services.provedor.provedor_service import ProvedorLLMService
from backend.app.services.provedor.tipos import RequisicaoLLM, RespostaLLM, UsoTokens


class Saida(BaseModel):
    texto: str


def provedor(id_: int, nome: str, prioridade: int) -> ProvedorLLM:
    return ProvedorLLM(
        id=id_,
        nome=nome,
        modelo=f"modelo-{id_}",
        tipo=TipoProvedorLLM.LOCAL,
        endpoint=None,
        preco_input_por_milhao=Decimal(0),
        preco_output_por_milhao=Decimal(0),
        janela_contexto=8192,
        ativo=True,
        referencia_chave_secrets=None,
        prioridade=prioridade,
    )


class DbFalso:
    """Substitui a Session só no que o service usa: `scalars(...)` para a
    cadeia, e `get`/`add`/`commit` para os eventos do log."""

    def __init__(self, provedores: list[ProvedorLLM]) -> None:
        self._provedores = provedores
        self.adicionados: list = []
        self.commits = 0

    def scalars(self, _consulta):
        return iter(
            sorted(
                (p for p in self._provedores if p.ativo),
                key=lambda p: (p.prioridade, p.id),
            )
        )

    def get(self, _modelo, _id):
        return SimpleNamespace(docente_id=7)

    def add(self, objeto) -> None:
        self.adicionados.append(objeto)

    def commit(self) -> None:
        self.commits += 1


class ClienteRoteirizado:
    """Executa um roteiro de resultados: exceções são levantadas, valores são
    devolvidos. Um roteiro por provedor."""

    def __init__(self, provedor_alvo: ProvedorLLM, roteiro: list) -> None:
        self.provedor = provedor_alvo
        self.roteiro = list(roteiro)
        self.chamadas = 0

    def gerar(self, _requisicao):
        self.chamadas += 1
        resultado = self.roteiro.pop(0)
        if isinstance(resultado, Exception):
            raise resultado
        return resultado


def resposta_de(p: ProvedorLLM) -> RespostaLLM:
    return RespostaLLM(
        conteudo=Saida(texto="ok"),
        uso=UsoTokens(entrada=100, saida=50),
        provedor_id=p.id,
        modelo=p.modelo,
    )


def montar(provedores, roteiros, registrador=None, tentativas=2, db=None):
    clientes = {
        p.id: ClienteRoteirizado(p, roteiros[p.id])
        for p in provedores
        if p.id in roteiros
    }
    servico = ProvedorLLMService(
        db=db or DbFalso(provedores),
        registrador=registrador or RegistradorConsumoFake(),
        fabrica=lambda p: clientes[p.id],
        tentativas=tentativas,
    )
    return servico, clientes


def requisicao() -> RequisicaoLLM:
    return RequisicaoLLM(sistema="s", usuario="u", formato=Saida)


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(mod, "_BACKOFF_BASE_S", 0.0)


def test_primario_saudavel_responde_e_registra_uma_vez():
    p1 = provedor(1, "primario", 1)
    registrador = RegistradorConsumoFake()
    servico, clientes = montar([p1], {1: [resposta_de(p1)]}, registrador)

    resposta = servico.gerar(sessao_id=9, requisicao=requisicao())

    assert resposta.provedor_id == 1
    assert clientes[1].chamadas == 1
    assert registrador.registros == [(9, 1, UsoTokens(entrada=100, saida=50))]


def test_falha_transitoria_retenta_no_mesmo_provedor_sem_cair_para_o_fallback():
    p1, p2 = provedor(1, "primario", 1), provedor(2, "fallback", 2)
    servico, clientes = montar(
        [p1, p2],
        {
            1: [FalhaTransporteLLMException("timeout"), resposta_de(p1)],
            2: [resposta_de(p2)],
        },
    )

    resposta = servico.gerar(sessao_id=9, requisicao=requisicao())

    assert resposta.provedor_id == 1
    assert clientes[1].chamadas == 2
    assert clientes[2].chamadas == 0


def test_primario_esgotado_cai_para_o_fallback_e_registra_o_fallback():
    p1, p2 = provedor(1, "primario", 1), provedor(2, "fallback", 2)
    registrador = RegistradorConsumoFake()
    servico, clientes = montar(
        [p1, p2],
        {
            1: [FalhaTransporteLLMException("HTTP 500")] * 2,
            2: [resposta_de(p2)],
        },
        registrador,
    )

    resposta = servico.gerar(sessao_id=9, requisicao=requisicao())

    assert resposta.provedor_id == 2
    assert clientes[1].chamadas == 2
    # O consumo aponta para quem de fato serviu, não para o primeiro da cadeia.
    assert registrador.registros == [(9, 2, UsoTokens(entrada=100, saida=50))]


def test_cadeia_inteira_falha_traz_o_motivo_de_cada_provedor():
    p1, p2 = provedor(1, "primario", 1), provedor(2, "fallback", 2)
    registrador = RegistradorConsumoFake()
    servico, _ = montar(
        [p1, p2],
        {
            1: [FalhaTransporteLLMException("HTTP 500")] * 2,
            2: [FalhaTransporteLLMException("ConnectError")] * 2,
        },
        registrador,
    )

    with pytest.raises(FalhaProvedorLLMException) as capturado:
        servico.gerar(sessao_id=9, requisicao=requisicao())

    provedores = capturado.value.corpo()["provedores"]
    assert [p["provedor"] for p in provedores] == ["primario", "fallback"]
    assert "HTTP 500" in provedores[0]["motivo"]
    assert registrador.registros == []


def test_resposta_invalida_nao_escala_a_cadeia_nem_registra_consumo():
    """Trocar de modelo não conserta prompt ruim."""
    p1, p2 = provedor(1, "primario", 1), provedor(2, "fallback", 2)
    registrador = RegistradorConsumoFake()
    servico, clientes = montar(
        [p1, p2],
        {
            1: [RespostaLLMInvalidaException("campo faltando")],
            2: [resposta_de(p2)],
        },
        registrador,
    )

    with pytest.raises(RespostaLLMInvalidaException):
        servico.gerar(sessao_id=9, requisicao=requisicao())

    assert clientes[1].chamadas == 1
    assert clientes[2].chamadas == 0
    assert registrador.registros == []


def test_provedor_inativo_fica_fora_da_cadeia():
    p1, p2 = provedor(1, "inativo", 1), provedor(2, "ativo", 2)
    p1.ativo = False
    servico, clientes = montar([p1, p2], {2: [resposta_de(p2)]})

    assert servico.gerar(sessao_id=9, requisicao=requisicao()).provedor_id == 2
    assert 1 not in clientes


def test_cadeia_vazia_e_erro_de_configuracao():
    servico = ProvedorLLMService(
        db=DbFalso([]),
        registrador=RegistradorConsumoFake(),
        fabrica=lambda p: None,
        tentativas=2,
    )
    with pytest.raises(NenhumProvedorAtivoException):
        servico.gerar(sessao_id=9, requisicao=requisicao())


from backend.app.services.log_auditoria import pseudonimo


def test_fallback_grava_evento_com_as_falhas():
    p1, p2 = provedor(1, "primario", 1), provedor(2, "fallback", 2)
    db = DbFalso([p1, p2])
    servico, _ = montar(
        [p1, p2],
        {1: [FalhaTransporteLLMException("HTTP 500")] * 2, 2: [resposta_de(p2)]},
        db=db,
    )
    servico.gerar(sessao_id=9, requisicao=requisicao())

    [evento] = db.adicionados
    assert evento.tipo_evento == "fallback_provedor"
    assert evento.entidade_afetada == "sessoes_geracao:9"
    assert evento.ator == pseudonimo(7)
    assert evento.payload == {
        "provedor_usado": "fallback",
        "falhas": [
            {
                "provedor": "primario",
                "motivo": "Falha ao falar com o provedor: HTTP 500.",
            }
        ],
    }


def test_primario_saudavel_nao_grava_evento():
    p1 = provedor(1, "primario", 1)
    db = DbFalso([p1])
    servico, _ = montar([p1], {1: [resposta_de(p1)]}, db=db)
    servico.gerar(sessao_id=9, requisicao=requisicao())
    assert db.adicionados == []


def test_retentativa_no_mesmo_provedor_nao_e_fallback():
    p1, p2 = provedor(1, "primario", 1), provedor(2, "fallback", 2)
    db = DbFalso([p1, p2])
    servico, _ = montar(
        [p1, p2],
        {1: [FalhaTransporteLLMException("timeout"), resposta_de(p1)], 2: []},
        db=db,
    )
    servico.gerar(sessao_id=9, requisicao=requisicao())
    assert db.adicionados == []


def test_falha_da_cadeia_grava_e_confirma_antes_de_levantar():
    p1, p2 = provedor(1, "primario", 1), provedor(2, "fallback", 2)
    p2.endpoint = "http://segredo.interno:11434"
    p2.referencia_chave_secrets = "cofre/llm/fallback"
    db = DbFalso([p1, p2])
    servico, _ = montar(
        [p1, p2],
        {
            1: [FalhaTransporteLLMException("HTTP 500")] * 2,
            2: [FalhaTransporteLLMException("ConnectError")] * 2,
        },
        db=db,
    )
    with pytest.raises(FalhaProvedorLLMException):
        servico.gerar(sessao_id=9, requisicao=requisicao())

    [evento] = db.adicionados
    assert evento.tipo_evento == "falha_provedor"
    assert db.commits == 1
    texto = repr(evento.payload)
    assert "segredo.interno" not in texto
    assert "cofre/llm" not in texto


class DbSemSessao(DbFalso):
    def get(self, _modelo, _id):
        return None


def test_falha_da_cadeia_sem_sessao_ainda_levanta_falha_do_provedor_e_registra():
    """Achado 10: `db.get` devolve None para sessão inexistente; o evento de
    falha não pode virar AttributeError e esconder a FalhaProvedorLLMException."""
    p1 = provedor(1, "primario", 1)
    db = DbSemSessao([p1])
    servico, _ = montar(
        [p1], {1: [FalhaTransporteLLMException("HTTP 500")] * 2}, db=db
    )

    with pytest.raises(FalhaProvedorLLMException):
        servico.gerar(sessao_id=9, requisicao=requisicao())

    assert len(db.adicionados) == 1
    assert db.adicionados[0].ator is None
