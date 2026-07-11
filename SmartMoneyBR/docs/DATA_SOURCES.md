# Fontes de dados — fatos verificados na prática

Verificado em 2026-07-09 baixando dados reais (não assumido). Sempre re-verificar se a CVM mudar algo.

## CDA — Composição e Diversificação das Aplicações

**URL**: `https://dados.cvm.gov.br/dados/FI/DOC/CDA/DADOS/cda_fi_{AAAAMM}.zip`

Testado com `202605` (recente) e `202406` (~2 anos atrás) — **mesma estrutura de colunas nos dois**. A CVM reprocessou/republicou o histórico completo no schema atual (timestamps internos do zip de 2024-06 mostram regeneração em 2026-02-18). **Não existe necessidade de lógica por "era" de nome de arquivo** — um único padrão de URL/parsing funciona para toda a história.

### Arquivos dentro do zip

| Arquivo | Conteúdo |
|---|---|
| `cda_fi_BLC_1..8_{AAAAMM}.csv` | 8 blocos de ativos (títulos públicos, cotas de fundos, swaps, **ações/BLC_4**, depósitos IF, títulos agro, investimento exterior, outros) |
| `cda_fi_PL_{AAAAMM}.csv` | Patrimônio líquido por fundo/classe — `VL_PATRIM_LIQ` |
| `cda_fi_CONFID_{AAAAMM}.csv` | Posições confidenciais **agregadas por categoria** (não por ativo individual) — pode não existir em meses antigos (confidencialidade expira, ~3 meses) |
| `cda_fie_{AAAAMM}.csv` | Categoria separada "FIE" (não confundir com o rename geral — é só mais um tipo de fundo/classe, coexiste com os arquivos `cda_fi_*`) |

### BLC_4 — bloco relevante para ações (Fase 1)

Colunas (idênticas em 2024 e 2026):
```
TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;TP_ATIVO;EMISSOR_LIGADO;
TP_NEGOC;QT_VENDA_NEGOC;VL_VENDA_NEGOC;QT_AQUIS_NEGOC;VL_AQUIS_NEGOC;QT_POS_FINAL;
VL_MERC_POS_FINAL;VL_CUSTO_POS_FINAL;DT_CONFID_APLIC;CD_ATIVO;DS_ATIVO;CD_ISIN;
DT_INI_VIGENCIA;DT_FIM_VIGENCIA
```

**Mapeamento pros nossos campos:**
- `CNPJ_FUNDO_CLASSE` → chave natural do fundo (fund_id). Nota: pós-Resolução CVM 175, é comum ser uma **classe dentro de um fundo guarda-chuva** (`TP_FUNDO_CLASSE = "CLASSES - FIF"` na maioria dos casos — 25.381 de 25.534 linhas no PL de mai/2026; só 8 ainda são `FI` tradicional, 145 são `CLASSES - FIP`). Tratamos cada `CNPJ_FUNDO_CLASSE` como uma entidade "fundo" própria — é a granularidade real disponível.
- `DENOM_SOCIAL` → nome do fundo
- `DT_COMPTC` → `ref_date` (mês de competência, sempre fim de mês, ex. `2026-05-31`)
- `CD_ATIVO` → ticker (ex. `PETR4`, `KLBN11`)
- `QT_POS_FINAL` → quantidade da posição final do mês
- `VL_MERC_POS_FINAL` → valor de mercado da posição final do mês
- `CD_ISIN` → ISIN (nullable)

**BLC_4 NÃO é só ações** — mistura ações, debêntures, opções, futuros, BDRs etc, diferenciados por `TP_APLIC`/`TP_ATIVO`. Distribuição real (mai/2026, ~158k linhas): Debêntures (128k) >> Ações (12.9k) > Opções titulares (6.2k) > Opções lançadas (3.3k) > Ações cedidas em empréstimo (2.8k) > Ações recebidas em empréstimo (1.6k) > BDR (1.1k) > Certificado de depósito de ações (935) > Futuros (~700) > outros.

**Filtro de ações pra Fase 1** — `TP_ATIVO IN (...)`, não `TP_APLIC`:
- `'Ação ordinária'` (ON, ex. PETR3)
- `'Ação preferencial'` (PN, ex. PETR4)
- `'Certificado de depósito de ações'` (**units**, ex. `KLBN11`, `SANB11` — descoberto testando KLBN11 na prática, NÃO cai em "Ação ordinária/preferencial")

**Armadilha confirmada**: o mesmo ticker pode aparecer em múltiplas linhas por mês pro mesmo fundo com `TP_APLIC` diferente — ex. KLBN11 aparece como posição normal (`TP_APLIC = "Certificado ou recibo de depósito..."`) E como "cedidos em empréstimo" (`TP_APLIC = "Ações e outros TVM cedidos em empréstimo"`) na mesma linha de fundo+mês. **O parser deve agrupar por `(CNPJ_FUNDO_CLASSE, CD_ATIVO, DT_COMPTC)` e somar `QT_POS_FINAL`/`VL_MERC_POS_FINAL`** entre essas linhas — possuir + emprestar não muda a titularidade beneficiária, então devem ser consolidadas numa única posição.

### Parsing — confirmado na prática

- Separador: `;`
- Encoding: `latin-1` (cp1252 também funciona — nomes com acento tipo "Ações" aparecem corrompidos se ler como UTF-8)
- **Decimal: PONTO, não vírgula** — `VL_MERC_POS_FINAL` vem como `7457890.08`, não `7457890,08`. A suposição inicial do plano (decimal vírgula) estava errada — confirmado só ao inspecionar dado real. `pd.read_csv(..., sep=';', encoding='latin-1')` já lê certo com decimal padrão (ponto), sem precisar do parâmetro `decimal=`.

### CONFID — semântica confirmada

Estrutura: `TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;TP_APLIC;VL_VENDA_NEGOC;VL_AQUIS_NEGOC;VL_MERC_POS_FINAL;VL_CUSTO_POS_FINAL;DT_CONFID_APLIC`

**Agregado por (fundo, TP_APLIC/categoria), NÃO por ativo individual.** Não tem `CD_ATIVO`. Ou seja: quando um fundo tem posição confidencial em "Ações", o CONFID mostra só o valor total da categoria pra esse fundo, sem revelar QUAL ativo — não dá pra atribuir a um ticker específico de jeito nenhum. `DT_CONFID_APLIC` = data até quando fica confidencial (ex. `2026-08-29`).

**Implicação pro motor de comparação**: não precisa de tratamento especial de "linha confidencial dentro do BLC_4" — o BLC_4 simplesmente não vai ter a linha daquele ativo pro fundo naquele mês (fica só no CONFID, agregado, sem ticker). Isso significa que a % de carteira em ações pode ficar subestimada pra fundos com posições confidenciais ativas — limitação documentada, não um bug de parsing.

Meses antigos (testado: 2024-06) **não têm arquivo CONFID** — confidencialidade de ~3 meses já expirou, dados já são públicos e apareceriam normalmente no BLC_4. Parser deve tratar CONFID como opcional (pode não existir no zip).

### PL — patrimônio líquido

Estrutura: `TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;DENOM_SOCIAL;DT_COMPTC;VL_PATRIM_LIQ`

Uma linha por fundo/classe/mês. **Vem de graça no mesmo zip do CDA** — decidido incluir ingestão do PL já na Fase 1 (não esperar o Informe Diário) pra ter "% da carteira em ações vs. patrimônio total real" desde o início, já que o custo marginal é baixo (mesmo arquivo, já baixado).

### Volume real observado

Um mês (mai/2026): 25.534 fundos/classes no PL; ~12.9k linhas de "Ação ordinária/preferencial" + ~935 de units no BLC_4 (antes de agrupar). Confirma a estimativa do plano de volume "milhões de linhas" ao longo de ~24 meses de histórico é realista mas não assustador — segue sem partição por ora.

## Cadastro de gestor/administrador — adiado

BLC_4/PL não trazem nome do gestor, só `DENOM_SOCIAL` (nome do fundo). Cadastro de gestor fica pra fase futura (dataset de Cadastro de Fundos da CVM, fora do escopo da Fase 1).
