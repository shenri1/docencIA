import hashlib
import io

import docx
import pytest

from backend.app.domain import EstadoSessao, TipoExportacao
from backend.app.exceptions import (
    ArquivoExportadoCorrompidoException,
    ExportacaoNaoEncontradaException,
    InconsistenciaDeEstadoException,
)
from backend.app.models.provas import ExportacaoDocx
from backend.app.schemas.identidade import DocenteCriar
from backend.app.services.auth_service import registrar_docente
from backend.app.services.exportacao.exportacao_service import (
    abrir_exportacao,
    exportar,
    listar_exportacoes,
)
from backend.tests.services.provas.test_gabarito import provas_montadas


def test_exporta_dois_arquivos_e_dois_registros(
    db_session, docente, sessao_rascunho, armazenamento
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    registros = exportar(db_session, docente, armazenamento, banco)

    assert sorted(r.tipo.value for r in registros) == ["conteudo_puro", "metadados"]
    for registro in registros:
        dados = armazenamento.abrir(registro.caminho_arquivo)
        assert hashlib.sha256(dados).hexdigest() == registro.hash_conteudo
        assert registro.revisao_banco == banco.revisao
        docx.Document(io.BytesIO(dados))  # abre: é DOCX válido
    assert sessao_rascunho.estado is EstadoSessao.EXPORTADO


def test_conteudo_puro_exportado_nao_tem_gabarito(
    db_session, docente, sessao_rascunho, armazenamento
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    registros = exportar(db_session, docente, armazenamento, banco)
    puro = next(r for r in registros if r.tipo is TipoExportacao.CONTEUDO_PURO)
    texto = "\n".join(
        p.text
        for p in docx.Document(
            io.BytesIO(armazenamento.abrir(puro.caminho_arquivo))
        ).paragraphs
    )
    for proibido in ("Resposta:", "Justificativa", "Trecho-base", "Fonte:"):
        assert proibido not in texto


def test_exportar_de_novo_na_mesma_revisao_nao_cria_linha(
    db_session, docente, sessao_rascunho, armazenamento
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    primeira = exportar(db_session, docente, armazenamento, banco)
    segunda = exportar(db_session, docente, armazenamento, banco)
    assert {r.id for r in primeira} == {r.id for r in segunda}
    assert db_session.query(ExportacaoDocx).count() == 2


def test_estado_incoerente_nao_salva_nada(
    db_session, docente, sessao_rascunho, armazenamento
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    banco.n_atual = 99
    db_session.commit()
    with pytest.raises(InconsistenciaDeEstadoException):
        exportar(db_session, docente, armazenamento, banco)
    assert db_session.query(ExportacaoDocx).count() == 0
    assert not any(armazenamento.raiz.rglob("*.docx"))


def test_depois_de_mudar_a_revisao_o_arquivo_antigo_continua_integro(
    db_session, docente, sessao_rascunho, armazenamento
):
    """Substituição depois da montagem bloqueia nova exportação (risco
    declarado ), mas o que já saiu continua baixável e íntegro."""
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    registros = exportar(db_session, docente, armazenamento, banco)
    banco.revisao += 1
    db_session.commit()

    with pytest.raises(InconsistenciaDeEstadoException):
        exportar(db_session, docente, armazenamento, banco)
    for registro in registros:
        _, dados = abrir_exportacao(db_session, docente, armazenamento, registro.id)
        assert hashlib.sha256(dados).hexdigest() == registro.hash_conteudo


def test_arquivo_alterado_no_armazenamento_nao_e_entregue(
    db_session, docente, sessao_rascunho, armazenamento
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    registro = exportar(db_session, docente, armazenamento, banco)[0]
    armazenamento.salvar(registro.caminho_arquivo, b"adulterado")
    with pytest.raises(ArquivoExportadoCorrompidoException):
        abrir_exportacao(db_session, docente, armazenamento, registro.id)


def test_exportacao_de_outro_docente_responde_404(
    db_session, docente, sessao_rascunho, armazenamento
):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    registro = exportar(db_session, docente, armazenamento, banco)[0]
    outro = registrar_docente(
        db_session,
        DocenteCriar(
            nome="Bruno", credencial_institucional="prof-outro-exp", senha="senhaforte123"
        ),
    )
    with pytest.raises(ExportacaoNaoEncontradaException):
        abrir_exportacao(db_session, outro, armazenamento, registro.id)


def test_listar_exportacoes(db_session, docente, sessao_rascunho, armazenamento):
    banco, _ = provas_montadas(db_session, docente, sessao_rascunho)
    exportar(db_session, docente, armazenamento, banco)
    lista = listar_exportacoes(db_session, docente, banco.id)
    assert [(r.revisao_banco, r.tipo.value) for r in lista] == [
        (banco.revisao, "conteudo_puro"),
        (banco.revisao, "metadados"),
    ]
