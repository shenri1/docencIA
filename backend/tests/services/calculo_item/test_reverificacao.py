from backend.app.services.calculo_item.montagem import montar_calculo
from backend.app.services.calculo_item.reverificacao import reverificar
from backend.tests.services.calculo_item.test_montagem import _saida


def _gravadas(montada):
    return [
        (chr(65 + i), a.texto, chr(65 + i) == montada.letra_correta)
        for i, a in enumerate(montada.alternativas)
    ]


def test_questao_integra_nao_diverge():
    montada = montar_calculo(_saida(), k=4, numero=3)
    assert reverificar(montada.estrutura_formato, _gravadas(montada)) == []


def test_alternativa_correta_adulterada_diverge():
    montada = montar_calculo(_saida(), k=4, numero=3)
    gravadas = [
        (letra, r"\(9{,}99\ \frac{\mathrm{m}}{\mathrm{s}}\)" if c else t, c)
        for letra, t, c in _gravadas(montada)
    ]
    achados = reverificar(montada.estrutura_formato, gravadas)
    assert len(achados) == 1
    assert achados[0][0] == montada.letra_correta


def test_distrator_adulterado_diverge():
    montada = montar_calculo(_saida(), k=4, numero=3)
    gravadas = _gravadas(montada)
    letra, _, _ = next(g for g in gravadas if not g[2])
    gravadas = [(le, "outro" if le == letra else t, c) for le, t, c in gravadas]
    achados = reverificar(montada.estrutura_formato, gravadas)
    assert [a[0] for a in achados] == [letra]


def test_estrutura_que_nao_calcula_diverge_sem_levantar():
    montada = montar_calculo(_saida(), k=4, numero=3)
    estrutura = {**montada.estrutura_formato, "expressao": "__import__('os')"}
    assert reverificar(estrutura, _gravadas(montada))


def test_estrutura_vazia_diverge_sem_levantar():
    assert reverificar({}, [("A", "x", True)])
