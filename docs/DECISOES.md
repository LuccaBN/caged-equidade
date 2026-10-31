# Decisões técnicas e justificativas

Este documento registra cada decisão tomada no tratamento, na modelagem e no
armazenamento dos dados, com o motivo de cada uma. Os números citados vêm da
competência de agosto/2026.

## Tratamento

### 1. Ler o arquivo em blocos de 500 mil linhas, só com as colunas usadas
- **Decisão:** `pd.read_csv(..., usecols=..., chunksize=500_000)`, carregando 18 das 28 colunas.
- **Motivo:** o arquivo tem 465 MB e 4,4 milhões de linhas. Ler tudo de uma vez, com todas as colunas como texto, ocupa vários GB de memória. Em blocos, o processamento roda em um computador comum.

### 2. Padronizar os nomes das colunas
- **Decisão:** `snake_case`, sem acento e com prefixo pelo papel da coluna (`cod_` para códigos, `fl_` para indicadores, `qtd_` para contagens).
- **Motivo:** nomes como `raçacor` e `competênciamov` exigem aspas no SQL e causam erro em várias ferramentas. O prefixo deixa claro o tipo de cada campo.

### 3. Manter códigos como texto e recuperar zeros à esquerda
- **Decisão:** município, CBO e seção ficam como texto. CBO recebe `zfill(6)`, município `zfill(6)`.
- **Motivo:** são identificadores, não números (não faz sentido somar CBOs). No arquivo original, códigos como o CBO `010105` aparecem como `10105` (102 linhas na amostra), e o layout também perde o zero. Sem a correção, esses registros não se ligariam à dimensão.

### 4. Converter números com vírgula decimal
- **Decisão:** `salário`, `valorsaláriofixo` e `horascontratuais` trocam `,` por `.` e viram `NUMERIC`.
- **Motivo:** no original são texto (`"2010,00"`). Sem conversão, não é possível calcular média nem mediana.

### 5. Invalidar salários anômalos sem apagar o registro
- **Decisão:** o salário só é válido se for mensal (`unidadesaláriocódigo = 5`) e estiver entre 0,3 e 150 salários mínimos (R$ 486,30 a R$ 243.150 em 2026). Fora disso, o campo `salario` fica `NULL` e `fl_salario_valido = false`, **mas a linha continua no banco**.
- **Motivo:** o arquivo tem salários de até R$ 2,6 bilhões (erros de digitação, como valores 100 vezes maiores) e o desvio-padrão chega a R$ 1,2 milhão. Esses valores destruiriam qualquer média. Apagar a linha, porém, faria a admissão ou o desligamento sumir da contagem. Resultado: 55.913 salários zerados, 335.973 não mensais e 8.661 fora da faixa foram invalidados, e 91,1% dos salários seguem válidos.
- **Salário mínimo usado:** R$ 1.621,00 (2026), R$ 1.518,00 (2025) e R$ 1.412,00 (2024), configuráveis em `config.py`.

### 6. Não remover linhas idênticas
- **Decisão:** as 224.799 linhas repetidas do arquivo de movimentações (5,1%) são mantidas.
- **Motivo:** os microdados não têm CPF nem qualquer identificador. Duas linhas iguais podem ser duas pessoas reais contratadas pela mesma empresa, no mesmo cargo, salário e perfil. A prova é que, mantendo as linhas, o saldo calculado (+165.827) bate exatamente com o número oficial do MTE. Remover duplicatas é uma regra que depende do significado do dado.

### 7. Trocar a idade exata pela faixa etária
- **Decisão:** a idade vira 7 faixas (até 17, 18–24, 25–29, 30–39, 40–49, 50–64, 65+). Os 2.888 registros sem idade vão para a faixa "Não informado". A idade exata não é gravada.
- **Motivo:** a faixa etária é o recorte pedido no dashboard. Além disso, idade exata combinada com município, ocupação, sexo e raça aumenta o risco de reidentificar alguém (minimização, LGPD art. 6º, III).

### 8. Aplicar os arquivos de ajuste (FOR e EXC) na competência correta
- **Decisão:** registros do CAGEDFOR (declarados fora do prazo) entram com peso +1, e os do CAGEDEXC (cancelados) com peso −1, sempre na competência a que pertencem (`competênciamov`), não no mês do arquivo.
- **Motivo:** é a metodologia oficial do MTE. O arquivo de agosto traz correções de meses anteriores: suas 71.080 linhas de FOR/EXC são todas de competências anteriores a agosto e, por isso, ficam fora da janela desta carga. Quando a janela de 12 meses for carregada, elas corrigem os meses certos.
- **Limitação:** um cancelamento (EXC) não pode ser pareado com a linha original, pois não há identificador. Por isso ele é descontado nas contagens, mas não altera as estatísticas de salário.

### 9. Calcular o salário por hora
- **Decisão:** `salario_hora = salario / (horas_contratuais × 4,33)`, só quando as horas são maiores que zero.
- **Motivo:** compara remunerações de jornadas diferentes, como sugerido no guia do projeto (gap salarial por hora trabalhada).

### 10. Completar códigos ausentes nas dimensões
- **Decisão:** códigos que aparecem nos dados mas não existem no layout entram na dimensão como "Não identificado no layout". Foram 12 códigos de CBO.
- **Motivo:** garante a integridade referencial (as chaves estrangeiras não falham) sem descartar registros.

## Volume

### 11. Duas tabelas fato com granularidades diferentes
- **Decisão:** o Brasil fica **agregado**; só a Bahia fica **linha a linha**.
- **Motivo:** um mês bruto tem 465 MB, e 12 meses passariam de 5 GB, contra 1 GB do plano gratuito. Agregado, o Brasil cai de 4,4 milhões de linhas para 85.641 por mês (10,4 MB). A Bahia linha a linha (176.743 linhas, 25,6 MB) permite o drill-down por município e ocupação. O banco completo ocupa 44,6 MB por mês, cerca de 435 MB em 12 meses.

### 12. Não usar amostragem estatística
- **Motivo:** a amostragem reduziria grupos pequenos, como trabalhadores indígenas (cerca de 15 mil movimentações por mês) e amarelos, e tornaria instáveis justamente os cruzamentos de raça × sexo que são o foco do projeto. A agregação reduz o volume sem perder nenhum registro.

### 13. Guardar soma e mediana na fato agregada
- **Decisão:** além das contagens, cada grupo guarda `soma_salario`, `qtd_salario_valido` e `mediana_salario`.
- **Motivo:** com soma e quantidade, o dashboard calcula a média correta em qualquer recorte (ex.: Nordeste inteiro). A mediana é pré-calculada porque não pode ser recomposta depois da agregação e é mais robusta a valores extremos que a média.

## Modelagem

### 14. Esquema estrela em banco relacional (PostgreSQL)
- **Decisão:** 2 fatos ligadas a 11 dimensões, com chaves estrangeiras.
- **Motivo:**
  - Os dados são estruturados, com esquema fixo, o que se encaixa bem num banco relacional.
  - O próprio layout do MTE já é uma lista de dimensões (uma aba por código), então a modelagem segue a estrutura natural da fonte.
  - O esquema estrela é o padrão para análise (OLAP): as consultas do dashboard são sempre "medida X por dimensões Y e Z", resolvidas com poucos JOINs.
  - As dimensões guardam as descrições uma única vez. A fato guarda só códigos pequenos (SMALLINT, CHAR), o que economiza espaço.
  - As chaves estrangeiras garantem a Veracidade: nenhum registro aponta para um código inexistente.

### 15. Views de consumo com supressão
- **Decisão:** o dashboard lê das views, não das tabelas. A `vw_movimentacao_brasil` oculta as medianas de salário quando o grupo tem menos de 5 salários válidos. A soma e a quantidade de salários continuam disponíveis, e o painel aplica a mesma regra de mínimo de 5 registros depois de agrupar.
- **Motivo:** isola o dashboard da estrutura física e aplica a proteção da LGPD em um ponto central. Na granularidade mais fina, 47.301 dos 85.641 grupos (55%) têm menos de 5 salários. Por isso a soma não pode ser ocultada: sem ela, a média de recortes maiores, como uma região inteira, ficaria distorcida.

### 16. Carga idempotente com COPY
- **Decisão:** antes de gravar, apaga os dados das competências que estão sendo carregadas. Grava com `COPY`. Dimensões usam *upsert*.
- **Motivo:** recarregar um mês (por exemplo, quando chega um arquivo de correção) não duplica dados. O `COPY` grava 176 mil linhas em poucos segundos, contra minutos com `INSERT` linha a linha.

### 17. Tabela de controle de carga
- **Decisão:** cada execução grava em `controle_carga` as competências, os arquivos, as linhas lidas e gravadas e o relatório completo.
- **Motivo:** rastreabilidade. Permite verificar, a qualquer momento, a origem e a versão dos dados no banco.
