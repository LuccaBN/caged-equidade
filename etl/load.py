"""Carga: cria o esquema e grava dimensões e fatos no PostgreSQL.

Usa COPY (carga em massa do PostgreSQL), muito mais rápido que INSERT linha a
linha. A carga é idempotente: antes de gravar uma competência, os dados
antigos dela são apagados. Assim, recarregar um mês (por exemplo, depois de
chegar um arquivo de correção) não duplica nada.
"""
import io
import json
import logging

import pandas as pd
import psycopg2

from config import ARQ_SCHEMA, url_banco

log = logging.getLogger(__name__)

ORDEM_DIMENSOES = [
    "dim_tempo", "dim_regiao", "dim_uf", "dim_municipio", "dim_secao",
    "dim_cbo", "dim_instrucao", "dim_sexo", "dim_raca_cor",
    "dim_faixa_etaria", "dim_tipo_movimentacao",
]


def conectar():
    return psycopg2.connect(url_banco())


def criar_esquema(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(ARQ_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()


def _copy(cur, tabela: str, df: pd.DataFrame) -> None:
    buffer = io.StringIO()
    df.to_csv(buffer, index=False, header=False, na_rep="\\N")
    buffer.seek(0)
    colunas = ", ".join(df.columns)
    cur.copy_expert(
        f"COPY {tabela} ({colunas}) FROM STDIN WITH (FORMAT csv, NULL '\\N')", buffer)


def _upsert_dimensao(cur, tabela: str, df: pd.DataFrame) -> None:
    """Insere códigos novos e atualiza descrições, sem apagar o que existe
    (as fatos de outras competências dependem das dimensões)."""
    chave = df.columns[0]
    cur.execute(f"CREATE TEMP TABLE tmp_{tabela} (LIKE {tabela}) ON COMMIT DROP")
    _copy(cur, f"tmp_{tabela}", df)
    demais = [c for c in df.columns if c != chave]
    sets = ", ".join(f"{c} = EXCLUDED.{c}" for c in demais)
    colunas = ", ".join(df.columns)
    cur.execute(
        f"INSERT INTO {tabela} ({colunas}) SELECT {colunas} FROM tmp_{tabela} "
        f"ON CONFLICT ({chave}) DO UPDATE SET {sets}")


def carregar(dims: dict, fato_agr: pd.DataFrame, fato_ba: pd.DataFrame,
             competencias: list[int], relatorio: dict) -> None:
    conn = conectar()
    try:
        criar_esquema(conn)
        with conn.cursor() as cur:
            for tabela in ORDEM_DIMENSOES:
                _upsert_dimensao(cur, tabela, dims[tabela])
                log.info("Dimensão %s: %d registros", tabela, len(dims[tabela]))

            lista = tuple(competencias)
            cur.execute("DELETE FROM fato_movimentacao_agregada WHERE competencia IN %s", (lista,))
            cur.execute("DELETE FROM fato_movimentacao_ba WHERE competencia IN %s", (lista,))

            _copy(cur, "fato_movimentacao_agregada", fato_agr)
            log.info("Fato agregada: %d registros", len(fato_agr))
            _copy(cur, "fato_movimentacao_ba", fato_ba)
            log.info("Fato Bahia: %d registros", len(fato_ba))

            cur.execute(
                "INSERT INTO controle_carga (competencias, arquivos, linhas_lidas, "
                "linhas_agregada, linhas_ba, relatorio_json) VALUES (%s, %s, %s, %s, %s, %s)",
                (",".join(map(str, competencias)), ",".join(relatorio["arquivos"]),
                 relatorio["original"]["linhas_lidas"], len(fato_agr), len(fato_ba),
                 json.dumps(relatorio, ensure_ascii=False)),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def resumo_banco() -> pd.DataFrame:
    """Quantidade de linhas e espaço ocupado por tabela (para a documentação)."""
    sql = """
        SELECT c.relname AS tabela,
               c.reltuples::bigint AS linhas_estimadas,
               pg_total_relation_size(c.oid) AS bytes
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
        ORDER BY bytes DESC
    """
    conn = conectar()
    try:
        with conn.cursor() as cur:
            cur.execute("ANALYZE")
            cur.execute(sql)
            linhas = cur.fetchall()
            resultado = []
            for tabela, _, tamanho in linhas:
                cur.execute(f"SELECT COUNT(*) FROM {tabela}")
                resultado.append((tabela, cur.fetchone()[0], tamanho))
            cur.execute("SELECT pg_database_size(current_database())")
            total = cur.fetchone()[0]
    finally:
        conn.close()
    df = pd.DataFrame(resultado, columns=["tabela", "linhas", "bytes"])
    df["tamanho_mb"] = (df.bytes / 1024 / 1024).round(2)
    df.attrs["tamanho_banco_mb"] = round(total / 1024 / 1024, 2)
    return df
