-- =====================================================================
-- Esquema do banco: Novo CAGED - Equidade de gênero e raça no emprego
-- Modelagem: Esquema Estrela (Star Schema)
--   * 11 tabelas de dimensão (descrições dos códigos do MTE)
--   * 2 tabelas fato:
--       fato_movimentacao_agregada -> Brasil, dados agrupados (visão macro)
--       fato_movimentacao_ba       -> Bahia, linha a linha (drill-down)
--   * 1 tabela de controle de carga (rastreabilidade)
--   * views de consumo para o dashboard (com supressão LGPD)
-- Script idempotente: pode ser executado várias vezes.
-- =====================================================================

-- ------------------------- DIMENSÕES ---------------------------------
CREATE TABLE IF NOT EXISTS dim_tempo (
    competencia      INTEGER PRIMARY KEY,          -- AAAAMM
    ano              SMALLINT NOT NULL,
    mes              SMALLINT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    nome_mes         VARCHAR(10) NOT NULL,
    data_referencia  DATE NOT NULL                 -- 1º dia do mês
);

CREATE TABLE IF NOT EXISTS dim_regiao (
    cod_regiao  SMALLINT PRIMARY KEY,
    nome        VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_uf (
    cod_uf      SMALLINT PRIMARY KEY,              -- código IBGE
    sigla       CHAR(2) NOT NULL,
    nome        VARCHAR(40) NOT NULL,
    cod_regiao  SMALLINT NOT NULL REFERENCES dim_regiao (cod_regiao)
);

CREATE TABLE IF NOT EXISTS dim_municipio (
    cod_municipio  CHAR(6) PRIMARY KEY,            -- código IBGE (6 dígitos)
    nome           VARCHAR(80) NOT NULL,
    cod_uf         SMALLINT NOT NULL REFERENCES dim_uf (cod_uf)
);

CREATE TABLE IF NOT EXISTS dim_secao (
    cod_secao  CHAR(1) PRIMARY KEY,                -- seção CNAE 2.0 (A..U, Z)
    descricao  VARCHAR(120) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_cbo (
    cod_cbo    CHAR(6) PRIMARY KEY,                -- CBO 2002
    descricao  VARCHAR(200) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_instrucao (
    cod_instrucao  SMALLINT PRIMARY KEY,
    descricao      VARCHAR(60) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_sexo (
    cod_sexo   SMALLINT PRIMARY KEY,               -- 1 Homem, 3 Mulher, 9 NI
    descricao  VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_raca_cor (
    cod_raca_cor  SMALLINT PRIMARY KEY,            -- 1 Branca ... 9 NI
    descricao     VARCHAR(30) NOT NULL
);

CREATE TABLE IF NOT EXISTS dim_faixa_etaria (
    id_faixa_etaria  SMALLINT PRIMARY KEY,
    descricao        VARCHAR(30) NOT NULL,
    idade_min        SMALLINT,
    idade_max        SMALLINT
);

CREATE TABLE IF NOT EXISTS dim_tipo_movimentacao (
    cod_tipo_mov  SMALLINT PRIMARY KEY,
    descricao     VARCHAR(80) NOT NULL,
    classe        VARCHAR(20) NOT NULL             -- Admissão / Desligamento
);

-- ------------------------- FATOS -------------------------------------
-- Brasil agregado. Grão: competência x UF x seção x sexo x raça x faixa etária x tipo de movimentação
CREATE TABLE IF NOT EXISTS fato_movimentacao_agregada (
    competencia           INTEGER  NOT NULL REFERENCES dim_tempo (competencia),
    cod_uf                SMALLINT NOT NULL REFERENCES dim_uf (cod_uf),
    cod_secao             CHAR(1)  NOT NULL REFERENCES dim_secao (cod_secao),
    cod_sexo              SMALLINT NOT NULL REFERENCES dim_sexo (cod_sexo),
    cod_raca_cor          SMALLINT NOT NULL REFERENCES dim_raca_cor (cod_raca_cor),
    id_faixa_etaria       SMALLINT NOT NULL REFERENCES dim_faixa_etaria (id_faixa_etaria),
    cod_tipo_mov          SMALLINT NOT NULL REFERENCES dim_tipo_movimentacao (cod_tipo_mov),
    qtd_admissoes         INTEGER  NOT NULL DEFAULT 0,
    qtd_desligamentos     INTEGER  NOT NULL DEFAULT 0,
    saldo                 INTEGER  NOT NULL DEFAULT 0,
    qtd_salario_valido    INTEGER  NOT NULL DEFAULT 0,
    soma_salario          NUMERIC(16,2),
    mediana_salario       NUMERIC(12,2),
    mediana_salario_hora  NUMERIC(10,2),
    PRIMARY KEY (competencia, cod_uf, cod_secao, cod_sexo, cod_raca_cor, id_faixa_etaria, cod_tipo_mov)
);

-- Bahia linha a linha (sem idade exata: só a faixa etária - LGPD)
CREATE TABLE IF NOT EXISTS fato_movimentacao_ba (
    id_movimentacao    BIGSERIAL PRIMARY KEY,
    competencia        INTEGER  NOT NULL REFERENCES dim_tempo (competencia),
    cod_municipio      CHAR(6)  NOT NULL REFERENCES dim_municipio (cod_municipio),
    cod_uf             SMALLINT NOT NULL REFERENCES dim_uf (cod_uf),
    cod_secao          CHAR(1)  NOT NULL REFERENCES dim_secao (cod_secao),
    cod_cbo            CHAR(6)  NOT NULL REFERENCES dim_cbo (cod_cbo),
    cod_sexo           SMALLINT NOT NULL REFERENCES dim_sexo (cod_sexo),
    cod_raca_cor       SMALLINT NOT NULL REFERENCES dim_raca_cor (cod_raca_cor),
    id_faixa_etaria    SMALLINT NOT NULL REFERENCES dim_faixa_etaria (id_faixa_etaria),
    cod_instrucao      SMALLINT NOT NULL REFERENCES dim_instrucao (cod_instrucao),
    cod_tipo_mov       SMALLINT NOT NULL REFERENCES dim_tipo_movimentacao (cod_tipo_mov),
    saldo              SMALLINT NOT NULL CHECK (saldo IN (-1, 1)),
    peso               SMALLINT NOT NULL CHECK (peso IN (-1, 1)),   -- -1 = registro cancelado (EXC)
    origem             CHAR(3)  NOT NULL CHECK (origem IN ('MOV', 'FOR', 'EXC')),
    horas_contratuais  NUMERIC(5,2),
    salario            NUMERIC(12,2),          -- NULL quando inválido
    salario_hora       NUMERIC(10,2),
    fl_salario_valido  BOOLEAN NOT NULL,
    fl_intermitente    BOOLEAN NOT NULL,
    fl_parcial         BOOLEAN NOT NULL,
    fl_aprendiz        BOOLEAN NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_ba_competencia ON fato_movimentacao_ba (competencia);
CREATE INDEX IF NOT EXISTS ix_ba_perfil      ON fato_movimentacao_ba (cod_sexo, cod_raca_cor);
CREATE INDEX IF NOT EXISTS ix_ba_municipio   ON fato_movimentacao_ba (cod_municipio);
CREATE INDEX IF NOT EXISTS ix_agr_perfil     ON fato_movimentacao_agregada (cod_sexo, cod_raca_cor);

-- ------------------------- CONTROLE ----------------------------------
-- Registra cada carga: o que foi lido do original e o que foi gravado
CREATE TABLE IF NOT EXISTS controle_carga (
    id_carga            SERIAL PRIMARY KEY,
    executado_em        TIMESTAMP NOT NULL DEFAULT NOW(),
    competencias        VARCHAR(200) NOT NULL,
    arquivos            VARCHAR(400) NOT NULL,
    linhas_lidas        BIGINT NOT NULL,
    linhas_agregada     BIGINT NOT NULL,
    linhas_ba           BIGINT NOT NULL,
    relatorio_json      TEXT
);

-- ------------------------- VIEWS -------------------------------------
-- Recriadas a cada execução (DROP + CREATE) para aceitar mudanças de colunas
DROP VIEW IF EXISTS vw_movimentacao_brasil;
DROP VIEW IF EXISTS vw_movimentacao_ba;
DROP VIEW IF EXISTS vw_gap_salarial_admissao;

-- Consumo pelo dashboard. Supressão LGPD: as medianas de grupos com menos de
-- 5 salários válidos não são exibidas. soma_salario e qtd_salario_valido são
-- mantidas porque o painel precisa delas para recalcular a média em recortes
-- maiores (ex.: Nordeste inteiro); o painel aplica a mesma regra de mínimo de
-- 5 registros depois de agrupar.
CREATE OR REPLACE VIEW vw_movimentacao_brasil AS
SELECT f.competencia, t.ano, t.mes, t.data_referencia,
       r.nome  AS regiao, u.sigla AS uf, u.nome AS nome_uf,
       s.cod_secao, s.descricao AS setor,
       sx.descricao AS sexo, rc.descricao AS raca_cor,
       fe.descricao AS faixa_etaria,
       tm.descricao AS tipo_movimentacao, tm.classe,
       f.qtd_admissoes, f.qtd_desligamentos, f.saldo, f.qtd_salario_valido,
       f.soma_salario,
       CASE WHEN f.qtd_salario_valido >= 5 THEN f.mediana_salario END      AS mediana_salario,
       CASE WHEN f.qtd_salario_valido >= 5 THEN f.mediana_salario_hora END AS mediana_salario_hora
FROM fato_movimentacao_agregada f
JOIN dim_tempo t              ON t.competencia     = f.competencia
JOIN dim_uf u                 ON u.cod_uf          = f.cod_uf
JOIN dim_regiao r             ON r.cod_regiao      = u.cod_regiao
JOIN dim_secao s              ON s.cod_secao       = f.cod_secao
JOIN dim_sexo sx              ON sx.cod_sexo       = f.cod_sexo
JOIN dim_raca_cor rc          ON rc.cod_raca_cor   = f.cod_raca_cor
JOIN dim_faixa_etaria fe      ON fe.id_faixa_etaria = f.id_faixa_etaria
JOIN dim_tipo_movimentacao tm ON tm.cod_tipo_mov   = f.cod_tipo_mov;

CREATE OR REPLACE VIEW vw_movimentacao_ba AS
SELECT f.id_movimentacao, f.competencia, m.nome AS municipio,
       s.descricao AS setor, c.descricao AS ocupacao,
       sx.descricao AS sexo, rc.descricao AS raca_cor, fe.descricao AS faixa_etaria,
       i.descricao AS instrucao, tm.descricao AS tipo_movimentacao, tm.classe,
       f.saldo, f.peso, f.origem, f.horas_contratuais, f.salario, f.salario_hora,
       f.fl_salario_valido, f.fl_intermitente, f.fl_parcial, f.fl_aprendiz
FROM fato_movimentacao_ba f
JOIN dim_municipio m          ON m.cod_municipio    = f.cod_municipio
JOIN dim_secao s              ON s.cod_secao        = f.cod_secao
JOIN dim_cbo c                ON c.cod_cbo          = f.cod_cbo
JOIN dim_sexo sx              ON sx.cod_sexo        = f.cod_sexo
JOIN dim_raca_cor rc          ON rc.cod_raca_cor    = f.cod_raca_cor
JOIN dim_faixa_etaria fe      ON fe.id_faixa_etaria = f.id_faixa_etaria
JOIN dim_instrucao i          ON i.cod_instrucao    = f.cod_instrucao
JOIN dim_tipo_movimentacao tm ON tm.cod_tipo_mov    = f.cod_tipo_mov;

-- Indicador interseccional pronto: salário médio de admissão por sexo x raça
-- (soma dos salários válidos / quantidade de salários válidos)
CREATE OR REPLACE VIEW vw_gap_salarial_admissao AS
SELECT f.competencia, sx.descricao AS sexo, rc.descricao AS raca_cor,
       SUM(f.qtd_admissoes)                                        AS admissoes,
       ROUND(SUM(f.soma_salario) / NULLIF(SUM(f.qtd_salario_valido), 0), 2) AS salario_medio
FROM fato_movimentacao_agregada f
JOIN dim_sexo sx              ON sx.cod_sexo     = f.cod_sexo
JOIN dim_raca_cor rc          ON rc.cod_raca_cor = f.cod_raca_cor
JOIN dim_tipo_movimentacao tm ON tm.cod_tipo_mov = f.cod_tipo_mov
WHERE tm.classe = 'Admissão'
GROUP BY f.competencia, sx.descricao, rc.descricao
HAVING SUM(f.qtd_salario_valido) >= 5;
