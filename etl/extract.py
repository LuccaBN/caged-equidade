"""Extração: baixa os arquivos do Novo CAGED do FTP do MTE e descompacta.

Estrutura do FTP:
    /pdet/microdados/NOVO CAGED/<ANO>/<AAAAMM>/CAGEDMOV<AAAAMM>.7z
    /pdet/microdados/NOVO CAGED/<ANO>/<AAAAMM>/CAGEDFOR<AAAAMM>.7z
    /pdet/microdados/NOVO CAGED/<ANO>/<AAAAMM>/CAGEDEXC<AAAAMM>.7z
    /pdet/microdados/NOVO CAGED/Layout Não-identificado Novo Caged Movimentação.xlsx
"""
from ftplib import FTP
from pathlib import Path
import logging

import py7zr

from config import DIR_RAW, FTP_HOST, FTP_DIR_BASE, TIPOS_ARQUIVO, ARQ_LAYOUT

log = logging.getLogger(__name__)


def _baixar(ftp: FTP, remoto: str, local: Path) -> None:
    local.parent.mkdir(parents=True, exist_ok=True)
    log.info("Baixando %s", remoto)
    with open(local, "wb") as f:
        ftp.retrbinary(f"RETR {remoto}", f.write)


def _descompactar(arquivo_7z: Path) -> Path:
    destino = arquivo_7z.with_suffix("")  # pasta com o mesmo nome
    txt = destino / (arquivo_7z.stem + ".txt")
    if txt.exists():
        return txt
    log.info("Descompactando %s", arquivo_7z.name)
    with py7zr.SevenZipFile(arquivo_7z, "r") as z:
        z.extractall(destino)
    return txt


def caminho_txt(tipo: str, competencia: str) -> Path:
    """Caminho esperado do .txt descompactado (ex.: data/raw/CAGEDMOV202608/CAGEDMOV202608.txt)."""
    nome = f"CAGED{tipo}{competencia}"
    return DIR_RAW / nome / f"{nome}.txt"


def obter_competencia(competencia: str, baixar: bool = True) -> dict:
    """Garante que os 3 arquivos de uma competência estejam disponíveis localmente.

    Se `baixar` for False, apenas usa o que já estiver em data/raw
    (útil quando o FTP estiver fora do ar ou o arquivo já foi baixado à mão).
    Retorna {tipo: caminho_do_txt}.
    """
    arquivos = {}
    ftp = None
    try:
        for tipo in TIPOS_ARQUIVO:
            txt = caminho_txt(tipo, competencia)
            if txt.exists():
                arquivos[tipo] = txt
                continue
            arq_7z = DIR_RAW / f"CAGED{tipo}{competencia}.7z"
            if not arq_7z.exists():
                if not baixar:
                    log.warning("Arquivo %s não encontrado e download desativado", arq_7z.name)
                    continue
                if ftp is None:
                    ftp = FTP(FTP_HOST, timeout=120, encoding="latin-1")
                    ftp.login()  # acesso anônimo
                remoto = f"{FTP_DIR_BASE}/{competencia[:4]}/{competencia}/{arq_7z.name}"
                _baixar(ftp, remoto, arq_7z)
            arquivos[tipo] = _descompactar(arq_7z)

        if not ARQ_LAYOUT.exists() and baixar:
            if ftp is None:
                ftp = FTP(FTP_HOST, timeout=120, encoding="latin-1")
                ftp.login()
            _baixar(ftp, f"{FTP_DIR_BASE}/{ARQ_LAYOUT.name}", ARQ_LAYOUT)
    finally:
        if ftp is not None:
            ftp.quit()
    return arquivos
