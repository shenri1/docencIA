import pytest

from backend.app.core.storage import ArmazenamentoLocal


def test_salvar_e_abrir_roundtrip(tmp_path):
    armazenamento = ArmazenamentoLocal(tmp_path)
    escritos = armazenamento.salvar("7/3/abc.pdf", b"conteudo")
    assert escritos == len(b"conteudo")
    assert armazenamento.abrir("7/3/abc.pdf") == b"conteudo"
    assert armazenamento.existe("7/3/abc.pdf")


def test_salvar_cria_diretorios_intermediarios(tmp_path):
    ArmazenamentoLocal(tmp_path).salvar("7/3/abc.pdf", b"x")
    assert (tmp_path / "7" / "3" / "abc.pdf").is_file()


def test_remover_apaga_o_arquivo(tmp_path):
    armazenamento = ArmazenamentoLocal(tmp_path)
    armazenamento.salvar("7/3/abc.pdf", b"x")
    armazenamento.remover("7/3/abc.pdf")
    assert not armazenamento.existe("7/3/abc.pdf")


def test_remover_arquivo_inexistente_nao_levanta(tmp_path):
    ArmazenamentoLocal(tmp_path).remover("7/3/nao-existe.pdf")


def test_chave_fora_da_raiz_e_rejeitada(tmp_path):
    armazenamento = ArmazenamentoLocal(tmp_path)
    with pytest.raises(ValueError):
        armazenamento.salvar("../fora.pdf", b"x")
    assert not (tmp_path.parent / "fora.pdf").exists()
