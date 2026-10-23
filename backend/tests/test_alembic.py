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
                text("SELECT n_alvo_objetivas, n_alvo_discursivas FROM bancos_questoes")
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
                    "INSERT INTO questoes (banco_id, numero, tipo, formato, "
                    "enunciado, nivel_bloom, faixa_dificuldade, estado) VALUES "
                    "(:b, 1, 'OBJETIVA', 'PROPOSICAO', 'Candidata?', 'APLICAR', "
                    "'MEDIA', 'CANDIDATA')"
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
                return (
                    conn.execute(
                        text("SELECT ator FROM registros_auditoria ORDER BY id")
                    )
                    .scalars()
                    .all()
                )

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
                text("SELECT versao, ativo FROM prompts_mestres ORDER BY versao")
            ).all()
        assert (nome, perfil) == ("Admin", "ADMINISTRADOR")
        assert verificar_senha("senhaforte123", senha_hash)
        # A 1.0.0 é semeada pela e1a4c8f02b77, a 2.0.0 pela b7d2e9f4a1c6,
        # a 2.1.0 pela c5e1f8a3b7d9, a 2.2.0 pela d8a4f1c6e3b2
        # e a 2.3.0 pela e9c3a6d2f8b1, que fica ativa;
        # rodar de novo não duplica nenhuma.
        assert [tuple(p) for p in prompts] == [
            ("1.0.0", False),
            ("2.0.0", False),
            ("2.1.0", False),
            ("2.2.0", False),
            ("2.3.0", True),
        ]
    finally:
        eng.dispose()


def _cadastrar_ana(eng, senha: str) -> None:
    from backend.app.core.security import hash_senha

    with eng.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO docentes (nome, credencial_institucional, "
                "senha_hash, perfil) VALUES ('Ana', 'ana', :h, 'DOCENTE')"
            ),
            {"h": hash_senha(senha)},
        )


def _perfil_da_ana(eng) -> str:
    with eng.connect() as conn:
        return conn.execute(
            text("SELECT perfil FROM docentes WHERE credencial_institucional = 'ana'")
        ).scalar_one()


def test_semente_promove_conta_existente_quando_a_senha_confere(monkeypatch):
    _admin_do_env(monkeypatch, credencial="ana", senha="senhadaana123")
    cfg, eng = _banco_ate("d8b3f6a2c914")
    try:
        _cadastrar_ana(eng, "senhadaana123")
        command.upgrade(cfg, "head")
        assert _perfil_da_ana(eng) == "ADMINISTRADOR"
    finally:
        eng.dispose()


def test_semente_recusa_promover_conta_de_outra_senha(monkeypatch):
    # Quem se cadastrou antes com a credencial do administrador não vira
    # administrador: a senha da conta tem de ser a ADMIN_SENHA.
    _admin_do_env(monkeypatch, credencial="ana", senha="senhadooperador1")
    cfg, eng = _banco_ate("d8b3f6a2c914")
    try:
        _cadastrar_ana(eng, "senhadoatacante1")
        with pytest.raises(ValueError, match="ADMIN_CREDENCIAL"):
            command.upgrade(cfg, "head")
        assert _perfil_da_ana(eng) == "DOCENTE"
    finally:
        eng.dispose()


def test_semente_sem_env_nao_cria_admin_mas_ativa_prompt(monkeypatch):
    _admin_do_env(monkeypatch, credencial=None, nome=None, senha=None)
    cfg, eng = _banco_ate("d8b3f6a2c914")
    try:
        command.upgrade(cfg, "head")
        with eng.connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM docentes")).scalar_one() == 0
            assert (
                conn.execute(
                    text("SELECT count(*) FROM prompts_mestres WHERE ativo")
                ).scalar_one()
                == 1
            )
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
        command.upgrade(cfg, "a3f9c2e7d415")
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
        command.upgrade(cfg, "a3f9c2e7d415")
        assert _cadeia(eng) == cadeia_nova
    finally:
        eng.dispose()


def test_migracao_qwen25_ida_e_volta(monkeypatch):
    """O 3b entra na frente e empurra a cadeia; o downgrade só o desativa e
    devolve as prioridades da a3f9c2e7d415."""
    _admin_do_env(monkeypatch, credencial=None, nome=None, senha=None)
    cfg, eng = _banco_ate("e9c3a6d2f8b1")
    try:
        cadeia_9b = [
            ("ollama-qwen3.5-9b", "qwen3.5:9b", 1),
            ("ollama-qwen3-4b", "qwen3:4b", 2),
            ("ollama-qwen3-1.7b", "qwen3:1.7b", 3),
        ]
        cadeia_3b = [
            ("ollama-qwen2.5-3b", "qwen2.5:3b-instruct", 1),
            ("ollama-qwen3.5-9b", "qwen3.5:9b", 2),
            ("ollama-qwen3-4b", "qwen3:4b", 3),
            ("ollama-qwen3-1.7b", "qwen3:1.7b", 4),
        ]
        assert _cadeia(eng) == cadeia_9b
        command.upgrade(cfg, "f2c8a4d1b6e7")
        assert _cadeia(eng) == cadeia_3b
        command.downgrade(cfg, "e9c3a6d2f8b1")
        assert _cadeia(eng) == cadeia_9b
        # Subir de novo reativa a linha que o downgrade só desativou.
        command.upgrade(cfg, "f2c8a4d1b6e7")
        assert _cadeia(eng) == cadeia_3b
        # O teste reprovou o 3b: a a7d3e5b9c1f4 devolve a cadeia do 9b.
        command.upgrade(cfg, "a7d3e5b9c1f4")
        assert _cadeia(eng) == cadeia_9b
        command.downgrade(cfg, "f2c8a4d1b6e7")
        assert _cadeia(eng) == cadeia_3b
    finally:
        eng.dispose()


BANCO_MIGRACAO_18 = "docencia_migracao_18_test"


def test_migracao_18_preserva_questoes_e_ativa_o_prompt_2():
    """Banco com questões gravadas antes passa no upgrade: elas
    viram PROPOSICAO, que é o que são, e o default de servidor some."""
    base_url = settings.database_url.rsplit("/", 1)[0]
    admin = create_engine(f"{base_url}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{BANCO_MIGRACAO_18}"'))
        conn.execute(text(f'CREATE DATABASE "{BANCO_MIGRACAO_18}"'))
    admin.dispose()

    url = f"{base_url}/{BANCO_MIGRACAO_18}"
    cfg = Config(str(RAIZ / "alembic.ini"))
    cfg.set_main_option("script_location", str(RAIZ / "backend" / "alembic"))
    cfg.set_main_option("sqlalchemy.url", url)
    command.upgrade(cfg, "a3f9c2e7d415")

    eng = create_engine(url)
    try:
        with eng.begin() as conn:
            docente_id = conn.execute(
                text(
                    "INSERT INTO docentes (nome, credencial_institucional, "
                    "senha_hash, perfil) VALUES ('Ana', 'ana18', 'x', 'DOCENTE') "
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

        command.upgrade(cfg, "b7d2e9f4a1c6")

        with eng.connect() as conn:
            assert conn.execute(text("SELECT formato FROM questoes")).scalar_one() == (
                "PROPOSICAO"
            )
            default = conn.execute(
                text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_name = 'questoes' AND column_name = 'formato'"
                )
            ).scalar_one()
            assert default is None
            ativos = (
                conn.execute(text("SELECT versao FROM prompts_mestres WHERE ativo"))
                .scalars()
                .all()
            )
            assert ativos == ["2.0.0"]
    finally:
        eng.dispose()


_TABELAS_19 = {"orientacoes_docente", "questoes_orientacoes"}


def _tabelas(eng) -> set[str]:
    with eng.connect() as conn:
        return set(
            conn.execute(
                text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
            ).scalars()
        )


def test_migracao_19_cria_e_remove_as_tabelas_de_orientacao():
    cfg, eng = _banco_ate("b7d2e9f4a1c6")
    try:
        command.upgrade(cfg, "head")
        assert _TABELAS_19 <= _tabelas(eng)

        command.downgrade(cfg, "b7d2e9f4a1c6")
        assert not (_TABELAS_19 & _tabelas(eng))
        with eng.connect() as conn:
            tipos = (
                conn.execute(
                    text(
                        "SELECT typname FROM pg_type WHERE typname IN "
                        "('origem_orientacao', 'estado_orientacao')"
                    )
                )
                .scalars()
                .all()
            )
        assert tipos == []
    finally:
        eng.dispose()


def test_migracao_19_ativa_o_prompt_2_1():
    cfg, eng = _banco_ate("b7d2e9f4a1c6")
    try:
        command.upgrade(cfg, "c5e1f8a3b7d9")
        with eng.connect() as conn:
            ativos = (
                conn.execute(text("SELECT versao FROM prompts_mestres WHERE ativo"))
                .scalars()
                .all()
            )
        assert ativos == ["2.1.0"]
    finally:
        eng.dispose()


def test_migracao_20_ativa_o_prompt_2_2():
    cfg, eng = _banco_ate("c5e1f8a3b7d9")
    try:
        command.upgrade(cfg, "d8a4f1c6e3b2")
        with eng.connect() as conn:
            ativos = (
                conn.execute(text("SELECT versao FROM prompts_mestres WHERE ativo"))
                .scalars()
                .all()
            )
            existentes = (
                conn.execute(text("SELECT versao FROM prompts_mestres ORDER BY versao"))
                .scalars()
                .all()
            )
        assert ativos == ["2.2.0"]
        assert existentes[-3:] == ["2.0.0", "2.1.0", "2.2.0"]
    finally:
        eng.dispose()


def test_migracao_calculo_aceita_formato_calculo():
    from sqlalchemy.exc import IntegrityError

    cfg, eng = _banco_ate("d8a4f1c6e3b2")
    try:
        command.upgrade(cfg, "head")
        with eng.begin() as conn:
            docente_id = conn.execute(
                text(
                    "INSERT INTO docentes (nome, credencial_institucional, "
                    "senha_hash, perfil) VALUES ('Ana', 'ana21', 'x', 'DOCENTE') "
                    "RETURNING id"
                )
            ).scalar_one()
            sessao_id = conn.execute(
                text(
                    "INSERT INTO sessoes_geracao (docente_id, disciplina, periodo, "
                    "k_alternativas, p_f, p_m, p_d, p_calculo, estado) VALUES "
                    "(:d, 'Física', '2026.2', 5, 30, 40, 30, 30, "
                    "'MATERIAIS_CONFIRMADOS') RETURNING id"
                ),
                {"d": docente_id},
            ).scalar_one()
            banco_id = conn.execute(
                text(
                    "INSERT INTO bancos_questoes (sessao_id, versao, estado, n_alvo, "
                    "n_alvo_objetivas, n_alvo_discursivas, n_atual) VALUES "
                    "(:s, 'v1', 'ABERTO', 1, 1, 0, 1) RETURNING id"
                ),
                {"s": sessao_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO questoes (banco_id, numero, tipo, enunciado, "
                    "nivel_bloom, faixa_dificuldade, estado, formato) VALUES "
                    "(:b, 1, 'OBJETIVA', 'Calcule.', 'APLICAR', 'MEDIA', 'ATIVA', "
                    "'CALCULO')"
                ),
                {"b": banco_id},
            )
        with eng.connect() as conn:
            assert (
                conn.execute(text("SELECT formato FROM questoes")).scalar_one()
                == "CALCULO"
            )
            padrao = conn.execute(
                text(
                    "SELECT column_default FROM information_schema.columns "
                    "WHERE table_name='sessoes_geracao' AND column_name='p_calculo'"
                )
            ).scalar_one()
            assert padrao == "0"
        with pytest.raises(IntegrityError), eng.begin() as conn:
            conn.execute(
                text("UPDATE sessoes_geracao SET p_calculo = 101 WHERE id = :s"),
                {"s": sessao_id},
            )
    finally:
        eng.dispose()


def test_migracao_21_ativa_o_prompt_2_3_e_desfaz_a_coluna():
    cfg, eng = _banco_ate("d8a4f1c6e3b2")
    try:
        command.upgrade(cfg, "head")
        with eng.connect() as conn:
            ativos = (
                conn.execute(text("SELECT versao FROM prompts_mestres WHERE ativo"))
                .scalars()
                .all()
            )
        assert ativos == ["2.3.0"]
        command.downgrade(cfg, "d8a4f1c6e3b2")
        with eng.connect() as conn:
            colunas = (
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name='sessoes_geracao'"
                    )
                )
                .scalars()
                .all()
            )
        assert "p_calculo" not in colunas
    finally:
        eng.dispose()
