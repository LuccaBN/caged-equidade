"""Configurações do pipeline ETL do Novo CAGED.

Todos os parâmetros que influenciam o tratamento ficam aqui, para que as
decisões técnicas estejam documentadas em um único lugar.
"""
from pathlib import Path
import os

# ---------------------------------------------------------------------------
# Pastas
# ---------------------------------------------------------------------------
RAIZ = Path(__file__).resolve().parent.parent
DIR_DADOS = Path(os.getenv("CAGED_DIR_DADOS", RAIZ / "data"))
DIR_RAW = DIR_DADOS / "raw"            # arquivos originais (.7z e .txt) - fora do Git
DIR_PROCESSADO = DIR_DADOS / "processed"  # base tratada exportada (CSV.gz)
DIR_AMOSTRA = DIR_DADOS / "amostra_original"  # trecho do arquivo original para conferência
DIR_RELATORIOS = RAIZ / "docs" / "relatorios"
ARQ_LAYOUT = DIR_RAW / "Layout Não-identificado Novo Caged Movimentação.xlsx"
ARQ_SCHEMA = RAIZ / "sql" / "schema.sql"

# ---------------------------------------------------------------------------
# Fonte
# ---------------------------------------------------------------------------
FTP_HOST = "ftp.mtps.gov.br"
FTP_DIR_BASE = "/pdet/microdados/NOVO CAGED"
TIPOS_ARQUIVO = ("MOV", "FOR", "EXC")   # movimentações, fora do prazo, exclusões

# Peso de cada tipo de arquivo no cálculo dos totais:
# MOV e FOR somam; EXC (registros cancelados) subtrai.
PESO_ARQUIVO = {"MOV": 1, "FOR": 1, "EXC": -1}

# ---------------------------------------------------------------------------
# Recortes (otimização de volume)
# ---------------------------------------------------------------------------
UF_DETALHE = 29          # Bahia: única UF guardada linha a linha
MESES_JANELA = 12        # recorte temporal: últimos 12 meses
CHUNK_SIZE = 500_000     # linhas lidas por bloco

# Colunas do arquivo original que são carregadas (16 de 28 + 2 do EXC)
COLUNAS_USADAS = [
    "competênciamov", "região", "uf", "município", "seção",
    "saldomovimentação", "cbo2002ocupação", "graudeinstrução", "idade",
    "horascontratuais", "raçacor", "sexo", "tipomovimentação",
    "indtrabintermitente", "indtrabparcial", "salário",
    "indicadoraprendiz", "unidadesaláriocódigo",
]

# ---------------------------------------------------------------------------
# Regras de qualidade
# ---------------------------------------------------------------------------
# Salário mínimo por ano (Decretos federais)
SALARIO_MINIMO = {2024: 1412.00, 2025: 1518.00, 2026: 1621.00}
SALARIO_MIN_FATOR = 0.3    # abaixo de 0,3 SM -> salário inválido
SALARIO_MAX_FATOR = 150    # acima de 150 SM -> salário inválido
UNIDADE_SALARIO_MENSAL = 5
SEMANAS_POR_MES = 4.33
LIMITE_SUPRESSAO = 5       # LGPD: grupos com menos de 5 registros têm salário ocultado

# Faixas etárias: (id, descrição, idade mínima, idade máxima)
FAIXAS_ETARIAS = [
    (1, "Até 17 anos", 0, 17),
    (2, "18 a 24 anos", 18, 24),
    (3, "25 a 29 anos", 25, 29),
    (4, "30 a 39 anos", 30, 39),
    (5, "40 a 49 anos", 40, 49),
    (6, "50 a 64 anos", 50, 64),
    (7, "65 anos ou mais", 65, 200),
    (9, "Não informado", None, None),
]

# Siglas das UFs (o layout traz só o nome)
SIGLAS_UF = {
    11: "RO", 12: "AC", 13: "AM", 14: "RR", 15: "PA", 16: "AP", 17: "TO",
    21: "MA", 22: "PI", 23: "CE", 24: "RN", 25: "PB", 26: "PE", 27: "AL",
    28: "SE", 29: "BA", 31: "MG", 32: "ES", 33: "RJ", 35: "SP", 41: "PR",
    42: "SC", 43: "RS", 50: "MS", 51: "MT", 52: "GO", 53: "DF", 99: "NI",
}


def url_banco() -> str:
    """Monta a URL de conexão a partir de variáveis de ambiente (.env).

    Nenhuma credencial fica no código: ou se usa DATABASE_URL (fornecida pelo
    output do Terraform), ou as variáveis PG* separadas.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("PGHOST", "localhost")
    porta = os.getenv("PGPORT", "5432")
    usuario = os.getenv("PGUSER", "postgres")
    senha = os.getenv("PGPASSWORD", "")
    banco = os.getenv("PGDATABASE", "defaultdb")
    ssl = os.getenv("PGSSLMODE", "require")
    return f"postgresql://{usuario}:{senha}@{host}:{porta}/{banco}?sslmode={ssl}"
