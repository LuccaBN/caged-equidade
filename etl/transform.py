"""Transformação: limpeza, tipagem, regras de qualidade e agregação.

Cada decisão está comentada no ponto em que é aplicada. O resumo das
decisões e suas justificativas está em docs/DECISOES.md.
"""
from collections import Counter
from pathlib import Path
import logging

import numpy as np
import pandas as pd

from config import (
    CHUNK_SIZE, COLUNAS_USADAS, FAIXAS_ETARIAS, PESO_ARQUIVO,
    SALARIO_MINIMO, SALARIO_MIN_FATOR, SALARIO_MAX_FATOR,
    UNIDADE_SALARIO_MENSAL, SEMANAS_POR_MES, UF_DETALHE,
)

log = logging.getLogger(__name__)

# Nomes padronizados (snake_case, sem acento) para as colunas do banco
RENOMEAR = {
    "competênciamov": "competencia",
    "região": "cod_regiao",
    "uf": "cod_uf",
    "município": "cod_municipio",
    "seção": "cod_secao",
    "saldomovimentação": "saldo",
    "cbo2002ocupação": "cod_cbo",
    "graudeinstrução": "cod_instrucao",
    "idade": "idade",
    "horascontratuais": "horas_contratuais",
    "raçacor": "cod_raca_cor",
    "sexo": "cod_sexo",
    "tipomovimentação": "cod_tipo_mov",
    "indtrabintermitente": "fl_intermitente",
    "indtrabparcial": "fl_parcial",
    "salário": "salario",
    "indicadoraprendiz": "fl_aprendiz",
    "unidadesaláriocódigo": "cod_unidade_salario",
}


def _decimal(serie: pd.Series) -> pd.Series:
    """Converte texto com vírgula decimal ("2010,00") para número."""
    return pd.to_numeric(serie.str.replace(",", ".", regex=False), errors="coerce")


def _inteiro(serie: pd.Series, tipo="Int16") -> pd.Series:
    return pd.to_numeric(serie, errors="coerce").astype(tipo)


def faixa_etaria(idade: pd.Series) -> pd.Series:
    """Converte idade exata em faixa etária (LGPD: a idade exata não é gravada)."""
    faixa = pd.Series(9, index=idade.index, dtype="int8")  # 9 = Não informado
    for fid, _, ini, fim in FAIXAS_ETARIAS:
        if ini is None:
            continue
        faixa[(idade >= ini) & (idade <= fim)] = fid
    return faixa


def limpar_bloco(bloco: pd.DataFrame, tipo_arquivo: str, stats: Counter) -> pd.DataFrame:
    """Aplica padronização, tipagem e regras de qualidade a um bloco de linhas."""
    df = bloco.rename(columns=RENOMEAR)
    stats["linhas_lidas"] += len(df)

    out = pd.DataFrame(index=df.index)
    out["competencia"] = _inteiro(df["competencia"], "int32")
    out["cod_regiao"] = _inteiro(df["cod_regiao"], "int16")
    out["cod_uf"] = _inteiro(df["cod_uf"], "int16")
    # Códigos são identificadores, não números: ficam como texto e recuperam
    # os zeros à esquerda que se perdem no arquivo (ex.: CBO 10105 -> 010105).
    out["cod_municipio"] = df["cod_municipio"].str.strip().str.zfill(6)
    out["cod_secao"] = df["cod_secao"].str.strip().str.upper()
    out["cod_cbo"] = df["cod_cbo"].str.strip().str.zfill(6)
    out["cod_instrucao"] = _inteiro(df["cod_instrucao"], "int16")
    out["cod_raca_cor"] = _inteiro(df["cod_raca_cor"], "int16")
    out["cod_sexo"] = _inteiro(df["cod_sexo"], "int16")
    out["cod_tipo_mov"] = _inteiro(df["cod_tipo_mov"], "int16")
    out["saldo"] = _inteiro(df["saldo"], "int8")

    # Peso do registro: MOV e FOR somam (+1); EXC são cancelamentos (-1)
    out["peso"] = np.int8(PESO_ARQUIVO[tipo_arquivo])
    out["origem"] = tipo_arquivo

    # Idade: nulos viram faixa "Não informado"
    idade = pd.to_numeric(df["idade"], errors="coerce")
    stats["idade_nula"] += int(idade.isna().sum())
    out["id_faixa_etaria"] = faixa_etaria(idade)

    horas = _decimal(df["horas_contratuais"])
    horas = horas.where(horas > 0)  # 0 ou negativo não é jornada válida
    out["horas_contratuais"] = horas.round(2)

    # Indicadores 0/1 -> booleano
    for col in ("fl_intermitente", "fl_parcial", "fl_aprendiz"):
        out[col] = df[col].str.strip() == "1"

    # ---------------- Regras do salário ----------------
    salario = _decimal(df["salario"])
    unidade = _inteiro(df["cod_unidade_salario"], "Int16")
    ano = out["competencia"] // 100
    sm = ano.map(SALARIO_MINIMO).fillna(max(SALARIO_MINIMO.values()))
    mensal = unidade == UNIDADE_SALARIO_MENSAL
    zerado = salario.isna() | (salario <= 0)
    fora_faixa = ~zerado & ((salario < SALARIO_MIN_FATOR * sm) | (salario > SALARIO_MAX_FATOR * sm))
    valido = mensal.fillna(False) & ~zerado & ~fora_faixa

    stats["salario_zerado"] += int(zerado.sum())
    stats["salario_nao_mensal"] += int((~mensal.fillna(False) & ~zerado).sum())
    stats["salario_fora_faixa"] += int((mensal.fillna(False) & fora_faixa).sum())
    stats["salario_valido"] += int(valido.sum())

    # O registro não é apagado: só o valor do salário fica nulo, para que a
    # linha continue contando nas admissões e desligamentos.
    out["fl_salario_valido"] = valido.astype(bool)
    out["salario"] = salario.where(valido).round(2)
    out["salario_hora"] = (out["salario"] / (out["horas_contratuais"] * SEMANAS_POR_MES)).round(2)
    return out


def ler_arquivo(caminho: Path, tipo_arquivo: str, competencias: set, stats: Counter) -> pd.DataFrame:
    """Lê um arquivo do CAGED em blocos e devolve só as linhas da janela de análise.

    competencias: conjunto de AAAAMM aceitos (recorte temporal). Linhas de FOR/EXC
    referentes a meses fora da janela são descartadas.
    """
    log.info("Lendo %s", caminho.name)
    partes = []
    leitor = pd.read_csv(
        caminho, sep=";", dtype=str, usecols=COLUNAS_USADAS,
        chunksize=CHUNK_SIZE, encoding="utf-8",
    )
    for bloco in leitor:
        limpo = limpar_bloco(bloco, tipo_arquivo, stats)
        dentro = limpo["competencia"].isin(competencias)
        stats["fora_da_janela"] += int((~dentro).sum())
        partes.append(limpo[dentro])
    df = pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
    stats[f"linhas_{tipo_arquivo}"] += len(df)
    return df


# ---------------------------------------------------------------------------
# Saídas
# ---------------------------------------------------------------------------
GRAO_AGREGADO = ["competencia", "cod_uf", "cod_secao", "cod_sexo",
                 "cod_raca_cor", "id_faixa_etaria", "cod_tipo_mov"]


def agregar_brasil(df: pd.DataFrame) -> pd.DataFrame:
    """Fato agregada: um registro por combinação do grão (todas as UFs).

    Contagens usam o peso (MOV/FOR +1, EXC -1). As estatísticas de salário usam
    apenas registros com salário válido e peso +1 (cancelamentos não têm como ser
    pareados com a linha original, pois a base não tem identificador).
    """
    d = df.copy()
    d["adm"] = np.where(d["saldo"] == 1, d["peso"], 0)
    d["desl"] = np.where(d["saldo"] == -1, d["peso"], 0)
    d["mov_saldo"] = d["saldo"] * d["peso"]

    contagens = d.groupby(GRAO_AGREGADO, observed=True).agg(
        qtd_admissoes=("adm", "sum"),
        qtd_desligamentos=("desl", "sum"),
        saldo=("mov_saldo", "sum"),
    )

    s = d[(d["peso"] == 1) & d["fl_salario_valido"]]
    salarios = s.groupby(GRAO_AGREGADO, observed=True).agg(
        qtd_salario_valido=("salario", "size"),
        soma_salario=("salario", "sum"),
        mediana_salario=("salario", "median"),
        mediana_salario_hora=("salario_hora", "median"),
    )
    fato = contagens.join(salarios, how="left").reset_index()
    fato["qtd_salario_valido"] = fato["qtd_salario_valido"].fillna(0).astype("int32")
    for c in ("soma_salario", "mediana_salario", "mediana_salario_hora"):
        fato[c] = fato[c].round(2)
    return fato


COLUNAS_DETALHE = [
    "competencia", "cod_municipio", "cod_uf", "cod_secao", "cod_cbo",
    "cod_sexo", "cod_raca_cor", "id_faixa_etaria", "cod_instrucao",
    "cod_tipo_mov", "saldo", "peso", "origem", "horas_contratuais", "salario",
    "salario_hora", "fl_salario_valido", "fl_intermitente", "fl_parcial", "fl_aprendiz",
]


def detalhe_uf(df: pd.DataFrame, uf: int = UF_DETALHE) -> pd.DataFrame:
    """Microdados (linha a linha) apenas da UF de detalhe (Bahia)."""
    return df.loc[df["cod_uf"] == uf, COLUNAS_DETALHE].reset_index(drop=True)
