"""Armazenamento de arquivos enviados pelo docente.

O resto do sistema depende só do Protocol e da *chave lógica*
(`{docente_id}/{sessao_id}/{uuid}.{ext}`), nunca de um caminho de disco — é
isso que permite trocar o backend por S3/MinIO sem tocar em banco nem em
service."""

import os
import tempfile
from pathlib import Path
from typing import Protocol

from backend.app.core.config import settings


class ArmazenamentoArquivos(Protocol):
    def salvar(self, chave: str, dados: bytes) -> int: ...
    def abrir(self, chave: str) -> bytes: ...
    def remover(self, chave: str) -> None: ...
    def existe(self, chave: str) -> bool: ...


def montar_chave(docente_id: int, sessao_id: int, nome_uuid: str) -> str:
    return f"{docente_id}/{sessao_id}/{nome_uuid}"


class ArmazenamentoLocal:
    def __init__(self, raiz: Path | str) -> None:
        self.raiz = Path(raiz).resolve()
        self.raiz.mkdir(parents=True, exist_ok=True)

    def _resolver(self, chave: str) -> Path:
        destino = (self.raiz / chave).resolve()
        # Defesa em profundidade: as chaves são geradas com UUID pelo servidor,
        # mas um caminho que escape da raiz nunca pode ser escrito.
        if not destino.is_relative_to(self.raiz):
            raise ValueError(f"Chave fora da raiz de armazenamento: {chave}")
        return destino

    def salvar(self, chave: str, dados: bytes) -> int:
        destino = self._resolver(chave)
        destino.parent.mkdir(parents=True, exist_ok=True)
        # Escrita atômica: um upload interrompido não deixa arquivo parcial.
        descritor, temporario = tempfile.mkstemp(dir=destino.parent)
        try:
            with os.fdopen(descritor, "wb") as saida:
                saida.write(dados)
            os.replace(temporario, destino)
        except BaseException:
            Path(temporario).unlink(missing_ok=True)
            raise
        return len(dados)

    def abrir(self, chave: str) -> bytes:
        return self._resolver(chave).read_bytes()

    def remover(self, chave: str) -> None:
        self._resolver(chave).unlink(missing_ok=True)

    def existe(self, chave: str) -> bool:
        return self._resolver(chave).is_file()


def get_armazenamento() -> ArmazenamentoArquivos:
    return ArmazenamentoLocal(settings.storage_dir)
