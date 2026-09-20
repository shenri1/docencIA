from backend.app.domain import OrigemTexto
from backend.app.exceptions import MaterialSemTextoException
from backend.app.services.extracao.tipos import BlocoTexto, ResultadoExtracao

_CODIFICACOES = ("utf-8", "utf-8-sig", "cp1252")


def decodificar(dados: bytes) -> str:
    if b"\x00" in dados:
        raise MaterialSemTextoException("txt")
    for codificacao in _CODIFICACOES:
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise MaterialSemTextoException("txt")


def extrair_txt(dados: bytes) -> ResultadoExtracao:
    texto = decodificar(dados)
    linhas = texto.splitlines()
    blocos: list[BlocoTexto] = []
    inicio: int | None = None
    acumulado: list[str] = []

    def fechar(fim: int) -> None:
        if inicio is None:
            return
        conteudo = "\n".join(acumulado).strip()
        if conteudo:
            blocos.append(
                BlocoTexto(
                    localizacao=f"linhas {inicio}–{fim}",
                    texto=conteudo,
                    origem=OrigemTexto.NATIVO,
                )
            )

    for numero, linha in enumerate(linhas, start=1):
        if linha.strip():
            if inicio is None:
                inicio = numero
            acumulado.append(linha)
        else:
            fechar(numero - 1)
            inicio, acumulado = None, []
    fechar(len(linhas))

    if not blocos:
        raise MaterialSemTextoException("txt")
    return ResultadoExtracao(blocos, None, OrigemTexto.NATIVO)
