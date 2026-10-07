from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text

from backend.app.core.config import settings
from backend.app.models import Base

RAIZ = Path(__file__).resolve().parents[2]
BANCO_MIGRACAO = "docencia_migracao_test"


@pytest.fixture(scope="module")
def engine_migrado():
    """Banco construído SÓ por migração — é isso que torna a comparação com
    os models significativa."""
    base_url = settings.database_url.rsplit("/", 1)[0]
    # "postgres" é o banco de manutenção que existe em qualquer instância —
    # nunca depender do banco de dev "docencia" para emitir CREATE DATABASE.
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        # Enum types criados por op.create_table não são derrubados pelo
        # downgrade; recriar o banco do zero garante uma base limpa.
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BANCO_MIGRACAO}"'))
        conn.execute(text(f'CREATE DATABASE "{BANCO_MIGRACAO}"'))
    admin.dispose()

    url = f"{base_url}/{BANCO_MIGRACAO}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "head")

    eng = create_engine(url)
    yield eng
    eng.dispose()


def test_migracao_reproduz_os_models_sem_diferenca(engine_migrado):
    with engine_migrado.connect() as conexao:
        contexto = MigrationContext.configure(
            conexao, opts={"compare_type": True, "include_schemas": False}
        )
        diferencas = compare_metadata(contexto, Base.metadata)
    assert diferencas == [], f"Migração fora de sincronia com os models: {diferencas}"


def test_seed_cria_a_cadeia_de_fallback(engine_migrado):
    with engine_migrado.connect() as conexao:
        linhas = conexao.execute(
            text(
                "SELECT nome, modelo, prioridade, endpoint, "
                "referencia_chave_secrets FROM provedores_llm "
                "WHERE ativo = true ORDER BY prioridade"
            )
        ).all()

    assert [(linha[0], linha[1], linha[2]) for linha in linhas] == [
        ("ollama-qwen3.5-9b", "qwen3.5:9b", 1),
        ("ollama-qwen3-4b", "qwen3:4b", 2),
        ("ollama-qwen3-1.7b", "qwen3:1.7b", 3),
    ]
    # endpoint NULL = usar settings.llm_base_url, que difere entre local e
    # Compose. Gravar um host aqui quebraria um dos dois ambientes.
    assert all(linha[3] is None for linha in linhas)
    assert all(linha[4] is None for linha in linhas)


BANCO_MIGRACAO_DADOS = "docencia_migracao_dados_test"


def test_migracao_10c_preserva_bancos_e_questoes_existentes():
    """Questões objetivas geradas antes da 10c continuam válidas: viram
    tipo OBJETIVA, e o banco ganha n_alvo_objetivas = n_alvo."""
    base_url = settings.database_url.rsplit("/", 1)[0]
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BANCO_MIGRACAO_DADOS}"'))
        conn.execute(text(f'CREATE DATABASE "{BANCO_MIGRACAO_DADOS}"'))
    admin.dispose()

    url = f"{base_url}/{BANCO_MIGRACAO_DADOS}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "e5b2c9d71a40")

    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            docente_id = conn.execute(
                text(
                    "INSERT INTO docentes (nome, credencial_institucional, "
                    "senha_hash, perfil) VALUES ('Ana', 'ana01', 'x', 'DOCENTE') "
                    "RETURNING id"
                )
            ).scalar_one()
            sessao_id = conn.execute(
                text(
                    "INSERT INTO sessoes_geracao (docente_id, disciplina, periodo, "
                    "k_alternativas, p_f, p_m, p_d, estado) VALUES "
                    "(:d, 'Algoritmos', '2026.2', 5, 30, 40, 30, "
                    "'MATERIAIS_CONFIRMADOS') RETURNING id"
                ),
                {"d": docente_id},
            ).scalar_one()
            banco_id = conn.execute(
                text(
                    "INSERT INTO bancos_questoes (sessao_id, versao, estado, n_alvo, "
                    "n_atual) VALUES (:s, 'v1', 'ABERTO', 7, 1) RETURNING id"
                ),
                {"s": sessao_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO questoes (banco_id, numero, enunciado, nivel_bloom, "
                    "faixa_dificuldade, estado) VALUES "
                    "(:b, 1, 'Qual?', 'APLICAR', 'MEDIA', 'ATIVA')"
                ),
                {"b": banco_id},
            )

        command.upgrade(cfg, "head")

        with eng.connect() as conn:
            assert conn.execute(text("SELECT tipo FROM questoes")).scalar_one() == (
                "OBJETIVA"
            )
            linha = conn.execute(
                text(
                    "SELECT n_alvo_objetivas, n_alvo_discursivas FROM bancos_questoes"
                )
            ).one()
            assert tuple(linha) == (7, 0)
    finally:
        eng.dispose()


BANCO_MIGRACAO_11 = "docencia_migracao_11_test"


def test_migracao_11_preserva_bancos_e_questoes_existentes():
    """Banco gerado antes continua válido: ganha revisao = 0, e a
    questão existente segue ocupando o seu número sob o índice parcial."""
    base_url = settings.database_url.rsplit("/", 1)[0]
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BANCO_MIGRACAO_11}"'))
        conn.execute(text(f'CREATE DATABASE "{BANCO_MIGRACAO_11}"'))
    admin.dispose()

    url = f"{base_url}/{BANCO_MIGRACAO_11}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "a8d4e2f61c37")

    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            docente_id = conn.execute(
                text(
                    "INSERT INTO docentes (nome, credencial_institucional, "
                    "senha_hash, perfil) VALUES ('Ana', 'ana11', 'x', 'DOCENTE') "
                    "RETURNING id"
                )
            ).scalar_one()
            sessao_id = conn.execute(
                text(
                    "INSERT INTO sessoes_geracao (docente_id, disciplina, periodo, "
                    "k_alternativas, p_f, p_m, p_d, estado) VALUES "
                    "(:d, 'Algoritmos', '2026.2', 5, 30, 40, 30, "
                    "'MATERIAIS_CONFIRMADOS') RETURNING id"
                ),
                {"d": docente_id},
            ).scalar_one()
            banco_id = conn.execute(
                text(
                    "INSERT INTO bancos_questoes (sessao_id, versao, estado, n_alvo, "
                    "n_alvo_objetivas, n_alvo_discursivas, n_atual) VALUES "
                    "(:s, 'v1', 'ABERTO', 7, 7, 0, 1) RETURNING id"
                ),
                {"s": sessao_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO questoes (banco_id, numero, tipo, enunciado, "
                    "nivel_bloom, faixa_dificuldade, estado) VALUES "
                    "(:b, 1, 'OBJETIVA', 'Qual?', 'APLICAR', 'MEDIA', 'ATIVA')"
                ),
                {"b": banco_id},
            )

        command.upgrade(cfg, "head")

        with eng.begin() as conn:
            assert (
                conn.execute(text("SELECT revisao FROM bancos_questoes")).scalar_one()
                == 0
            )
            assert conn.execute(text("SELECT count(*) FROM questoes")).scalar_one() == 1
            # 'CANDIDATA' existe e é usável: é o que o autocommit_block garante.
            conn.execute(
                text(
                    "INSERT INTO questoes (banco_id, numero, tipo, enunciado, "
                    "nivel_bloom, faixa_dificuldade, estado) VALUES "
                    "(:b, 1, 'OBJETIVA', 'Candidata?', 'APLICAR', 'MEDIA', "
                    "'CANDIDATA')"
                ),
                {"b": banco_id},
            )
    finally:
        eng.dispose()


BANCO_MIGRACAO_16 = "docencia_migracao_16_test"


def test_migracao_pseudonimiza_o_ator_legado():
    """ parte B gravava a credencial em claro. A migração troca pelo
    pseudônimo, anula credencial sem docente e não toca pseudônimo existente —
    inclusive ao rodar de novo."""
    from backend.app.services.log_auditoria import pseudonimo

    base_url = settings.database_url.rsplit("/", 1)[0]
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BANCO_MIGRACAO_16}"'))
        conn.execute(text(f'CREATE DATABASE "{BANCO_MIGRACAO_16}"'))
    admin.dispose()

    url = f"{base_url}/{BANCO_MIGRACAO_16}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "c4a7e19d3f58")

    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            docente_id = conn.execute(
                text(
                    "INSERT INTO docentes (nome, credencial_institucional, "
                    "senha_hash, perfil) VALUES ('Ana', 'ana16', 'x', 'DOCENTE') "
                    "RETURNING id"
                )
            ).scalar_one()
            ja_pseudonimo = "a" * 64
            for ator, tipo in (
                ("ana16", "auditoria_questao"),
                ("sumiu16", "auditoria_questao"),
                (ja_pseudonimo, "auditoria_questao"),
                ("ana16", "outro_evento"),
            ):
                conn.execute(
                    text(
                        "INSERT INTO registros_auditoria (tipo_evento, "
                        "entidade_afetada, payload, ator) VALUES "
                        "(:t, 'questoes:1', '{}'::jsonb, :a)"
                    ),
                    {"t": tipo, "a": ator},
                )

        def atores():
            with eng.connect() as conn:
                return conn.execute(
                    text("SELECT ator FROM registros_auditoria ORDER BY id")
                ).scalars().all()

        esperado = [pseudonimo(docente_id), None, ja_pseudonimo, "ana16"]
        command.upgrade(cfg, "head")
        assert atores() == esperado

        # Rodar de novo (downgrade é no-op) não transforma pseudônimo em NULL.
        command.downgrade(cfg, "c4a7e19d3f58")
        command.upgrade(cfg, "head")
        assert atores() == esperado
    finally:
        eng.dispose()


BANCO_SEMENTE = "docencia_migracao_semente_test"


def _banco_ate(revisao: str):
    """Banco novo migrado até `revisao`; devolve (cfg, engine)."""
    base_url = settings.database_url.rsplit("/", 1)[0]
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BANCO_SEMENTE}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{BANCO_SEMENTE}"'))
    admin.dispose()

    url = f"{base_url}/{BANCO_SEMENTE}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, revisao)
    return cfg, create_engine(url)


def _admin_do_env(monkeypatch, credencial="admin", nome="Admin", senha="senhaforte123"):
    monkeypatch.setattr(settings, "admin_credencial", credencial)
    monkeypatch.setattr(settings, "admin_nome", nome)
    monkeypatch.setattr(settings, "admin_senha", senha)


def test_semente_cria_admin_do_env_e_ativa_prompt(monkeypatch):
    from backend.app.core.security import verificar_senha

    _admin_do_env(monkeypatch)
    cfg, eng = _banco_ate("d8b3f6a2c914")
    try:
        command.upgrade(cfg, "head")
        # Rodar de novo (downgrade é no-op) não duplica nada.
        command.downgrade(cfg, "d8b3f6a2c914")
        command.upgrade(cfg, "head")

        with eng.connect() as conn:
            [(nome, perfil, senha_hash)] = conn.execute(
                text("SELECT nome, perfil, senha_hash FROM docentes")
            ).all()
            prompts = conn.execute(
                text("SELECT versao, ativo FROM prompts_mestres")
            ).all()
        assert (nome, perfil) == ("Admin", "ADMINISTRADOR")
        assert verificar_senha("senhaforte123", senha_hash)
        assert [tuple(p) for p in prompts] == [("1.0.0", True)]
    finally:
        eng.dispose()


def test_semente_promove_conta_existente_sem_trocar_a_senha(monkeypatch):
    _admin_do_env(monkeypatch, credencial="ana", senha="outrasenha123")
    cfg, eng = _banco_ate("d8b3f6a2c914")
    try:
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO docentes (nome, credencial_institucional, "
                    "senha_hash, perfil) VALUES ('Ana', 'ana', 'hash-antigo', 'DOCENTE')"
                )
            )
        command.upgrade(cfg, "head")

        with eng.connect() as conn:
            linha = conn.execute(
                text("SELECT perfil, senha_hash FROM docentes WHERE credencial_institucional = 'ana'")
            ).one()
        assert tuple(linha) == ("ADMINISTRADOR", "hash-antigo")
    finally:
        eng.dispose()


def test_semente_sem_env_nao_cria_admin_mas_ativa_prompt(monkeypatch):
    _admin_do_env(monkeypatch, credencial=None, nome=None, senha=None)
    cfg, eng = _banco_ate("d8b3f6a2c914")
    try:
        command.upgrade(cfg, "head")
        with eng.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM docentes")).scalar_one() == 0
            assert conn.execute(
                text("SELECT count(*) FROM prompts_mestres WHERE ativo")
            ).scalar_one() == 1
    finally:
        eng.dispose()


def test_semente_recusa_senha_curta(monkeypatch):
    _admin_do_env(monkeypatch, senha="curta")
    cfg, eng = _banco_ate("d8b3f6a2c914")
    try:
        with pytest.raises(ValueError, match="ADMIN_SENHA"):
            command.upgrade(cfg, "head")
    finally:
        eng.dispose()


def _cadeia(eng):
    with eng.connect() as conn:
        return [
            tuple(linha)
            for linha in conn.execute(
                text(
                    "SELECT nome, modelo, prioridade FROM provedores_llm "
                    "WHERE ativo = true ORDER BY prioridade"
                )
            ).all()
        ]


def test_migracao_qwen35_ida_e_volta(monkeypatch):
    """A troca de modelo regrava as tags (desfaz edição manual da linha), e o
    downgrade não apaga o 9b quando uma sessão já aponta para ele."""
    _admin_do_env(monkeypatch, credencial=None, nome=None, senha=None)
    cfg, eng = _banco_ate("e1a4c8f02b77")
    try:
        with eng.begin() as conn:
            conn.execute(
                text(
                    "UPDATE provedores_llm SET modelo = 'qwen3:latest' "
                    "WHERE nome = 'ollama-qwen3-4b'"
                )
            )

        cadeia_nova = [
            ("ollama-qwen3.5-9b", "qwen3.5:9b", 1),
            ("ollama-qwen3-4b", "qwen3:4b", 2),
            ("ollama-qwen3-1.7b", "qwen3:1.7b", 3),
        ]
        command.upgrade(cfg, "head")
        assert _cadeia(eng) == cadeia_nova

        with eng.begin() as conn:
            docente_id = conn.execute(
                text(
                    "INSERT INTO docentes (nome, credencial_institucional, "
                    "senha_hash, perfil) VALUES ('Ana', 'ana35', 'x', 'DOCENTE') "
                    "RETURNING id"
                )
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO sessoes_geracao (docente_id, disciplina, periodo, "
                    "k_alternativas, p_f, p_m, p_d, estado, provedor_llm_id) "
                    "SELECT :d, 'Algoritmos', '2026.2', 5, 30, 40, 30, "
                    "'MATERIAIS_CONFIRMADOS', id FROM provedores_llm "
                    "WHERE nome = 'ollama-qwen3.5-9b'"
                ),
                {"d": docente_id},
            )

        command.downgrade(cfg, "e1a4c8f02b77")
        assert _cadeia(eng) == [
            ("ollama-qwen3-4b", "qwen3:4b", 1),
            ("ollama-qwen3-1.7b", "qwen3:1.7b", 2),
        ]

        # Subir de novo reativa a linha que o downgrade só desativou.
        command.upgrade(cfg, "head")
        assert _cadeia(eng) == cadeia_nova
    finally:
        eng.dispose()
