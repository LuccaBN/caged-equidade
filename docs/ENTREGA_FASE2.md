# Entrega Técnica – Fase 2: Unificação, Tratamento, Modelagem e Armazenamento dos Dados

**Disciplina:** Big Data e Analytics
**Tema 08:** Dinâmica de Emprego Formal e Turnover Setorial
**Base de dados:** Microdados do Novo CAGED (PDET/MTE)
**Equipe:** Lucca Barbosa Nygaard e Guilherme de Jesus Duque Teixeira
**Repositório:** (colar aqui o link do GitHub)

## 1. Base de Dados Tratada

### Origem dos dados

Os dados vêm dos Microdados Não Identificados do Novo CAGED, publicados pelo Ministério do Trabalho e Emprego no FTP do PDET (ftp://ftp.mtps.gov.br/pdet/microdados/NOVO CAGED/). A base registra todas as admissões e desligamentos de trabalhadores com carteira assinada no Brasil.

### Versão original utilizada

Usamos a competência de agosto de 2026, composta por três arquivos e um dicionário:

- CAGEDMOV202608 (movimentações do mês) → 4.423.299 linhas, 28 colunas, 465 MB
- CAGEDFOR202608 (declarações fora do prazo) → 58.024 linhas, 28 colunas
- CAGEDEXC202608 (registros cancelados) → 13.056 linhas, 30 colunas
- Layout Não-identificado Novo Caged Movimentação.xlsx (dicionário com 22 abas de códigos)

Uma cópia das primeiras 1.000 linhas do arquivo original, sem nenhuma alteração, está no repositório, na pasta data/amostra_original, para comparação com a versão tratada.

### Versão resultante após o tratamento

A base tratada foi dividida em duas tabelas principais e onze tabelas de apoio:

- Movimentação agregada do Brasil → 85.641 linhas (de 4,4 milhões originais)
- Movimentação detalhada da Bahia → 176.743 linhas, uma por movimentação
- Onze tabelas de dimensão (estados, municípios, setores, profissões, sexo, raça/cor e outras) → 8.555 linhas no total

A base tratada também foi exportada em CSV, na pasta data/processed do repositório.

Para validar o tratamento, comparamos o resultado com o número oficial do governo. O saldo de empregos calculado para agosto de 2026 foi de 165.827 vagas, exatamente o mesmo valor divulgado pelo Ministério do Trabalho.

### Principais decisões e justificativas

**Salários anômalos foram invalidados, mas os registros foram mantidos.** O arquivo tem salários de até R$ 2,6 bilhões, causados por erros de digitação. Consideramos válidos apenas os salários mensais entre 0,3 e 150 salários mínimos. Quando o salário é inválido, só o valor do salário fica vazio: a linha continua contando nas admissões e desligamentos. Assim, 91,1% dos salários ficaram válidos para análise.

**Linhas idênticas não foram removidas.** O arquivo tem 224.799 linhas repetidas. Como a base não tem CPF nem outro identificador, duas linhas iguais podem ser duas pessoas reais contratadas para o mesmo cargo e salário. A comprovação é que, mantendo essas linhas, o saldo bate exatamente com o número oficial.

**A idade exata foi trocada por faixa etária.** Isso atende ao filtro de faixa etária do painel e reduz o risco de identificar pessoas, conforme a LGPD. Os 2.888 registros sem idade ficaram na faixa "Não informado".

**Códigos tiveram os zeros à esquerda recuperados.** No arquivo original, códigos de profissão como 010105 aparecem como 10105. Sem a correção, esses registros não se ligariam à tabela de profissões.

**Os arquivos de correção foram aplicados no mês correto.** Declarações fora do prazo são somadas, e registros cancelados são descontados, sempre no mês a que pertencem, como na metodologia oficial. No arquivo de agosto, todas as 71.080 linhas de correção se referem a meses anteriores e, por isso, ficaram fora desta carga.

**Não usamos amostragem estatística.** Ela reduziria os grupos menores, como trabalhadores indígenas e amarelos, e prejudicaria a análise por raça/cor e sexo. A agregação reduz o volume sem perder registros.

## 2. Processo de Tratamento dos Dados

O processo foi desenvolvido em Python, com a biblioteca Pandas, e está na pasta etl do repositório. Ele é executado com um único comando (python etl/pipeline.py --competencias 202608) e segue estas etapas:

1. **Extração:** baixa os arquivos do FTP do Ministério do Trabalho e descompacta.
2. **Leitura em blocos:** lê o arquivo em partes de 500 mil linhas, apenas com as 18 colunas necessárias, para não sobrecarregar a memória.
3. **Padronização:** renomeia as colunas para nomes sem acento e sem espaço (por exemplo, raçacor vira cod_raca_cor).
4. **Tipagem:** converte textos em números inteiros, decimais, datas e verdadeiro ou falso.
5. **Regras de qualidade:** invalida salários anômalos, trata idades vazias e cria a faixa etária e o salário por hora.
6. **Ajustes oficiais:** aplica as declarações fora do prazo e os cancelamentos.
7. **Agregação:** monta a tabela agregada do Brasil e a tabela detalhada da Bahia.
8. **Dimensões:** cria as tabelas de códigos a partir da planilha de layout do governo.
9. **Exportação:** salva a base tratada em CSV.
10. **Carga:** grava tudo no PostgreSQL.
11. **Relatório:** registra o que foi lido e o que foi gravado.

Organização do código:

- config.py → parâmetros e regras do tratamento, todos em um só lugar
- extract.py → download e descompactação
- transform.py → limpeza, tipagem, regras de qualidade e agregação
- dimensoes.py → tabelas de códigos a partir do layout
- load.py → criação do banco e carga dos dados
- pipeline.py → executa todas as etapas em ordem

Principais decisões técnicas do processo:

**Processamento mês a mês.** Cada mês é tratado separadamente, o que permite carregar 12 meses mesmo em um computador comum.

**Carga em massa com o comando COPY do PostgreSQL.** Ele grava os 176 mil registros da Bahia em poucos segundos, contra minutos inserindo linha por linha.

**Carga idempotente.** Antes de gravar um mês, o processo apaga os dados antigos desse mês. Recarregar um mês, por exemplo após uma correção do governo, não duplica dados.

**Rastreabilidade.** Cada execução grava um relatório na pasta docs/relatorios e na tabela controle_carga do banco, com os arquivos usados, as linhas lidas, as linhas gravadas e os problemas de qualidade encontrados.

**Segurança das credenciais.** As senhas ficam em variáveis de ambiente (arquivo .env) e nunca no código ou no GitHub. A conexão com o banco é criptografada (SSL).

O registro completo das decisões e justificativas está no arquivo docs/DECISOES.md do repositório.

## 3. Base Armazenada em Banco de Dados

### Infraestrutura

Os dados estão em um banco PostgreSQL hospedado na Aiven (plano gratuito, limite de 1 GB), provisionado com Terraform (pasta terraform do repositório).

### Estratégia de modelagem

Escolhemos o modelo estrela (star schema), com duas tabelas fato ligadas a onze tabelas de dimensão. Os motivos foram:

- Os dados são estruturados e têm formato fixo, o que combina com um banco relacional.
- A planilha de layout do governo já organiza os dados em códigos e descrições, que viram as dimensões naturalmente.
- As análises do painel são sempre do tipo "uma medida por categorias" (por exemplo, salário por sexo e raça), e o modelo estrela resolve isso com consultas simples.
- As descrições ficam guardadas uma única vez nas dimensões. As tabelas fato guardam apenas códigos pequenos, o que economiza espaço.
- As chaves estrangeiras impedem registros com códigos inexistentes, garantindo a consistência.

### Estrutura criada

**Tabelas fato:**

- fato_movimentacao_agregada → Brasil agrupado por mês, estado, setor, sexo, raça/cor, faixa etária e tipo de movimentação
- fato_movimentacao_ba → Bahia, uma linha por movimentação, para análises detalhadas

**Tabelas de dimensão:**

- dim_tempo → meses de referência
- dim_regiao → regiões do Brasil
- dim_uf → estados
- dim_municipio → municípios
- dim_secao → setores econômicos (CNAE)
- dim_cbo → profissões (CBO)
- dim_instrucao → grau de instrução
- dim_sexo → sexo
- dim_raca_cor → raça/cor
- dim_faixa_etaria → faixas de idade
- dim_tipo_movimentacao → motivo da admissão ou do desligamento

**Apoio e consulta:**

- controle_carga → histórico de cada carga realizada
- vw_movimentacao_brasil → consulta pronta para o painel, que oculta o salário mediano de grupos com menos de 5 pessoas (LGPD)
- vw_movimentacao_ba → consulta pronta da Bahia, com as descrições
- vw_gap_salarial_admissao → salário médio de admissão por sexo e raça/cor

### Campos e tipos

**fato_movimentacao_agregada (campo → tipo → descrição):**

- competencia → INTEGER → mês no formato AAAAMM
- cod_uf → SMALLINT → estado
- cod_secao → CHAR(1) → setor econômico
- cod_sexo → SMALLINT → sexo
- cod_raca_cor → SMALLINT → raça/cor
- id_faixa_etaria → SMALLINT → faixa etária
- cod_tipo_mov → SMALLINT → tipo de movimentação
- qtd_admissoes → INTEGER → total de admissões
- qtd_desligamentos → INTEGER → total de desligamentos
- saldo → INTEGER → admissões menos desligamentos
- qtd_salario_valido → INTEGER → quantidade de salários válidos
- soma_salario → NUMERIC(16,2) → soma dos salários válidos
- mediana_salario → NUMERIC(12,2) → salário mediano
- mediana_salario_hora → NUMERIC(10,2) → salário por hora mediano

**fato_movimentacao_ba (campo → tipo → descrição):**

- id_movimentacao → BIGSERIAL → identificador gerado na carga
- competencia → INTEGER → mês no formato AAAAMM
- cod_municipio → CHAR(6) → município
- cod_uf → SMALLINT → estado
- cod_secao → CHAR(1) → setor econômico
- cod_cbo → CHAR(6) → profissão
- cod_sexo → SMALLINT → sexo
- cod_raca_cor → SMALLINT → raça/cor
- id_faixa_etaria → SMALLINT → faixa etária
- cod_instrucao → SMALLINT → grau de instrução
- cod_tipo_mov → SMALLINT → tipo de movimentação
- saldo → SMALLINT → 1 para admissão e −1 para desligamento
- peso → SMALLINT → 1 para registro normal e −1 para registro cancelado
- origem → CHAR(3) → arquivo de origem (MOV, FOR ou EXC)
- horas_contratuais → NUMERIC(5,2) → horas semanais
- salario → NUMERIC(12,2) → salário mensal (vazio quando inválido)
- salario_hora → NUMERIC(10,2) → salário por hora
- fl_salario_valido → BOOLEAN → indica se o salário passou nas regras de qualidade
- fl_intermitente, fl_parcial e fl_aprendiz → BOOLEAN → tipo de contrato

**Dimensões:** todas seguem o padrão código → descrição. Algumas têm campos extras:

- dim_uf → sigla e região
- dim_municipio → estado
- dim_tempo → ano, mês, nome do mês e data
- dim_faixa_etaria → idade mínima e máxima
- dim_tipo_movimentacao → classe (admissão ou desligamento)

### Relacionamentos

- Cada tabela fato se liga às dimensões pelos campos de código, com chave estrangeira (relacionamento de um para muitos: um código de dimensão aparece em muitas linhas da fato).
- dim_regiao → dim_uf → dim_municipio formam uma hierarquia geográfica, que permite o detalhamento (drill-down) de região para estado e para município.
- A tabela agregada tem chave primária composta pelas sete colunas que definem o grupo, o que impede grupos repetidos.

### Quantidade de dados armazenados

Medido no banco após a carga de agosto de 2026:

- fato_movimentacao_ba → 176.743 linhas → 25,6 MB
- fato_movimentacao_agregada → 85.641 linhas → 10,4 MB
- dim_municipio → 5.659 linhas → 0,5 MB
- dim_cbo → 2.790 linhas → 0,3 MB
- demais 9 dimensões → 106 linhas → 0,3 MB
- **Total do banco → 44,6 MB**

Com 12 meses carregados, a projeção é de cerca de 435 MB, dentro do limite de 1 GB do plano gratuito.
