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

    def __init__(self, motivo: str = "assinatura_invalida") -> None:
        super().__init__("Token inválido ou expirado.")
        self.headers = {"WWW-Authenticate": "Bearer"}
        # Fora de `extras` de propósito: vai para o log, nunca para
        # o corpo da resposta. O cliente não aprende por que foi recusado.
        self.motivo = motivo


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


class ArquivoDescompressaoExcessivaException(DomainException):
    """O arquivo comprimido respeita MAX_UPLOAD_MB, mas o conteúdo declarado
    descomprimido não: barra zip bomb antes de o parser abrir o pacote."""

    status_code = 413
    codigo = "ARQUIVO_DESCOMPRESSAO_EXCESSIVA"

    def __init__(self, formato: str, motivo: str) -> None:
        super().__init__(
            f"Arquivo {formato.upper()} recusado: {motivo}.", motivo=motivo
        )


class PdfMuitoLongoException(DomainException):
    """Diferente de PdfEscaneadoOcrInsuficiente ("precisa de texto
    selecionável"): aqui o PDF é grande demais para ser processado."""

    status_code = 413
    codigo = "PDF_MUITO_LONGO"

    def __init__(self, paginas: int, max_paginas: int) -> None:
        super().__init__(
            f"PDF com {paginas} páginas; o limite é {max_paginas} por material. "
            "Divida o arquivo em partes menores.",
            paginas=paginas,
            max_paginas=max_paginas,
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
    """Base dos casos de material ilegível: o arquivo chegou, mas não dá para extrair
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
    """A cadeia inteira falhou. Carrega o motivo de cada provedor —
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
    """Depois da janela de exclusões o banco é congelado."""

    status_code = 409
    codigo = "BANCO_CONGELADO"

    def __init__(self, versao: str) -> None:
        super().__init__(
            f"O banco {versao} está congelado e não aceita novas questões.",
            versao=versao,
        )


class ServidorOcupadoException(DomainException):
    """Todas as vagas de chamada ao LLM estão em uso. Recusar na hora preserva
    as threads da API para login, health e leituras."""

    status_code = 503
    codigo = "SERVIDOR_OCUPADO"

    def __init__(self, retry_after_s: int) -> None:
        super().__init__(
            "O servidor está processando o máximo de gerações simultâneas. "
            "Tente de novo em instantes.",
            retry_after_s=retry_after_s,
        )
        self.headers = {"Retry-After": str(retry_after_s)}


class GeracaoEmAndamentoException(DomainException):
    """Outra requisição gravou a questão que esta acabou de gerar. Acontece no
    retry de um cliente cujo timeout venceu antes de a primeira requisição
    terminar. Nada se perde: o que a outra gravou fica, e chamar de novo
    continua de onde parou."""

    status_code = 409
    codigo = "GERACAO_EM_ANDAMENTO"

    def __init__(self, versao: str, numero: int) -> None:
        super().__init__(
            f"Outra requisição já gravou a questão {numero} do banco {versao}: "
            "há uma geração em andamento para ele. Aguarde-a terminar e, se "
            "faltar questão, chame de novo — a geração continua de onde parou.",
            versao=versao,
            numero=numero,
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


class FonteNaoSustentadaException(DomainException):
    """O material citado existe, mas o trecho-base que o modelo informou não
    consta nele. Sem trecho claro no material, a questão não é gerada: a fonte
    é o que o docente usa para conferir a questão."""

    status_code = 502
    codigo = "FONTE_NAO_SUSTENTADA"

    def __init__(self, identificador: str, trecho_base: str) -> None:
        resumo = trecho_base if len(trecho_base) <= 80 else trecho_base[:77] + "..."
        super().__init__(
            f"O modelo citou o material {identificador}, mas o trecho-base não "
            f"consta nele: «{resumo}».",
            identificador=identificador,
        )


# --- Controle do Banco ---


class BancoNaoEncontradoException(DomainException):
    """Banco de outro docente responde 404, não 403: não revela existência."""

    status_code = 404
    codigo = "BANCO_NAO_ENCONTRADO"

    def __init__(self, banco_id: int) -> None:
        super().__init__(f"Banco {banco_id} não encontrado.", banco_id=banco_id)


class QuestaoNaoEncontradaException(DomainException):
    status_code = 404
    codigo = "QUESTAO_NAO_ENCONTRADA"

    def __init__(self, numero: int) -> None:
        super().__init__(f"O banco não tem questão de número {numero}.", numero=numero)


class RevisaoDesatualizadaException(DomainException):
    """Human-in-the-loop: o comando vale sobre o banco que o docente viu. Sem
    isto, "excluir Q5" poderia valer sobre um Q5 que ele nunca leu."""

    status_code = 409
    codigo = "REVISAO_DESATUALIZADA"

    def __init__(self, atual: int, esperada: int) -> None:
        super().__init__(
            f"O banco está na revisão {atual} e o comando esperava a {esperada}. "
            "Leia o banco de novo antes de decidir.",
            revisao_atual=atual,
            revisao_esperada=esperada,
        )


class JanelaExclusoesFechadaException(DomainException):
    """O congelamento fecha a janela de exclusões. Substituição
    com comando explícito continua permitida — é a exceção que abre."""

    status_code = 409
    codigo = "JANELA_EXCLUSOES_FECHADA"

    def __init__(self, versao: str) -> None:
        super().__init__(
            f"O banco {versao} está congelado: a janela de exclusões fechou. "
            "Substituir uma questão específica continua possível.",
            versao=versao,
        )


class NumerosInvalidosException(DomainException):
    """Tudo-ou-nada: aplicar metade da lista deixaria o docente num estado que
    ele não pediu."""

    status_code = 422
    codigo = "NUMEROS_INVALIDOS"

    def __init__(self, invalidos: list[dict[str, object]]) -> None:
        numeros = ", ".join(str(item["numero"]) for item in invalidos)
        super().__init__(
            f"Nenhuma exclusão foi aplicada: {numeros} não pode(m) ser excluído(s).",
            invalidos=invalidos,
        )


class BancoVazioException(DomainException):
    status_code = 409
    codigo = "BANCO_VAZIO"

    def __init__(self, versao: str) -> None:
        super().__init__(
            f"O banco {versao} não tem nenhuma questão ativa para congelar.",
            versao=versao,
        )


class CandidataPendenteException(DomainException):
    status_code = 409
    codigo = "CANDIDATA_PENDENTE"

    def __init__(self, numero: int) -> None:
        super().__init__(
            f"A questão {numero} já tem uma candidata pendente. Aceite ou "
            "rejeite antes de propor outra.",
            numero=numero,
        )


class SemCandidataPendenteException(DomainException):
    status_code = 409
    codigo = "SEM_CANDIDATA_PENDENTE"

    def __init__(self, numero: int) -> None:
        super().__init__(
            f"A questão {numero} não tem candidata pendente.", numero=numero
        )


class EstadoQuestaoInvalidoException(DomainException):
    status_code = 409
    codigo = "ESTADO_QUESTAO_INVALIDO"

    def __init__(self, numero: int, estado: str) -> None:
        super().__init__(
            f"A questão {numero} está {estado} e não pode ser substituída. Só "
            "questão ativa ou excluída aceita substituição.",
            numero=numero,
            estado=estado,
        )


class InconsistenciaDeEstadoException(DomainException):
    """NÃO é bug: é o sistema se recusando a entregar estado
    incoerente. Bloqueia leitura e congelamento, e nas 14 vai
    bloquear provas, gabaritos e exportação."""

    status_code = 409
    codigo = "INCONSISTENCIA_DE_ESTADO"

    def __init__(self, problemas: list[str]) -> None:
        super().__init__(
            f"O banco está em estado incoerente ({len(problemas)} problema(s)) e "
            "não pode ser entregue.",
            problemas=problemas,
        )


# --- Montagem de Provas A/B ---


class ProvaNaoEncontradaException(DomainException):
    """Prova de outro docente responde 404, não 403 — mesma regra de banco e
    sessão: não revela existência."""

    status_code = 404
    codigo = "PROVA_NAO_ENCONTRADA"

    def __init__(self, prova_id: int) -> None:
        super().__init__(f"Prova {prova_id} não encontrada.", prova_id=prova_id)


class ProvasNaoMontadasException(DomainException):
    """Frontend ler as provas de um banco que ainda não as tem. Não usa
    `ProvaNaoEncontradaException`, que identifica uma prova por id — aqui não
    existe id nenhum."""

    status_code = 404
    codigo = "PROVAS_NAO_MONTADAS"

    def __init__(self, versao: str) -> None:
        super().__init__(
            f"O banco {versao} ainda não tem provas montadas.", versao=versao
        )


class BancoNaoCongeladoException(DomainException):
    """Montar sobre banco aberto deixaria uma exclusão invalidar em silêncio uma
    prova já impressa."""

    status_code = 409
    codigo = "BANCO_NAO_CONGELADO"

    def __init__(self, versao: str) -> None:
        super().__init__(
            f"O banco {versao} não está congelado. Congele antes de montar as "
            "provas: depois disso, exclusões ficam vetadas e a prova tem base fixa.",
            versao=versao,
        )


class ProvasJaMontadasException(DomainException):
    status_code = 409
    codigo = "PROVAS_JA_MONTADAS"

    def __init__(self, versoes: list[str]) -> None:
        super().__init__(
            f"A sessão já tem prova nas versões {', '.join(versoes)}. Remontar "
            "não é suportado.",
            versoes=versoes,
        )


class SubstituicaoAposMontagemException(DomainException):
    """Aceitar a substituição moveria a revisão do banco depois de as provas
    serem montadas: elas ficariam desatualizadas, a exportação bloquearia para
    sempre (remontar está fora do escopo) e o DOCX já entregue deixaria de
    corresponder ao banco. O fluxo que funciona é substituir antes de montar."""

    status_code = 409
    codigo = "SUBSTITUICAO_APOS_MONTAGEM"

    def __init__(self, versoes: list[str]) -> None:
        super().__init__(
            f"As provas {', '.join(versoes)} já foram montadas sobre este banco; "
            "aceitar a substituição as deixaria desatualizadas e remontar não é "
            "suportado. Substitua antes de montar as provas.",
            versoes=versoes,
        )


class BancoInsuficienteParaProvaException(DomainException):
    """Não é bug: é o banco não sustentando duas provas com a distribuição
    pedida. O docente decide entre prova menor, outro pF/pM/pD, ou substituir
    questões para reequilibrar."""

    status_code = 409
    codigo = "BANCO_INSUFICIENTE_PARA_PROVA"

    def __init__(
        self,
        cotas: dict[str, int],
        pedido_por_tipo: dict[str, int],
        disponivel_por_celula: dict[str, int],
    ) -> None:
        super().__init__(
            "O banco não sustenta duas provas com essa distribuição. Reduza N, "
            "mude pF/pM/pD, ou substitua questões para reequilibrar as faixas.",
            cotas_por_faixa=cotas,
            pedido_por_tipo=pedido_por_tipo,
            disponivel_por_celula=disponivel_por_celula,
        )


class SobreposicaoInevitavelException(DomainException):
    """No máximo 2 questões com o mesmo subtema nas duas provas."""

    status_code = 409
    codigo = "SOBREPOSICAO_INEVITAVEL"

    def __init__(
        self,
        subtema: str,
        quantas: int,
        limite: int,
        dica: str = "Reduza N ou substitua questões desse subtema.",
    ) -> None:
        super().__init__(
            f'O subtema "{subtema}" ficaria com {quantas} questões nas duas '
            f"provas, acima do limite de {limite}. {dica}",
            subtema=subtema,
            quantas=quantas,
            limite=limite,
        )


class QuestoesIndisponiveisException(DomainException):
    """O docente escolheu número que não é questão ativa do banco: não existe,
    foi excluída ou substituída. O que está na tela é velho."""

    status_code = 409
    codigo = "QUESTOES_INDISPONIVEIS"

    def __init__(self, numeros: list[int]) -> None:
        super().__init__(
            "Estas questões não estão ativas no banco: "
            f"{', '.join(map(str, numeros))}. Recarregue a lista e escolha de novo.",
            numeros=numeros,
        )


class PlanoDeLetrasImpossivelException(DomainException):
    """Erro de programação, não do docente: medido, o pior caso precisa de 616
    tentativas e o teto é 2000. Chegar aqui significa que um filtro mudou."""

    status_code = 500
    codigo = "PLANO_DE_LETRAS_IMPOSSIVEL"

    def __init__(self, n_posicoes: int, k: int, tentativas: int) -> None:
        super().__init__(
            f"Não foi possível planejar as letras de {n_posicoes} posições com "
            f"K={k} em {tentativas} tentativas.",
            n_posicoes=n_posicoes,
            k=k,
            tentativas=tentativas,
        )


class MontagemInconsistenteException(DomainException):
    """A verificação recusou o que a própria montagem acabou de gravar. Bug do
    sistema, e devolver 4xx faria o docente procurar erro no que ele pediu."""

    status_code = 500
    codigo = "MONTAGEM_INCONSISTENTE"

    def __init__(self, violacoes: list[str]) -> None:
        super().__init__(
            f"A montagem produziu estado que a verificação recusa "
            f"({len(violacoes)} violação(ões)).",
            violacoes=violacoes,
        )


# --- Exportação DOCX ---


class ExportacaoNaoEncontradaException(DomainException):
    """Exportação de outro docente responde 404, não 403 — não revela
    existência."""

    status_code = 404
    codigo = "EXPORTACAO_NAO_ENCONTRADA"

    def __init__(self, exportacao_id: int) -> None:
        super().__init__(
            f"Exportação {exportacao_id} não encontrada.", exportacao_id=exportacao_id
        )


class ArquivoExportadoCorrompidoException(DomainException):
    """O arquivo no armazenamento não é o que o registro diz ter saído. Problema
    de infraestrutura, não do docente — e entregá-lo seria entregar algo que o
    sistema não emitiu."""

    status_code = 500
    codigo = "ARQUIVO_EXPORTADO_CORROMPIDO"

    def __init__(self, exportacao_id: int) -> None:
        super().__init__(
            f"O arquivo da exportação {exportacao_id} não confere com o hash "
            "registrado e não será entregue.",
            exportacao_id=exportacao_id,
        )


# --- Agente Orquestrador ---


class ComandoForaDoMarcoException(DomainException):
    """Não é bug: o comando não vale no marco em que a sessão ou o banco está.
    A resposta diz quais valem — e, em BLOQUEADO, por quê."""

    status_code = 409
    codigo = "COMANDO_FORA_DO_MARCO"

    def __init__(
        self, marco: str, aceitos: list[str], motivo: str | None = None
    ) -> None:
        mensagem = (
            f"O comando não vale no marco {marco}. Aceitos agora: "
            f"{', '.join(aceitos) or 'nenhum'}."
        )
        if motivo:
            mensagem += f" {motivo}"
        super().__init__(mensagem, marco=marco, comandos_aceitos=aceitos, motivo=motivo)


class CamposDoMarcoException(DomainException):
    """O `prosseguir` aceita exatamente os campos do marco atual. A sobra também
    é recusada: um pedido de montagem reenviado com o banco aberto congelaria o
    banco, e congelar é irreversível."""

    status_code = 422
    codigo = "CAMPOS_DO_MARCO"

    def __init__(
        self,
        marco: str,
        esperados: list[str],
        faltando: list[str],
        sobrando: list[str],
    ) -> None:
        super().__init__(
            f"No marco {marco}, prosseguir leva exatamente: "
            f"{', '.join(esperados) or 'nenhum campo'}.",
            marco=marco,
            campos_esperados=esperados,
            faltando=faltando,
            sobrando=sobrando,
        )


# --- Orientações do docente ---


class OrientacaoNaoEncontradaException(DomainException):
    status_code = 404
    codigo = "ORIENTACAO_NAO_ENCONTRADA"

    def __init__(self, orientacao_id: int) -> None:
        super().__init__(
            f"Orientação {orientacao_id} não encontrada.", orientacao_id=orientacao_id
        )


class LimiteOrientacoesException(DomainException):
    """Cada "articular com" é uma busca a mais em toda questão, e cada
    orientação soma linhas a um pedido que já carrega os trechos."""

    status_code = 409
    codigo = "LIMITE_ORIENTACOES"

    def __init__(
        self, ativas: int, com_cruzamento: int, teto_ativas: int, teto_cruzamentos: int
    ) -> None:
        super().__init__(
            f"A sessão já tem {ativas} orientações ativas, {com_cruzamento} com "
            f"articulação. O limite é {teto_ativas}, das quais {teto_cruzamentos} "
            "com articulação. Desative uma antes de acrescentar outra.",
            ativas=ativas,
            com_cruzamento=com_cruzamento,
            teto_ativas=teto_ativas,
            teto_cruzamentos=teto_cruzamentos,
        )


class EstadoOrientacaoInvalidoException(DomainException):
    status_code = 409
    codigo = "ESTADO_ORIENTACAO_INVALIDO"

    def __init__(self, orientacao_id: int) -> None:
        super().__init__(
            f"A orientação {orientacao_id} valeu só para a variação que a pediu e "
            "não pode ser desativada.",
            orientacao_id=orientacao_id,
        )
