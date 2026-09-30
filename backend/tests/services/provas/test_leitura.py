from types import SimpleNamespace

from backend.app.domain import TipoQuestao
from backend.app.services.provas.leitura import letras_na_prova


def item_falso(ordem, tipo=TipoQuestao.OBJETIVA, k=5):
    """Função pura sobre dois atributos: não precisa de banco."""
    alternativas = [SimpleNamespace(letra=letra) for letra in "ABCDEFGHIJK"[:k]]
    questao = SimpleNamespace(tipo=tipo, alternativas=alternativas)
    return SimpleNamespace(questao=questao, ordem_alternativas=ordem)


def test_permutacao_identidade():
    assert letras_na_prova(item_falso(list("ABCDE"))) == {
        "A": "A", "B": "B", "C": "C", "D": "D", "E": "E",
    }


def test_permutacao_qualquer():
    """ordem[i] é a original que aparece na posição i. C na posição 0 vira A."""
    assert letras_na_prova(item_falso(["C", "A", "E", "B", "D"])) == {
        "C": "A", "A": "B", "E": "C", "B": "D", "D": "E",
    }


def test_discursiva_nao_tem_letra():
    assert letras_na_prova(item_falso(None, tipo=TipoQuestao.DISCURSIVA)) == {}
