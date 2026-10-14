"""Vocabulário fechado do domínio.

Enums persistidos como tipo nativo do Postgres: evita strings livres
inconsistentes. Valores em português, pois é o mesmo texto que aparece nos
relatórios e no payload da API.
"""

from enum import Enum


class PerfilDocente(str, Enum):
    DOCENTE = "docente"
    COORDENADOR = "coordenador"
    ADMINISTRADOR = "administrador"


class EstadoSessao(str, Enum):
    RASCUNHO = "rascunho"
    MATERIAIS_CONFIRMADOS = "materiais_confirmados"
    BANCO_GERADO = "banco_gerado"
    BANCO_CONGELADO = "banco_congelado"
    PROVAS_MONTADAS = "provas_montadas"
    EXPORTADO = "exportado"


class TipoMaterial(str, Enum):
    SLIDE = "slide"
    PDF = "pdf"
    LIVRO = "livro"


class FormatoArquivo(str, Enum):
    """Formato físico do arquivo enviado — detectado pelo sistema, diferente
    de TipoMaterial, que é a classificação didática informada pelo docente."""

    PDF = "pdf"
    PPTX = "pptx"
    DOCX = "docx"
    TXT = "txt"


class OrigemTexto(str, Enum):
    NATIVO = "nativo"
    OCR = "ocr"
    MISTO = "misto"


class StatusLegibilidade(str, Enum):
    PENDENTE = "pendente"
    LEGIVEL = "legivel"
    ILEGIVEL = "ilegivel"


class TipoProvedorLLM(str, Enum):
    NUVEM = "nuvem"
    LOCAL = "local"


class EstadoBanco(str, Enum):
    ABERTO = "aberto"
    CONGELADO = "congelado"


class EstadoQuestao(str, Enum):
    ATIVA = "ativa"
    EXCLUIDA = "excluida"
    # a original de uma substituição aceita. Mantém o número e o
    # motivo da troca; não conta em n_atual.
    SUBSTITUIDA = "substituida"
    # Gerada por propor_substituicao e ainda não lida pelo docente: ocupa uma
    # linha de `questoes` sem estar no banco. Toda consulta que conta ou lista
    # questão precisa filtrar por estado.
    CANDIDATA = "candidata"
    # Candidata rejeitada pelo docente. Fica gravada: a rejeição é dado.
    DESCARTADA = "descartada"


class EventoBanco(str, Enum):
    """O que motivou um RelatorioImpacto."""

    EXCLUSAO = "exclusao"
    SUBSTITUICAO = "substituicao"
    CONGELAMENTO = "congelamento"


class DecisaoSubstituicao(str, Enum):
    ACEITA = "aceita"
    REJEITADA = "rejeitada"


class OrigemOrientacao(str, Enum):
    """onde o docente deu a orientação — na sessão, antes de gerar, ou
    numa questão, ao pedir uma variação guiada."""

    SESSAO = "sessao"
    QUESTAO = "questao"


class EstadoOrientacao(str, Enum):
    """A única transição é ATIVA → INATIVA. PONTUAL vale para a chamada
    que a criou e nunca entra em outra geração."""

    ATIVA = "ativa"
    INATIVA = "inativa"
    PONTUAL = "pontual"


class NivelBloom(str, Enum):
    LEMBRAR = "lembrar"
    ENTENDER = "entender"
    APLICAR = "aplicar"
    ANALISAR = "analisar"
    AVALIAR = "avaliar"
    CRIAR = "criar"


class FaixaDificuldade(str, Enum):
    FACIL = "facil"
    MEDIA = "media"
    DIFICIL = "dificil"


class TipoQuestao(str, Enum):
    """Discriminador do item. Decide schema, prompt, validador e o
    que é persistido: alternativas ou aspectos esperados."""

    OBJETIVA = "objetiva"
    DISCURSIVA = "discursiva"


class FormatoItem(str, Enum):
    """Atribuído pelo plano do banco, nunca escolhido pelo modelo. O
    valor é também o nome da pasta do formato em `prompt/objetiva/formatos/`."""

    PROPOSICAO = "proposicao"
    AFIRMATIVAS = "afirmativas"
    ASSERCAO_RAZAO = "assercao_razao"


class EstadoProva(str, Enum):
    RASCUNHO = "rascunho"
    MONTADA = "montada"
    CONGELADA = "congelada"


class TipoGabarito(str, Enum):
    SIMPLES = "simples"
    COMENTADO = "comentado"


class TipoExportacao(str, Enum):
    CONTEUDO_PURO = "conteudo_puro"
    METADADOS = "metadados"


class RegraQualidade(str, Enum):
    """Regras de forma, e, medidas sem LLM."""

    TAMANHO_ALTERNATIVA = "tamanho_alternativa"
    CORRETA_LONGA = "correta_longa"
    TERMO_ABSOLUTO = "termo_absoluto"
    MENCAO_FONTE = "mencao_fonte"
    GEMEOS_INSUFICIENTES = "gemeos_insuficientes"
    GEMEO_NA_CORRETA = "gemeo_na_correta"
    COMANDO_AUSENTE = "comando_ausente"
    ASPECTOS_REPETIDOS = "aspectos_repetidos"
    INVALIDACAO_LETRA_INVALIDA = "invalidacao_letra_invalida"
    LETRA_CITADA_EM_TEXTO = "letra_citada_em_texto"
    #.
    CONTEXTO_CURTO = "contexto_curto"
    ALTERNATIVA_ROTULO = "alternativa_rotulo"
    ALTERNATIVA_GENERICA = "alternativa_generica"
    COMANDO_NEGATIVO = "comando_negativo"
    PONTUACAO_INCOERENTE = "pontuacao_incoerente"
    ASSERCAO_CITACAO = "assercao_citacao"
    OPINIAO_PESSOAL = "opiniao_pessoal"
    #.
    NOTACAO_INVALIDA = "notacao_invalida"


class RiscoAuditoria(str, Enum):
    """Os dois primeiros são juízo semântico e vêm do modelo; o
    terceiro é medido por `validar_objetiva` e nunca vem dele."""

    CORRETA_NAO_UNICA = "correta_nao_unica"
    DISTRATOR_INDEFENSAVEL = "distrator_indefensavel"
    ASSIMETRIA_FORMA = "assimetria_forma"


class Marco(str, Enum):
    """Derivado do estado gravado a cada pedido, nunca persistido.
    Numeração (F5–F12 ↔ M2–M10); M4, M5, M7, M8 e
    M9 não são paradas: auditar é comando próprio, e os demais saem embutidos
    na resposta do passo anterior."""

    M1_MATERIAIS = "m1_materiais"
    M2_BANCO = "m2_banco"
    M3_EXCLUSOES = "m3_exclusoes"
    M6_PROVAS = "m6_provas"
    M10_DOCX = "m10_docx"
    CONCLUIDO = "concluido"
    BLOQUEADO = "bloqueado"


class ComandoOrquestrador(str, Enum):
    PROSSEGUIR = "prosseguir"
    EXCLUIR = "excluir"
    AUDITAR = "auditar"


class TipoEventoAuditoria(str, Enum):
    """`registros_auditoria.tipo_evento` é String(100): este enum é o
    vocabulário, não um tipo do banco — acrescentar membro não pede migração."""

    QUESTAO_GERADA = "questao_gerada"
    EXCLUSAO = "exclusao"
    CONGELAMENTO = "congelamento"
    SUBSTITUICAO_ACEITA = "substituicao_aceita"
    SUBSTITUICAO_REJEITADA = "substituicao_rejeitada"
    PROVAS_MONTADAS = "provas_montadas"
    EXPORTACAO_DOCX = "exportacao_docx"
    FALLBACK_PROVEDOR = "fallback_provedor"
    FALHA_PROVEDOR = "falha_provedor"
    AUDITORIA_QUESTAO = "auditoria_questao"
    LOGIN_FALHO = "login_falho"
    TOKEN_SUSPEITO = "token_suspeito"
    ACESSO_NEGADO = "acesso_negado"
    ORIENTACAO_CRIADA = "orientacao_criada"
    ORIENTACAO_DESATIVADA = "orientacao_desativada"
