"""Monta as tabelas de dimensão a partir da planilha de layout do MTE.

A planilha traz uma aba por variável codificada (código -> descrição).
Essas abas viram as dimensões do modelo estrela.
"""
from pathlib import Path

import pandas as pd

from config import FAIXAS_ETARIAS, SIGLAS_UF

# Classificação de cada tipo de movimentação em admissão / desligamento
CLASSE_MOV = {
    10: "Admissão", 20: "Admissão", 25: "Admissão", 35: "Admissão",
    70: "Admissão", 97: "Admissão",
    31: "Desligamento", 32: "Desligamento", 33: "Desligamento",
    40: "Desligamento", 43: "Desligamento", 45: "Desligamento",
    50: "Desligamento", 60: "Desligamento", 80: "Desligamento",
    90: "Desligamento", 98: "Desligamento",
}

MESES = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho",
         "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]


def _aba(layout: dict, nome: str) -> pd.DataFrame:
    df = layout[nome].iloc[:, :2].copy()
    df.columns = ["codigo", "descricao"]
    df = df.dropna(subset=["codigo"])
    df["codigo"] = df["codigo"].astype(str).str.strip()
    df["descricao"] = df["descricao"].astype(str).str.strip()
    return df.drop_duplicates("codigo")


def montar_dimensoes(arq_layout: Path, competencias: list[int]) -> dict[str, pd.DataFrame]:
    layout = pd.read_excel(arq_layout, sheet_name=None, dtype=str)
    dims = {}

    r = _aba(layout, "região")
    dims["dim_regiao"] = pd.DataFrame({
        "cod_regiao": r.codigo.astype(int), "nome": r.descricao})

    u = _aba(layout, "uf")
    uf = pd.DataFrame({"cod_uf": u.codigo.astype(int), "nome": u.descricao})
    uf["sigla"] = uf.cod_uf.map(SIGLAS_UF).fillna("NI")
    # região = primeiro dígito do código IBGE da UF (99 -> 9 "Não identificado")
    uf["cod_regiao"] = (uf.cod_uf // 10).where(uf.cod_uf != 99, 9)
    dims["dim_uf"] = uf[["cod_uf", "sigla", "nome", "cod_regiao"]]

    m = _aba(layout, "município")
    mun = pd.DataFrame({"cod_municipio": m.codigo.str.zfill(6)})
    # descrição vem como "Ba-Salvador": separa a sigla do nome
    partes = m.descricao.str.split("-", n=1, expand=True)
    mun["nome"] = partes[1].fillna(partes[0]).str.strip().values
    mun["cod_uf"] = pd.to_numeric(mun.cod_municipio.str[:2], errors="coerce").fillna(99).astype(int)
    mun.loc[~mun.cod_uf.isin(uf.cod_uf), "cod_uf"] = 99
    dims["dim_municipio"] = mun

    s = _aba(layout, "seção")
    dims["dim_secao"] = pd.DataFrame({"cod_secao": s.codigo.str.upper(), "descricao": s.descricao})

    c = _aba(layout, "cbo2002ocupação")
    dims["dim_cbo"] = pd.DataFrame({"cod_cbo": c.codigo.str.zfill(6), "descricao": c.descricao})

    for aba, tabela, chave in [
        ("graudeinstrução", "dim_instrucao", "cod_instrucao"),
        ("raçacor", "dim_raca_cor", "cod_raca_cor"),
        ("sexo", "dim_sexo", "cod_sexo"),
    ]:
        a = _aba(layout, aba)
        dims[tabela] = pd.DataFrame({chave: a.codigo.astype(int), "descricao": a.descricao})

    t = _aba(layout, "tipomovimentação")
    tm = pd.DataFrame({"cod_tipo_mov": t.codigo.astype(int), "descricao": t.descricao})
    tm["classe"] = tm.cod_tipo_mov.map(CLASSE_MOV).fillna("Não identificado")
    dims["dim_tipo_movimentacao"] = tm

    dims["dim_faixa_etaria"] = pd.DataFrame(
        FAIXAS_ETARIAS, columns=["id_faixa_etaria", "descricao", "idade_min", "idade_max"]
    ).astype({"idade_min": "Int16", "idade_max": "Int16"})

    tempo = pd.DataFrame({"competencia": sorted(set(competencias))})
    tempo["ano"] = tempo.competencia // 100
    tempo["mes"] = tempo.competencia % 100
    tempo["nome_mes"] = tempo.mes.map(lambda x: MESES[x - 1])
    tempo["data_referencia"] = pd.to_datetime(tempo.competencia.astype(str) + "01", format="%Y%m%d").dt.date
    dims["dim_tempo"] = tempo
    return dims


def completar_codigos(dims: dict, fatos: list[pd.DataFrame]) -> dict:
    """Garante integridade referencial: códigos que aparecem nos dados mas não
    existem no layout entram na dimensão como 'Não identificado no layout'."""
    mapa = {
        "cod_municipio": ("dim_municipio", "nome"),
        "cod_cbo": ("dim_cbo", "descricao"),
        "cod_secao": ("dim_secao", "descricao"),
        "cod_instrucao": ("dim_instrucao", "descricao"),
        "cod_raca_cor": ("dim_raca_cor", "descricao"),
        "cod_sexo": ("dim_sexo", "descricao"),
        "cod_tipo_mov": ("dim_tipo_movimentacao", "descricao"),
        "cod_uf": ("dim_uf", "nome"),
    }
    adicionados = {}
    for col, (tabela, campo) in mapa.items():
        usados = set()
        for f in fatos:
            if col in f.columns:
                usados |= set(f[col].dropna().unique())
        faltantes = sorted(usados - set(dims[tabela][col]))
        if not faltantes:
            continue
        novos = pd.DataFrame({col: faltantes, campo: "Não identificado no layout"})
        if tabela == "dim_municipio":
            novos["cod_uf"] = pd.to_numeric(novos.cod_municipio.str[:2], errors="coerce").fillna(99).astype(int)
            novos.loc[~novos.cod_uf.isin(dims["dim_uf"].cod_uf), "cod_uf"] = 99
        if tabela == "dim_tipo_movimentacao":
            novos["classe"] = "Não identificado"
        if tabela == "dim_uf":
            novos["sigla"] = "NI"
            novos["cod_regiao"] = 9
        dims[tabela] = pd.concat([dims[tabela], novos], ignore_index=True)
        adicionados[tabela] = len(faltantes)
    return adicionados
