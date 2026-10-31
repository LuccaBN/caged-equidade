"""Pipeline completo do Novo CAGED: extração -> tratamento -> carga.

Uso:
    python etl/pipeline.py --competencias 202608
    python etl/pipeline.py --ultimos 12              # janela móvel de 12 meses
    python etl/pipeline.py --competencias 202608 --sem-download --sem-banco

Opções:
    --sem-download  usa só os arquivos que já estão em data/raw
    --sem-banco     gera a base tratada (CSV) sem gravar no PostgreSQL
"""
from collections import Counter
from datetime import date
import argparse
import json
import logging
import sys

import pandas as pd
from dotenv import load_dotenv

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

from config import (  # noqa: E402
    ARQ_LAYOUT, DIR_AMOSTRA, DIR_PROCESSADO, DIR_RELATORIOS, MESES_JANELA,
    TIPOS_ARQUIVO, UF_DETALHE,
)
from extract import obter_competencia  # noqa: E402
from transform import agregar_brasil, detalhe_uf, ler_arquivo  # noqa: E402
from dimensoes import completar_codigos, montar_dimensoes  # noqa: E402

log = logging.getLogger("pipeline")


def ultimas_competencias(n: int, defasagem: int = 2) -> list[str]:
    """Últimos n meses publicados (o MTE publica com cerca de 1 a 2 meses de atraso)."""
    hoje = date.today()
    ano, mes = hoje.year, hoje.month - defasagem
    lista = []
    for _ in range(n):
        while mes <= 0:
            mes += 12
            ano -= 1
        lista.append(f"{ano}{mes:02d}")
        mes -= 1
    return sorted(lista)


def salvar_amostra_original(arquivo, linhas: int = 1000) -> None:
    """Guarda as primeiras linhas do arquivo original, sem alteração,
    para permitir comparar a versão original com a tratada."""
    DIR_AMOSTRA.mkdir(parents=True, exist_ok=True)
    destino = DIR_AMOSTRA / f"{arquivo.stem}_primeiras_{linhas}_linhas.txt"
    with open(arquivo, encoding="utf-8") as origem, open(destino, "w", encoding="utf-8") as saida:
        for i, linha in enumerate(origem):
            if i > linhas:
                break
            saida.write(linha)


def executar(competencias: list[str], baixar: bool, gravar_banco: bool) -> dict:
    comps_int = sorted(int(c) for c in competencias)
    janela = set(comps_int)
    stats = Counter()
    arquivos_usados = []

    # 1) Garante os arquivos de todas as competências
    arquivos = {comp: obter_competencia(comp, baixar=baixar) for comp in competencias}

    # 2) FOR e EXC são pequenos e podem corrigir QUALQUER mês da janela
    #    (ex.: o arquivo de agosto traz declarações atrasadas de julho).
    #    Por isso são lidos todos antes, e distribuídos pela competência real.
    ajustes = []
    for comp in competencias:
        for tipo in ("FOR", "EXC"):
            if tipo in arquivos[comp]:
                ajustes.append(ler_arquivo(arquivos[comp][tipo], tipo, janela, stats))
                arquivos_usados.append(arquivos[comp][tipo].name)
    ajustes = pd.concat(ajustes, ignore_index=True) if ajustes else None

    # 3) MOV é grande: processado um mês por vez para não estourar a memória.
    #    Como a competência faz parte do grão da fato agregada, agregar mês a
    #    mês dá exatamente o mesmo resultado que agregar tudo junto.
    agregadas, detalhes = [], []
    for comp in competencias:
        if "MOV" not in arquivos[comp]:
            log.warning("Competência %s sem arquivo MOV", comp)
            continue
        salvar_amostra_original(arquivos[comp]["MOV"])
        base = ler_arquivo(arquivos[comp]["MOV"], "MOV", janela, stats)
        arquivos_usados.append(arquivos[comp]["MOV"].name)
        stats["saldo_apenas_mov"] += int(base["saldo"].sum())
        if ajustes is not None:
            base = pd.concat([base, ajustes[ajustes.competencia == int(comp)]], ignore_index=True)
        agregadas.append(agregar_brasil(base))
        detalhes.append(detalhe_uf(base, UF_DETALHE))
        log.info("Competência %s tratada: %d linhas", comp, len(base))
        del base

    fato_agr = pd.concat(agregadas, ignore_index=True)
    fato_ba = pd.concat(detalhes, ignore_index=True)

    dims = montar_dimensoes(ARQ_LAYOUT, comps_int)
    codigos_novos = completar_codigos(dims, [fato_agr, fato_ba])

    # ---------------- Relatório: versão original x tratada ----------------
    relatorio = {
        "competencias": comps_int,
        "arquivos": arquivos_usados,
        "original": {
            "linhas_lidas": int(stats["linhas_lidas"]),
            "colunas_originais": 28,
            "colunas_usadas": 18,
            "linhas_fora_da_janela_descartadas": int(stats["fora_da_janela"]),
            "linhas_por_arquivo": {t: int(stats[f"linhas_{t}"]) for t in TIPOS_ARQUIVO},
        },
        "qualidade": {
            "idade_nula": int(stats["idade_nula"]),
            "salario_zerado": int(stats["salario_zerado"]),
            "salario_nao_mensal": int(stats["salario_nao_mensal"]),
            "salario_fora_da_faixa": int(stats["salario_fora_faixa"]),
            "salario_valido": int(stats["salario_valido"]),
            "pct_salario_valido": round(stats["salario_valido"] / max(stats["linhas_lidas"], 1) * 100, 2),
            "codigos_ausentes_no_layout": codigos_novos,
        },
        "resultado": {
            "fato_agregada_linhas": len(fato_agr),
            "fato_ba_linhas": len(fato_ba),
            "admissoes": int(fato_agr.qtd_admissoes.sum()),
            "desligamentos": int(fato_agr.qtd_desligamentos.sum()),
            "saldo": int(fato_agr.saldo.sum()),
            "saldo_apenas_mov": int(stats["saldo_apenas_mov"]),
        },
    }

    # ---------------- Exporta a base tratada ----------------
    DIR_PROCESSADO.mkdir(parents=True, exist_ok=True)
    sufixo = f"{comps_int[0]}_{comps_int[-1]}"
    fato_agr.to_csv(DIR_PROCESSADO / f"fato_movimentacao_agregada_{sufixo}.csv.gz", index=False)
    fato_ba.to_csv(DIR_PROCESSADO / f"fato_movimentacao_ba_{sufixo}.csv.gz", index=False)
    (DIR_PROCESSADO / "dimensoes").mkdir(exist_ok=True)
    for nome, df in dims.items():
        df.to_csv(DIR_PROCESSADO / "dimensoes" / f"{nome}.csv", index=False)

    if gravar_banco:
        from load import carregar, resumo_banco
        carregar(dims, fato_agr, fato_ba, comps_int, relatorio)
        resumo = resumo_banco()
        relatorio["banco"] = {
            "tamanho_total_mb": resumo.attrs["tamanho_banco_mb"],
            "tabelas": resumo.drop(columns="bytes").to_dict(orient="records"),
        }

    DIR_RELATORIOS.mkdir(parents=True, exist_ok=True)
    (DIR_RELATORIOS / f"relatorio_carga_{sufixo}.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8")
    return relatorio


def main():
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="ETL Novo CAGED")
    g = p.add_mutually_exclusive_group()
    g.add_argument("--competencias", nargs="+", help="Lista de AAAAMM")
    g.add_argument("--ultimos", type=int, help="Últimos N meses publicados")
    p.add_argument("--sem-download", action="store_true")
    p.add_argument("--sem-banco", action="store_true")
    a = p.parse_args()

    comps = a.competencias or ultimas_competencias(a.ultimos or MESES_JANELA)
    rel = executar(comps, baixar=not a.sem_download, gravar_banco=not a.sem_banco)
    print(json.dumps(rel["resultado"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
