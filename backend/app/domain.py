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
    """Regras de forma e, medidas sem LLM."""

    TAMANHO_ALTERNATIVA = "tamanho_alternativa"
    CORRETA_LONGA = "correta_longa"
    TERMO_ABSOLUTO = "termo_absoluto"
    MENCAO_FONTE = "mencao_fonte"
    GEMEOS_INSUFICIENTES = "gemeos_insuficientes"
    GEMEO_NA_CORRETA = "gemeo_na_correta"
    COMANDO_AUSENTE = "comando_ausente"
    ASPECTOS_REPETIDOS = "aspectos_repetidos"
