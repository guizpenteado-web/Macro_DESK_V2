# Instalação e Uso — Indicador Fluxo Estrangeiro IBOV no TradingView

> **Arquivo do indicador:** `FluxoEstrangeiro_IBOV.pine`
> **Dados:** B3 via dadosdemercado.com.br

---

## Visão Geral do Fluxo de Instalação

```
PASSO 1          PASSO 2               PASSO 3            PASSO 4
Obter CSV   →   Importar no TV   →   Colar Pine Script  →  Configurar
(dados B3)      (símbolo custom)      (editor Pine)         (inputs)
```

O TradingView não acessa URLs externas via Pine Script em contas padrão.
O dado precisa chegar como **símbolo customizado importado por CSV**.

---

## Pré-requisitos

| Requisito | Mínimo | Recomendado |
|-----------|--------|-------------|
| Conta TradingView | Essential (paga) | Premium+ |
| Acesso à internet | Sim | — |
| Backend rodando | Não (manual) | Sim (atualização diária) |

> **Contas gratuitas (Basic)** não suportam importação de dados CSV customizados.
> A funcionalidade "Carregar dados de arquivo" exige plano **Essential ou superior**.

---

## PASSO 1 — Obter o Arquivo CSV

Escolha uma das duas formas:

---

### Opção A: Geração via Backend (recomendada — automática)

Se o backend do projeto já está rodando ([SistemaFluxoEstrangeiro.md](SistemaFluxoEstrangeiro.md)):

```bash
# Baixar o CSV completo gerado pela API
curl "http://localhost/api/v1/fluxo/export.csv" -o fluxo_estrangeiro.csv

# Ou via URL pública (produção)
curl "https://SEU-DOMINIO/api/v1/fluxo/export.csv" -o fluxo_estrangeiro.csv
```

---

### Opção B: Criação Manual do CSV

Se ainda não tem o backend, crie o CSV manualmente com base nos dados de
[dadosdemercado.com.br/fluxo](https://www.dadosdemercado.com.br/fluxo).

**Formato obrigatório do CSV:**

```csv
date,open,high,low,close,volume
2024-01-02,-1500.00,-1500.00,-1600.00,-1600.00,100.00
2024-01-03,-1600.00,-1400.00,-1600.00,-1400.00,200.00
2024-01-04,-1400.00,-1200.00,-1400.00,-1200.00,200.00
```

| Coluna | O que armazenar | Fórmula |
|--------|-----------------|---------|
| `date` | Data do pregão | `YYYY-MM-DD` |
| `close` | Saldo acumulado do dia | `saldo_acumulado` |
| `open` | Saldo acumulado do dia anterior | `saldo_acumulado - saldo_dia` |
| `high` | Máximo entre open e close | `MAX(open, close)` |
| `low` | Mínimo entre open e close | `MIN(open, close)` |
| `volume` | Magnitude do fluxo do dia | `ABS(saldo_dia)` |

**Exemplo preenchido com valores reais (R$ milhões):**

| date | open | high | low | close | volume |
|------|------|------|-----|-------|--------|
| 2024-01-02 | 0.00 | 312.45 | 0.00 | 312.45 | 312.45 |
| 2024-01-03 | 312.45 | 312.45 | 189.22 | 189.22 | 123.23 |
| 2024-01-04 | 189.22 | 631.80 | 189.22 | 631.80 | 442.58 |

> **Regra de ouro:** `close - open` deve ser igual ao `saldo_dia` daquela data.
> Positivo = entrada de capital estrangeiro. Negativo = saída.

**Template de planilha Excel/Google Sheets para montar o CSV:**

```
Coluna A: Data (dd/mm/aaaa da B3 → converter para aaaa-mm-dd)
Coluna B: Saldo_dia (valor bruto da tabela)
Coluna C: Saldo_acumulado (soma corrida da coluna B)
Coluna D: open  → =C2-B2  (acumulado anterior)
Coluna E: high  → =MAX(D2,C2)
Coluna F: low   → =MIN(D2,C2)
Coluna G: close → =C2
Coluna H: volume → =ABS(B2)
```

Salve exportando apenas as colunas date, open, high, low, close, volume em CSV UTF-8.

---

## PASSO 2 — Importar o CSV no TradingView

### 2.1 Acessar a importação de dados

1. No TradingView, abra qualquer gráfico (ex: IBOV)
2. Na barra superior, clique em **"+"** (Adicionar ao gráfico) → **"Indicador"** 
3. Na caixa de busca, clique na aba **"Dados personalizados"**
4. Clique em **"Carregar dados de arquivo"**

**Caminho alternativo:**
- Menu superior → **Gráfico** → **Gerenciar dados personalizados** → **Importar arquivo**

---

### 2.2 Upload do CSV

1. Clique em **"Selecionar arquivo"**
2. Selecione o arquivo `fluxo_estrangeiro.csv`
3. O TradingView fará o parse automático das colunas
4. Verifique o preview — confirme que as colunas foram mapeadas corretamente:

```
date   → Date     ✓
open   → Open     ✓
high   → High     ✓
low    → Low      ✓
close  → Close    ✓
volume → Volume   ✓
```

---

### 2.3 Nomear o símbolo customizado

Após o upload:

1. Em **"Nome do símbolo"**, digite exatamente:
   ```
   FLUXO_EST_IBOV
   ```
2. Em **"Descrição"**, digite:
   ```
   Fluxo Acumulado Investidor Estrangeiro IBOV
   ```
3. Em **"Tipo"**, selecione **"Índice"**
4. Em **"Moeda"**, selecione **"BRL"**
5. Clique em **"Importar"**

> O símbolo ficará disponível como `SPREADSHEET:FLUXO_EST_IBOV`
> (prefixo `SPREADSHEET:` é adicionado automaticamente pelo TradingView)

---

### 2.4 Verificar a importação

Para confirmar que os dados chegaram corretamente:

1. Na caixa de busca de ativos (topo do gráfico), digite:
   ```
   FLUXO_EST_IBOV
   ```
2. Selecione o resultado com prefixo `SPREADSHEET:`
3. O gráfico deve mostrar candlesticks com os dados importados
4. Verifique se a escala e as datas batem com os dados da B3

---

## PASSO 3 — Instalar o Pine Script

### 3.1 Abrir o Pine Editor

1. No rodapé do gráfico, clique em **"Pine Editor"**
   (ou atalho `Alt + P` no Windows)
2. Clique em **"Novo script"** → **"Indicador vazio"**
3. Apague todo o conteúdo padrão do editor

---

### 3.2 Colar o código

1. Abra o arquivo [FluxoEstrangeiro_IBOV.pine](FluxoEstrangeiro_IBOV.pine)
2. Selecione todo o conteúdo (`Ctrl + A`) e copie (`Ctrl + C`)
3. Cole no Pine Editor do TradingView (`Ctrl + V`)

---

### 3.3 Compilar e adicionar ao gráfico

1. Clique em **"Adicionar ao gráfico"** (botão azul no canto superior direito do editor)
2. O indicador deve aparecer como painel separado abaixo do gráfico principal
3. Se houver erros de compilação, veja a seção **Solução de Problemas** abaixo

---

## PASSO 4 — Configurar os Inputs

Dê duplo clique no indicador (ou clique na engrenagem ⚙️) para abrir as configurações.

---

### Aba: Fonte de Dados

| Campo | Valor padrão | O que mudar |
|-------|-------------|-------------|
| **Símbolo do CSV Importado** | `SPREADSHEET:FLUXO_EST_IBOV` | Manter se usou o nome do Passo 2.3 |
| **Período de Referência** | `Acumulado Total` | Ver opções abaixo |

**Opções de Período:**

| Opção | O que plota |
|-------|-------------|
| `Acumulado Total` | Soma histórica desde o início da série |
| `No Ano (YTD)` | Zerado a cada 1° de janeiro |
| `No Mês` | Zerado a cada 1° do mês |

---

### Aba: Visual

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| Cor — Fluxo Positivo | Verde `#26a69a` | Cor das barras de entrada |
| Cor — Fluxo Negativo | Vermelho `#ef5350` | Cor das barras de saída |
| Cor — Linha do Acumulado | Branco | Linha de saldo acumulado |
| Espessura da Linha | `2` | 1 = mais fino, 5 = mais grosso |
| Mostrar Histograma | `✓ ativado` | Barras de fluxo diário |
| Colorir Background | `✓ ativado` | Fundo verde/vermelho por zona |

---

### Aba: Média Móvel

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| Mostrar Média Móvel | `✓ ativado` | Linha de média sobre o acumulado |
| Tipo | `EMA` | EMA / SMA / WMA |
| Período | `21` | Janela da média em dias |

> **Interpretação:** quando o acumulado está **acima** da média, o fundo fica
> levemente verde (tendência de entrada). Abaixo = fundo vermelho (saída).

---

### Aba: Tabela de Resumo

| Campo | Padrão | Descrição |
|-------|--------|-----------|
| Mostrar Tabela | `✓ ativado` | Painel com valores no gráfico |
| Posição | `Canto Superior Direito` | Onde aparece a tabela |

**O que a tabela exibe:**

```
┌─────────────────────────────────────┐
│   FLUXO ESTRANGEIRO · IBOV          │
├──────────────┬──────────────────────┤
│ Hoje         │ ▲ +312 mi            │
│ Acumulado    │ ▲ +4,21 bi           │
│ EMA 21d      │ ▲ +3,85 bi           │
│ Posição      │ Acima da média       │
│ Última data  │ 24/06/2026           │
├──────────────┴──────────────────────┤
│ B3 · dadosdemercado.com.br          │
└─────────────────────────────────────┘
```

---

### Aba: Alertas

| Campo | Padrão |
|-------|--------|
| Cruzamento do zero | `✓ ativado` |
| Cruzamento da média | `✓ ativado` |

---

## PASSO 5 — Configurar Alertas

1. Clique com botão direito no indicador → **"Adicionar alerta"**
   (ou `Ctrl + Alt + A`)
2. Em **"Condição"**, selecione **"Fluxo Acumulado — Investidor Estrangeiro IBOV"**
3. Escolha o tipo:

| Alerta disponível | Quando dispara |
|-------------------|---------------|
| `FluxoExt: Acumulado → Positivo` | Saldo acumulado cruza de negativo para positivo |
| `FluxoExt: Acumulado → Negativo` | Saldo acumulado cruza de positivo para negativo |
| `FluxoExt: Acumulado cruzou ACIMA da média` | Linha cruza para cima da EMA/SMA |
| `FluxoExt: Acumulado cruzou ABAIXO da média` | Linha cruza para baixo da EMA/SMA |

4. Configure a expiração e o canal (notificação, email, webhook)
5. Clique em **"Criar"**

---

## PASSO 6 — Atualizar os Dados (rotina diária)

Como o TradingView não acessa URLs externas automaticamente, os dados precisam
ser reimportados periodicamente.

### Com backend rodando (automático via cron):

O backend já coleta os dados às 20h e gera o CSV. Você precisa apenas
reimportar o CSV no TradingView.

**Fluxo de atualização:**
```bash
# 1. Baixar CSV atualizado
curl "https://SEU-DOMINIO/api/v1/fluxo/export.csv" -o fluxo_estrangeiro_novo.csv

# 2. No TradingView: Gerenciar dados → FLUXO_EST_IBOV → Atualizar arquivo
#    Selecionar fluxo_estrangeiro_novo.csv → Confirmar
```

### Sem backend (manual):

1. Acesse [dadosdemercado.com.br/fluxo](https://www.dadosdemercado.com.br/fluxo)
2. Copie os novos registros e adicione ao final do CSV existente
3. Reimporte no TradingView seguindo o Passo 2

> **Dica:** no TradingView, ao reimportar sobre um símbolo existente,
> os dados são **substituídos** (não acumulados). Sempre importe o
> arquivo completo, não apenas os novos registros.

---

## Interpretação do Indicador

```
LEITURA DO GRÁFICO
══════════════════

Histograma (barras):
  ▲ Verde  = entrada líquida de capital estrangeiro no dia
  ▼ Verm.  = saída líquida de capital estrangeiro no dia

Linha branca:
  = Saldo acumulado total (ou YTD / mensal, conforme input)
  Subindo  → fluxo predominantemente comprador
  Caindo   → fluxo predominantemente vendedor

Área entre linha e média:
  Verde translúcido = acumulado acima da média (força)
  Verm. translúcido = acumulado abaixo da média (fraqueza)

Background:
  Verde suave = acumulado positivo no período
  Verm. suave = acumulado negativo no período

SINAIS RELEVANTES
═════════════════
Acumulado cruza ZERO para cima  → potencial entrada de fluxo
Acumulado cruza ZERO para baixo → potencial saída de fluxo
Divergência com IBOV            → atenção a reversões
Acumulado > EMA e IBOV subindo  → tendência confirmada pelo fluxo
```

---

## Solução de Problemas

### "Símbolo não encontrado" no input

**Causa:** o nome digitado no input não confere com o importado.

**Solução:** no input `Símbolo do CSV Importado`, clique no ícone de busca
e procure por `FLUXO_EST_IBOV`. Selecione o resultado com prefixo `SPREADSHEET:`.

---

### Gráfico aparece vazio / sem dados

**Causas possíveis:**

1. **CSV vazio ou mal formatado** — abra o CSV e confirme que as colunas
   têm os nomes exatos: `date,open,high,low,close,volume`

2. **Datas em formato errado** — as datas devem ser `YYYY-MM-DD` (ex: `2024-01-02`).
   Formatos como `02/01/2024` causam falha silenciosa na importação.

3. **Timeframe errado** — o indicador busca dados no timeframe `D` (diário).
   Aplique-o em um gráfico com timeframe diário ou superior.

4. **Símbolo errado no input** — confirme que o campo está preenchido com
   `SPREADSHEET:FLUXO_EST_IBOV` (com o prefixo `SPREADSHEET:`).

---

### Erro de compilação: "Cannot call 'request.security' in local scope"

**Causa:** o código foi modificado e a chamada `request.security()` foi movida
para dentro de um bloco `if` ou função.

**Solução:** restaure o código original — o bloco `[f_close, f_open, f_vol] = request.security(...)`
deve estar no escopo global (sem indentação).

---

### Tabela não aparece

**Causa:** o input `Mostrar Tabela de Resumo` pode estar desativado,
ou o indicador está em escala incompatível.

**Solução:** abra as configurações → aba `Tabela de Resumo` → ative o checkbox.

---

### Valores na tabela mostram "Sem dado"

**Causa:** a última barra do símbolo importado não tem dado para a data atual.

**Situação normal:** o dado da B3 só fica disponível após o fechamento do mercado
(~18h30 BRT). Se importar o CSV antes disso, o dia atual estará ausente —
isso é esperado. O indicador mostrará o último dado disponível.

---

### Histograma e linha em escalas muito diferentes

Se as barras do histograma "esmagam" a linha ou vice-versa:

1. Clique com botão direito na escala do indicador
2. Selecione **"Escala automática"**

Ou ajuste manualmente: clique e arraste a escala para redimensionar.

---

## Atualização Automática via TradingView Pine (Contas Premium/Enterprise)

Para integração direta sem necessidade de reimportar CSV manualmente,
é necessário configurar um **UDF (User-Defined Data Feed)** com a API do projeto:

1. Na área de administração TradingView (acesso broker/Enterprise):
   - Cadastre a URL: `https://SEU-DOMINIO/api/v1/`
   - Defina o símbolo: `FLUXO_EST_IBOV`
   - Tipo: índice, resolução: `1D`

2. No Pine Script, substitua o input do símbolo por:
   ```pine
   i_simbolo = input.symbol("SEU_BROKER:FLUXO_EST_IBOV", ...)
   ```

Documentação oficial: `https://www.tradingview.com/broker-api-docs/`

---

## Referência Rápida

| Ação | Como fazer |
|------|-----------|
| Abrir configurações | Duplo clique no indicador ou ícone ⚙️ |
| Alterar período | Configurações → Fonte de Dados → Período |
| Mover a tabela | Configurações → Tabela → Posição |
| Criar alerta | Botão direito no indicador → Adicionar alerta |
| Reimportar CSV | Gerenciar dados → FLUXO_EST_IBOV → Atualizar |
| Ver valor exato | Passar o mouse sobre o gráfico (tooltip) |
| Remover indicador | Botão direito → Remover |
