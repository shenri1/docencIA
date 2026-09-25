class DomainException(Exception):
    """Base das exceções de negócio. Não são bugs: representam comportamento
    obrigatório do sistema. O handler genérico usa status_code,
    codigo e headers para montar a resposta."""

    status_code: int = 400
    codigo: str = "ERRO_DOMINIO"
    headers: dict[str, str] | None = None

    def __init__(self, mensagem: str, **extras: object) -> None:
        self.mensagem = mensagem
        self.extras = extras
        super().__init__(mensagem)

    def corpo(self) -> dict[str, object]:
        return {"detail": self.mensagem, "codigo": self.codigo, **self.extras}


# --- Autenticação e perfis ---


class CredencialJaCadastradaException(DomainException):
    status_code = 409
    codigo = "CREDENCIAL_JA_CADASTRADA"

    def __init__(self, credencial_institucional: str) -> None:
        self.credencial_institucional = credencial_institucional
        super().__init__(
            f"Credencial institucional '{credencial_institucional}' já cadastrada."
        )


class CredenciaisInvalidasException(DomainException):
    status_code = 401
    codigo = "CREDENCIAIS_INVALIDAS"

    def __init__(self) -> None:
        super().__init__("Credenciais inválidas.")


class TokenInvalidoException(DomainException):
    status_code = 401
    codigo = "TOKEN_INVALIDO"

    def __init__(self) -> None:
        super().__init__("Token inválido ou expirado.")
        self.headers = {"WWW-Authenticate": "Bearer"}


class PerfilInsuficienteException(DomainException):
    status_code = 403
    codigo = "PERFIL_INSUFICIENTE"

    def __init__(self) -> None:
        super().__init__("Perfil insuficiente para este recurso.")


# --- Sessão de geração ---


class ParametrosInconsistentesException(DomainException):
    status_code = 422
    codigo = "PARAMETROS_INCONSISTENTES"

    def __init__(self, p_f: int, p_m: int, p_d: int) -> None:
        soma = p_f + p_m + p_d
        super().__init__(
            f"pF + pM + pD deve somar exatamente 100%. "
            f"Recebido pF={p_f}, pM={p_m}, pD={p_d} — soma {soma}.",
            soma=soma,
        )


class SessaoNaoEncontradaException(DomainException):
    status_code = 404
    codigo = "SESSAO_NAO_ENCONTRADA"

    def __init__(self, sessao_id: int) -> None:
        super().__init__(f"Sessão {sessao_id} não encontrada.")


class SessaoEstadoInvalidaException(DomainException):
    status_code = 409
    codigo = "SESSAO_ESTADO_INVALIDO"

    def __init__(self, motivo: str) -> None:
        super().__init__(f"Operação não permitida no estado atual da sessão: {motivo}.")


class IndiceVazioException(DomainException):
    status_code = 409
    codigo = "INDICE_VAZIO"

    def __init__(self) -> None:
        super().__init__(
            "A sessão não tem nenhum material enviado — "
            "envie ao menos um antes de confirmar o índice."
        )


class IndiceNaoConfirmadoException(DomainException):
    status_code = 409
    codigo = "INDICE_NAO_CONFIRMADO"

    def __init__(self) -> None:
        super().__init__(
            "O índice de materiais ainda não foi confirmado pelo docente."
        )


# --- Materiais ---


class MaterialNaoEncontradoException(DomainException):
    status_code = 404
    codigo = "MATERIAL_NAO_ENCONTRADO"

    def __init__(self, material_id: int) -> None:
        super().__init__(f"Material {material_id} não encontrado nesta sessão.")


class MaterialDuplicadoException(DomainException):
    status_code = 409
    codigo = "MATERIAL_DUPLICADO"

    def __init__(self, identificador_curto: str) -> None:
        super().__init__(
            f"Este arquivo já foi enviado nesta sessão como {identificador_curto}.",
            identificador_curto=identificador_curto,
        )


class ArquivoMuitoGrandeException(DomainException):
    status_code = 413
    codigo = "ARQUIVO_MUITO_GRANDE"

    def __init__(self, max_mb: int) -> None:
        super().__init__(
            f"Arquivo acima do limite de {max_mb} MB por material.", max_mb=max_mb
        )


class FormatoNaoSuportadoException(DomainException):
    status_code = 415
    codigo = "FORMATO_NAO_SUPORTADO"

    def __init__(self, detectado: str) -> None:
        super().__init__(
            f"Formato não suportado: {detectado}. Aceitos: PDF, PPTX, DOCX, TXT.",
            detectado=detectado,
        )


class MaterialIlegivelException(DomainException):
    """Base dos casos do o arquivo chegou, mas não dá para extrair
    texto dele de forma confiável."""

    status_code = 422
    codigo = "MATERIAL_ILEGIVEL"

    def __init__(self, mensagem: str, motivo: str, **extras: object) -> None:
        super().__init__(mensagem, motivo=motivo, **extras)


class PdfProtegidoException(MaterialIlegivelException):
    codigo = "PDF_PROTEGIDO"

    def __init__(self, motivo: str) -> None:
        super().__init__(
            "PDF protegido: não é possível extrair o texto. "
            "Envie uma versão sem senha e com permissão de cópia.",
            motivo=motivo,
        )


class PdfEscaneadoOcrInsuficienteException(MaterialIlegivelException):
    codigo = "PDF_OCR_INSUFICIENTE"

    def __init__(self, paginas_afetadas: list[int], motivo: str) -> None:
        super().__init__(
            "Não foi possível extrair texto confiável deste PDF, nem com OCR. "
            "Envie uma versão com texto selecionável.",
            motivo=motivo,
            paginas_afetadas=paginas_afetadas,
        )


class ArquivoProtegidoException(MaterialIlegivelException):
    codigo = "ARQUIVO_PROTEGIDO"

    def __init__(self, formato: str) -> None:
        super().__init__(
            f"Arquivo {formato.upper()} protegido por senha.",
            motivo="arquivo protegido por senha",
        )


class ArquivoCorrompidoException(MaterialIlegivelException):
    codigo = "ARQUIVO_CORROMPIDO"

    def __init__(self, formato: str) -> None:
        super().__init__(
            f"Arquivo {formato.upper()} corrompido ou ilegível.",
            motivo="arquivo não pôde ser aberto",
        )


class MaterialSemTextoException(MaterialIlegivelException):
    codigo = "MATERIAL_SEM_TEXTO"

    def __init__(self, formato: str) -> None:
        super().__init__(
            f"O arquivo {formato.upper()} foi aberto, mas não contém texto útil.",
            motivo="nenhum texto extraível encontrado",
        )


# --- RAG ---


class FalhaEmbeddingException(DomainException):
    status_code = 502
    codigo = "FALHA_EMBEDDING"

    def __init__(self, motivo: str) -> None:
        super().__init__(f"Serviço de embedding indisponível: {motivo}.", motivo=motivo)


class FalhaRerankException(DomainException):
    status_code = 502
    codigo = "FALHA_RERANK"

    def __init__(self, motivo: str) -> None:
        super().__init__(
            f"Serviço de reordenação indisponível: {motivo}.", motivo=motivo
        )


class ConfiguracaoEmbeddingInvalidaException(DomainException):
    """Erro de configuração, não falha transitória: retentar não resolve."""

    status_code = 500
    codigo = "CONFIGURACAO_EMBEDDING_INVALIDA"

    def __init__(self, recebida: int, esperada: int) -> None:
        super().__init__(
            f"O modelo de embedding devolveu vetor de {recebida} dimensões, "
            f"mas o banco espera {esperada}. Verifique EMBEDDING_MODEL e "
            "embedding_dim — trocar de modelo exige reindexar.",
            recebida=recebida,
            esperada=esperada,
        )


class SessaoNaoIndexadaException(DomainException):
    status_code = 409
    codigo = "SESSAO_NAO_INDEXADA"

    def __init__(self) -> None:
        super().__init__(
            "A sessão foi confirmada mas não tem nenhum trecho indexado. "
            "Isso ocorre em sessões confirmadas antes do pipeline de RAG existir."
        )


class ArtefatoDeTextoInvalidoException(DomainException):
    status_code = 500
    codigo = "ARTEFATO_TEXTO_INVALIDO"

    def __init__(self, identificador_curto: str) -> None:
        super().__init__(
            f"O artefato de texto extraído do material {identificador_curto} "
            "está ausente ou corrompido — reenvie o material.",
            identificador_curto=identificador_curto,
        )


# --- Provedor de LLM ---


class FalhaTransporteLLMException(DomainException):
    """Interna à camada: `ProvedorLLMService` a consome como motivo de
    retentativa e nunca a deixa chegar ao handler HTTP. O status existe só
    para satisfazer o contrato de `DomainException`."""

    status_code = 503
    codigo = "FALHA_TRANSPORTE_LLM"

    def __init__(self, motivo: str) -> None:
        super().__init__(f"Falha ao falar com o provedor: {motivo}.", motivo=motivo)


class FalhaProvedorLLMException(DomainException):
    """a cadeia inteira falhou. Carrega o motivo de cada provedor —
    sem isso, diagnosticar exige ler log do servidor."""

    status_code = 503
    codigo = "FALHA_PROVEDOR_LLM"

    def __init__(self, motivos: list[tuple[str, str]]) -> None:
        detalhe = "; ".join(f"{nome}: {motivo}" for nome, motivo in motivos)
        super().__init__(
            f"Nenhum provedor de LLM respondeu. Tentados — {detalhe}.",
            provedores=[{"provedor": n, "motivo": m} for n, m in motivos],
        )


class RespostaLLMInvalidaException(DomainException):
    """O provedor respondeu: o problema é o conteúdo, não a disponibilidade.
    Por isso 502, e por isso NÃO dispara fallback — trocar de modelo não
    conserta prompt ruim."""

    status_code = 502
    codigo = "RESPOSTA_LLM_INVALIDA"

    def __init__(self, motivo: str) -> None:
        super().__init__(
            f"O provedor respondeu fora do formato esperado: {motivo}.",
            motivo=motivo,
        )


class NenhumProvedorAtivoException(DomainException):
    status_code = 500
    codigo = "NENHUM_PROVEDOR_ATIVO"

    def __init__(self) -> None:
        super().__init__(
            "Nenhum provedor de LLM ativo cadastrado — verifique a tabela "
            "provedores_llm."
        )


# --- Prompt Mestre ---


class PlaceholderNaoResolvidoException(DomainException):
    """Prompt entregue ao modelo com `{{tema}}` literal é falha silenciosa de
    qualidade: o modelo não reclama, só gera pior. Falhar alto é obrigatório."""

    status_code = 500
    codigo = "PLACEHOLDER_NAO_RESOLVIDO"

    def __init__(self, placeholders: list[str]) -> None:
        nomes = ", ".join(placeholders)
        super().__init__(
            f"O prompt mestre foi montado com placeholders não resolvidos: "
            f"{nomes}. Verifique ParametrosGeracao e os módulos em "
            "backend/app/prompt/.",
            placeholders=placeholders,
        )


class VersaoPromptDuplicadaException(DomainException):
    status_code = 409
    codigo = "VERSAO_PROMPT_DUPLICADA"

    def __init__(self, versao: str) -> None:
        super().__init__(
            f"Já existe uma versão {versao} do prompt mestre.", versao=versao
        )


class NenhumPromptAtivoException(DomainException):
    status_code = 409
    codigo = "NENHUM_PROMPT_ATIVO"

    def __init__(self) -> None:
        super().__init__(
            "Nenhuma versão do prompt mestre está ativa — ative uma antes de "
            "gerar questões."
        )


class VersaoPromptNaoEncontradaException(DomainException):
    status_code = 404
    codigo = "VERSAO_PROMPT_NAO_ENCONTRADA"

    def __init__(self, versao: str) -> None:
        super().__init__(
            f"Versão {versao} do prompt mestre não encontrada.", versao=versao
        )


class PromptDivergenteException(DomainException):
    """Os módulos em disco mudaram sem que uma versão nova fosse registrada.
    Sem isso, `PromptMestre.conteudo` descreveria algo que não é mais o que
    seria enviado, e a auditoria passaria a mentir."""

    status_code = 409
    codigo = "PROMPT_DIVERGENTE"

    def __init__(self, gravado: str, em_disco: str) -> None:
        super().__init__(
            "Os módulos do prompt em disco divergem da versão ativa registrada. "
            "Registre uma versão nova antes de continuar.",
            hash_gravado=gravado,
            hash_em_disco=em_disco,
        )


# --- Agente Gerador ---


class MaterialInsuficienteParaBancoException(DomainException):
    """Levantada antes da primeira chamada ao modelo: descobrir isso no
    minuto 7 desperdiçaria minutos de GPU."""

    status_code = 409
    codigo = "MATERIAL_INSUFICIENTE_PARA_BANCO"

    def __init__(self, chunks: int, pedidos: int) -> None:
        super().__init__(
            f"A sessão tem {chunks} trechos indexados, insuficientes para "
            f"{pedidos} questões — cada questão nasce de um trecho distinto. "
            "Envie mais material ou reduza o tamanho do banco.",
            chunks_disponiveis=chunks,
            questoes_pedidas=pedidos,
        )


class BancoCongeladoException(DomainException):
    """depois da janela de exclusões o banco é congelado."""

    status_code = 409
    codigo = "BANCO_CONGELADO"

    def __init__(self, versao: str) -> None:
        super().__init__(
            f"O banco {versao} está congelado e não aceita novas questões.",
            versao=versao,
        )


class ParametrosBancoDivergentesException(DomainException):
    """As contagens por tipo ficam fixas na criação do banco.
    Mudá-las na retomada deslocaria quais números são objetivos e quais são
    discursivos, e recalcularia as âncoras com outro espaçamento."""

    status_code = 409
    codigo = "PARAMETROS_BANCO_DIVERGENTES"

    def __init__(
        self, versao: str, gravado: tuple[int, int], pedido: tuple[int, int]
    ) -> None:
        super().__init__(
            f"O banco {versao} foi criado com {gravado[0]} objetivas e "
            f"{gravado[1]} discursivas; a retomada pediu {pedido[0]} e "
            f"{pedido[1]}. Retome com as mesmas contagens ou crie outra versão.",
            versao=versao,
            gravado={"objetivas": gravado[0], "discursivas": gravado[1]},
            pedido={"objetivas": pedido[0], "discursivas": pedido[1]},
        )


class FonteInvalidaException(DomainException):
    """O modelo citou material que não estava entre os trechos enviados. Sem
    esta checagem a rastreabilidade seria ficção."""

    status_code = 502
    codigo = "FONTE_INVALIDA"

    def __init__(self, identificador: str, disponiveis: list[str]) -> None:
        super().__init__(
            f"O modelo citou o material {identificador}, que não estava entre "
            f"os trechos fornecidos ({', '.join(disponiveis)}).",
            identificador=identificador,
            disponiveis=disponiveis,
        )
