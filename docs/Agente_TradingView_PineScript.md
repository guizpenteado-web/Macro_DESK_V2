# Guia de Construção de Indicadores no TradingView para Agentes de IA

> **Propósito:** Este documento orienta um agente de IA a escrever indicadores funcionais em Pine Script v5 para o TradingView. Contém padrões obrigatórios, exemplos práticos e armadilhas comuns. Leia integralmente antes de gerar qualquer código.

---

## 1. Regras Absolutas do Pine Script v5

Estas regras causam erro de compilação se violadas. Nunca as ignore.

### 1.1 Declaração obrigatória na primeira linha

```pine
//@version=5
indicator("Meu Indicador", overlay=false)
```

- `overlay=true` → plota sobre o gráfico de preço
- `overlay=false` → painel separado abaixo (use para osciladores, fluxo, volume)
- Sempre a **primeira linha executável** do script

### 1.2 Tipos são inferidos — não declare explicitamente no corpo

```pine
// CORRETO
minhaVar = close * 1.05

// ERRADO — Pine Script não usa anotações de tipo em variáveis locais
float minhaVar = close * 1.05  // causa erro
```

Exceção: parâmetros de função e `var`/`varip` aceitam tipo opcional.

### 1.3 `var` vs `varip` — persistência entre barras

```pine
// var: persiste entre barras, inicializa apenas na barra 0
var float acumulado = 0.0
acumulado += close  // soma todas as barras até a atual

// varip: persiste e atualiza em tempo real (intrabar, tick-by-tick)
varip int contagem = 0
contagem += 1
```

### 1.4 Acesso a barras anteriores com `[]`

```pine
close[0]   // barra atual (mesmo que close)
close[1]   // barra anterior
close[10]  // 10 barras atrás
high[1] - low[1]  // range da barra anterior
```

### 1.5 `na` é o valor ausente — sempre verifique antes de usar

```pine
// Checar ausência
if na(close[1])
    label.new(bar_index, high, "Primeira barra")

// Substituir na por zero
valor = na(minhaSerie) ? 0.0 : minhaSerie

// Função nativa
valorSeguro = nz(minhaSerie, 0.0)  // equivalente ao acima
```

---

## 2. Estrutura Padrão de um Indicador

Todo indicador bem construído segue esta ordem:

```pine
//@version=5
indicator("Nome do Indicador", shorttitle="ABREV", overlay=false, max_bars_back=500)

// ── 1. INPUTS ──────────────────────────────────────────────────────────
periodo   = input.int(14,    title="Período",    minval=1, maxval=200)
cor_alta  = input.color(color.teal,  title="Cor Alta")
cor_baixa = input.color(color.red,   title="Cor Baixa")
mostrar   = input.bool(true, title="Mostrar Linha")

// ── 2. CÁLCULOS ────────────────────────────────────────────────────────
media     = ta.sma(close, periodo)
delta     = close - close[1]
positivo  = delta >= 0

// ── 3. PLOTS ───────────────────────────────────────────────────────────
plot(mostrar ? media : na, title="Média", color=cor_alta, linewidth=2)
plot(delta, style=plot.style_histogram, color=positivo ? cor_alta : cor_baixa)
hline(0, color=color.gray, linestyle=hline.style_dashed)

// ── 4. ELEMENTOS VISUAIS (labels, tables, shapes) ──────────────────────
var table tbl = table.new(position.top_right, 2, 3, bgcolor=color.new(color.black, 70))

if barstate.islast
    table.cell(tbl, 0, 0, "Último valor", text_color=color.white, text_size=size.small)
    table.cell(tbl, 1, 0, str.tostring(media, "#,##0.00"), text_color=cor_alta, text_size=size.small)
```

---

## 3. Inputs — Todos os Tipos Disponíveis

```pine
// Inteiro com limites
n = input.int(20, title="Período", minval=1, maxval=500, step=1)

// Float
fator = input.float(1.5, title="Fator", minval=0.1, maxval=10.0, step=0.1)

// Booleano (checkbox)
ativo = input.bool(true, title="Ativar")

// String com opções fixas (dropdown)
tipo = input.string("EMA", title="Tipo de Média", options=["SMA","EMA","WMA","VWMA"])

// Cor
cor = input.color(#26a69a, title="Cor da Linha")

// Símbolo (abre buscador de ativos)
ativo2 = input.symbol("BMFBOVESPA:IBOV", title="Ativo de Referência")

// Timeframe (dropdown de periodicidades)
tf = input.timeframe("D", title="Timeframe")

// Source (dropdown: close, open, high, low, hl2, hlc3, ohlc4)
fonte = input.source(close, title="Fonte")
```

---

## 4. Plots — Todos os Estilos

```pine
// Linha simples
plot(close, title="Preço", color=color.white, linewidth=1, style=plot.style_line)

// Linha tracejada
plot(media, style=plot.style_linebr)  // quebra onde há na

// Histograma (barras verticais — ideal para fluxo/volume)
plot(delta, style=plot.style_histogram, color=delta >= 0 ? color.teal : color.red, linewidth=4)

// Área preenchida
p1 = plot(banda_sup, color=color.new(color.blue, 80))
p2 = plot(banda_inf, color=color.new(color.blue, 80))
fill(p1, p2, color=color.new(color.blue, 90), title="Banda")

// Colunas (barras de cima para baixo a partir do zero)
plot(volume, style=plot.style_columns, color=color.new(color.teal, 60))

// Stepline
plot(rsi, style=plot.style_stepline, color=color.orange)

// Círculos em pontos específicos
plot(condicao ? low - ta.atr(14) : na, style=plot.style_circles, color=color.yellow, linewidth=3)
```

---

## 5. Linhas Horizontais Fixas — `hline`

```pine
hline(0,   "Zero",       color=color.gray,  linestyle=hline.style_dashed,  linewidth=1)
hline(100, "Teto",       color=color.red,   linestyle=hline.style_solid,   linewidth=2)
hline(50,  "Meio",       color=color.white, linestyle=hline.style_dotted,  linewidth=1)
hline(-100,"Suporte",    color=color.green, linestyle=hline.style_dashed)
```

---

## 6. Cores — Padrões e Transparência

```pine
// Cores nativas
color.red, color.green, color.blue, color.white, color.black
color.gray, color.yellow, color.orange, color.purple, color.teal
color.lime, color.maroon, color.navy, color.olive, color.silver

// Hex direto
#26a69a   // verde TradingView
#ef5350   // vermelho TradingView

// Transparência (0 = opaco, 100 = invisível)
color.new(color.red, 80)   // vermelho 80% transparente
color.new(#26a69a, 0)      // teal totalmente opaco

// Cor condicional inline
cor = condicao ? color.teal : color.red

// Cor com transparência condicional
cor = valor > 0 ? color.new(color.teal, 20) : color.new(color.red, 20)

// Gradiente entre duas cores
cor_grad = color.from_gradient(valor, 0, 100, color.red, color.green)
```

---

## 7. Tabelas — Elemento Visual Essencial

Tabelas são o painel de informações fixo na tela. Use `var` para criar uma vez.

```pine
// Criar tabela (var = cria apenas na primeira barra)
var table painel = table.new(
    position   = position.top_right,  // top_left, bottom_right, bottom_left, middle_right...
    columns    = 2,
    rows       = 5,
    bgcolor    = color.new(color.black, 70),
    border_color = color.new(color.gray, 50),
    border_width = 1,
    frame_color  = color.new(color.gray, 30),
    frame_width  = 1
)

// Preencher células apenas na última barra visível
if barstate.islast
    // Cabeçalho
    table.cell(painel, 0, 0,
        text       = "INDICADOR XYZ",
        text_color = color.white,
        text_size  = size.small,
        bgcolor    = color.new(color.navy, 40),
        text_halign = text.align_center
    )
    table.merge_cells(painel, 0, 0, 1, 0)  // mesclar colunas 0 e 1 da linha 0

    // Linha de dado
    table.cell(painel, 0, 1, "Valor",   text_color=color.gray,  text_size=size.tiny)
    table.cell(painel, 1, 1,
        text       = str.tostring(close, "#,##0.00"),
        text_color = close > close[1] ? color.teal : color.red,
        text_size  = size.small
    )
```

**Posições disponíveis para tabela:**
`position.top_left` · `position.top_center` · `position.top_right`
`position.middle_left` · `position.middle_center` · `position.middle_right`
`position.bottom_left` · `position.bottom_center` · `position.bottom_right`

**Tamanhos de texto:** `size.tiny` · `size.small` · `size.normal` · `size.large` · `size.huge`

---

## 8. Labels e Linhas Dinâmicas

```pine
// Label em pontos específicos do gráfico
if ta.crossover(close, media)
    label.new(
        x         = bar_index,
        y         = low - ta.atr(14),
        text      = "▲ Cruzamento",
        color     = color.teal,
        textcolor = color.white,
        style     = label.style_label_up,  // label_down, label_left, label_right, arrowup...
        size      = size.small
    )

// Linha entre dois pontos
if condicao
    line.new(
        x1    = bar_index[5],
        y1    = high[5],
        x2    = bar_index,
        y2    = high,
        color = color.yellow,
        width = 2,
        style = line.style_dashed  // solid, dotted
    )
```

---

## 9. Dados Externos — `request.security()`

### 9.1 Buscar dado de outro ativo ou timeframe

```pine
// Preço de fechamento do IBOV no diário (independente do TF do gráfico)
ibov_close = request.security("BMFBOVESPA:IBOV", "D", close)

// Volume do dólar futuro
dol_vol = request.security("BMFBOVESPA:DOL1!", "D", volume)

// Média móvel calculada no TF diário
ibov_media = request.security("BMFBOVESPA:IBOV", "D", ta.sma(close, 20))

// Múltiplos valores em uma chamada (mais eficiente)
[ibov_max, ibov_min, ibov_vol] = request.security(
    "BMFBOVESPA:IBOV", "D",
    [high, low, volume]
)
```

### 9.2 Buscar dado de símbolo customizado importado

Quando dados externos (ex: fluxo estrangeiro) são importados no TradingView
como planilha/CSV com símbolo customizado:

```pine
// Símbolo importado via "Adicionar dados" → "Carregar dados de arquivo"
simbolo_fluxo = input.symbol("SPREADSHEET:FLUXO_EST_IBOV", title="Símbolo de Fluxo")

// Buscar campos OHLCV do símbolo importado
[fluxo_acum, fluxo_dia] = request.security(
    symbol     = simbolo_fluxo,
    timeframe  = "D",
    expression = [close, open]  // close = saldo acumulado, open = saldo do dia
)
```

### 9.3 Regra crítica: `request.security()` não aceita URL HTTP

```pine
// ISSO NÃO FUNCIONA — Pine Script não faz chamadas HTTP
dados = request.security("https://minha-api.com/dados", "D", close)  // ERRO

// O CORRETO é usar um símbolo registrado no TradingView
// (nativo, broker, ou dado importado como planilha)
```

---

## 10. Formatação de Strings

```pine
// Número com casas decimais
str.tostring(1234567.89, "#,##0.00")   // "1,234,567.89"
str.tostring(0.0045,     "#.####")     // "0.0045"
str.tostring(valor,      "0.00%")      // formato percentual: 0.05 → "5.00%"

// Inteiro
str.tostring(math.round(valor))

// Data/hora
str.format_time(time, "dd/MM/yyyy")           // "24/06/2026"
str.format_time(time, "dd/MM/yyyy HH:mm")     // com hora
str.tostring(timenow, "yyyy-MM-dd")            // data atual

// Concatenação
texto = "Valor: " + str.tostring(close, "#,##0.00") + " | Vol: " + str.tostring(volume)

// str.format (mais legível para múltiplos campos)
texto = str.format("Preço: {0,number,#,##0.00}  Vol: {1,number,#,##0}", close, volume)
```

---

## 11. Funções Técnicas Nativas (`ta.*`)

```pine
// Médias
ta.sma(close, 20)          // Simples
ta.ema(close, 20)          // Exponencial
ta.wma(close, 20)          // Ponderada
ta.vwma(close, volume, 20) // Por volume
ta.rma(close, 20)          // Wilder (usada no RSI)

// Osciladores
ta.rsi(close, 14)
[macd, signal, hist] = ta.macd(close, 12, 26, 9)
ta.stoch(close, high, low, 14)
ta.cci(high, low, close, 20)

// Volatilidade
ta.atr(14)
[upper, basis, lower] = ta.bb(close, 20, 2.0)

// Cruzamentos
ta.crossover(serie1, serie2)   // serie1 cruzou ACIMA de serie2
ta.crossunder(serie1, serie2)  // serie1 cruzou ABAIXO de serie2
ta.cross(serie1, serie2)       // qualquer cruzamento

// Máximo/mínimo em janela
ta.highest(high, 50)
ta.lowest(low, 50)
ta.highestbars(high, 50)  // quantas barras atrás foi o máximo
ta.lowestbars(low, 50)

// Outros
ta.change(close)          // close - close[1]
ta.change(close, 5)       // close - close[5]
ta.cum(delta)             // soma acumulada (equivalente a var + +=)
ta.sum(close, 20)         // soma da janela
```

---

## 12. Lógica Condicional — Sintaxe Correta

```pine
// If/else em linha (ternário)
cor = valor > 0 ? color.teal : color.red

// If/else em bloco — INDENTAÇÃO É OBRIGATÓRIA (4 espaços ou 1 tab)
if valor > 0
    cor := color.teal
    label.new(bar_index, high, "Alta")
else if valor < -100
    cor := color.red
else
    cor := color.gray

// Switch/match (Pine Script v5.2+)
resultado = switch tipo
    "SMA" => ta.sma(close, n)
    "EMA" => ta.ema(close, n)
    "WMA" => ta.wma(close, n)
    =>       ta.ema(close, n)  // default
```

---

## 13. `barstate` — Controle de Execução por Barra

```pine
barstate.isfirst      // true apenas na primeira barra histórica
barstate.islast       // true na última barra (a mais recente visível)
barstate.isrealtime   // true em dados ao vivo (não histórico)
barstate.ishistory    // true em dados históricos
barstate.isconfirmed  // true quando a barra fechou definitivamente
barstate.isnew        // true na primeira atualização de uma nova barra
```

**Padrão obrigatório para tabelas:** sempre use `if barstate.islast` para preencher células — caso contrário a tabela é reescrita em cada barra e fica lenta.

---

## 14. Background e Destaque de Zonas

```pine
// Colorir fundo do painel por condição
bgcolor(
    condicao_alta ? color.new(color.teal, 90) :
    condicao_baixa ? color.new(color.red, 90) : na,
    title = "Zona de Tendência"
)

// Destacar barra específica
barcolor(close > open ? color.teal : color.red)  // só funciona com overlay=true
```

---

## 15. Alerta — `alertcondition`

```pine
alertcondition(
    condition = ta.crossover(close, media),
    title     = "Cruzamento de Alta",
    message   = "{{ticker}} cruzou acima da média em {{close}}"
)
```

---

## 16. Exemplo Completo — Indicador de Fluxo Acumulado

Este é o padrão de referência para o indicador de Fluxo do Investidor Estrangeiro no IBOVESPA. Use como base para qualquer indicador de fluxo/acumulado.

```pine
//@version=5
indicator(
    title         = "Fluxo Acumulado — Investidor Estrangeiro IBOV",
    shorttitle    = "FluxoExt",
    overlay       = false,
    scale         = scale.right,
    max_bars_back = 500
)

// ══════════════════════════════════════════════
// INPUTS
// ══════════════════════════════════════════════
i_simbolo   = input.symbol("SPREADSHEET:FLUXO_EST_IBOV",
                  title="Símbolo Importado (CSV)")
i_cor_pos   = input.color(#26a69a, title="Cor — Fluxo Positivo")
i_cor_neg   = input.color(#ef5350, title="Cor — Fluxo Negativo")
i_cor_linha = input.color(color.white, title="Cor — Linha Acumulado")
i_linha_w   = input.int(2,     title="Espessura da Linha", minval=1, maxval=5)
i_hist      = input.bool(true,  title="Mostrar Histograma Diário")
i_bg        = input.bool(true,  title="Colorir Background por Zona")
i_tabela    = input.bool(true,  title="Mostrar Tabela de Resumo")
i_periodo   = input.string("Acumulado Total", title="Período",
                  options=["Acumulado Total","Acumulado Ano","Acumulado Mês"])

// ══════════════════════════════════════════════
// DADOS EXTERNOS
// ══════════════════════════════════════════════
// Convenção do CSV importado:
//   close = saldo acumulado (R$ milhões)
//   open  = saldo do dia (R$ milhões)
[f_acumulado, f_dia] = request.security(
    symbol     = i_simbolo,
    timeframe  = "D",
    expression = [close, open],
    gaps       = barmerge.gaps_on   // preserva na onde não há dado
)

// ══════════════════════════════════════════════
// CÁLCULOS
// ══════════════════════════════════════════════
// Saldo acumulado YTD (recalculado dentro do Pine)
var float acum_ytd = 0.0
var float acum_mes = 0.0

eh_novo_ano = year(time) != year(time[1])
eh_novo_mes = month(time) != month(time[1])

if not na(f_dia)
    // Reiniciar acumulados em virada de período
    if eh_novo_ano
        acum_ytd := 0.0
    if eh_novo_mes
        acum_mes := 0.0
    acum_ytd += nz(f_dia, 0.0)
    acum_mes += nz(f_dia, 0.0)

// Selecionar série conforme input
serie_acum = switch i_periodo
    "Acumulado Ano"  => acum_ytd
    "Acumulado Mês"  => acum_mes
    =>                  f_acumulado  // Total histórico vindo do CSV

// Cores condicionais
cor_dia  = nz(f_dia, 0) >= 0 ? i_cor_pos : i_cor_neg
cor_acum = nz(serie_acum, 0) >= 0 ? i_cor_pos : i_cor_neg

// ══════════════════════════════════════════════
// PLOTS
// ══════════════════════════════════════════════

// Histograma de fluxo diário
plot(
    series    = i_hist ? f_dia : na,
    title     = "Fluxo Diário",
    style     = plot.style_histogram,
    color     = color.new(cor_dia, 30),
    linewidth = 4
)

// Linha do saldo acumulado
plot(
    series    = serie_acum,
    title     = "Saldo Acumulado",
    color     = i_cor_linha,
    linewidth = i_linha_w,
    style     = plot.style_line
)

// Linha zero
hline(0, "Zero", color=color.new(color.gray, 50), linestyle=hline.style_dashed, linewidth=1)

// Background por zona de tendência
bgcolor(
    i_bg and nz(serie_acum) > 0 ? color.new(i_cor_pos, 93) :
    i_bg and nz(serie_acum) < 0 ? color.new(i_cor_neg, 93) : na,
    title = "Background Zona"
)

// ══════════════════════════════════════════════
// TABELA DE RESUMO
// ══════════════════════════════════════════════
var table tbl = table.new(
    position     = position.top_right,
    columns      = 2,
    rows         = 5,
    bgcolor      = color.new(color.black, 65),
    border_color = color.new(color.gray, 60),
    border_width = 1
)

f_fmt(v) =>
    // Converte R$ milhões → "1,23 bi" ou "456 mi"
    abs_v = math.abs(v)
    sinal = v >= 0 ? "+" : "-"
    abs_v >= 1000 ?
        sinal + str.tostring(abs_v / 1000, "#,##0.0") + " bi" :
        sinal + str.tostring(abs_v, "#,##0") + " mi"

if barstate.islast and i_tabela
    // Cabeçalho
    table.cell(tbl, 0, 0, "Fluxo Estrangeiro · IBOV",
        text_color  = color.white,
        text_size   = size.small,
        bgcolor     = color.new(color.navy, 50),
        text_halign = text.align_center
    )
    table.merge_cells(tbl, 0, 0, 1, 0)

    // Linha 1 — Hoje
    table.cell(tbl, 0, 1, "Hoje",
        text_color = color.new(color.gray, 20), text_size = size.tiny)
    table.cell(tbl, 1, 1,
        not na(f_dia) ? f_fmt(f_dia) : "—",
        text_color  = cor_dia,
        text_size   = size.small,
        text_halign = text.align_right
    )

    // Linha 2 — Acumulado selecionado
    label_acum = i_periodo == "Acumulado Ano" ? "No Ano" :
                 i_periodo == "Acumulado Mês" ? "No Mês" : "Acumulado"
    table.cell(tbl, 0, 2, label_acum,
        text_color = color.new(color.gray, 20), text_size = size.tiny)
    table.cell(tbl, 1, 2,
        not na(serie_acum) ? f_fmt(serie_acum) : "—",
        text_color  = cor_acum,
        text_size   = size.small,
        text_halign = text.align_right
    )

    // Linha 3 — Última atualização
    table.cell(tbl, 0, 3, "Última data",
        text_color = color.new(color.gray, 20), text_size = size.tiny)
    table.cell(tbl, 1, 3,
        str.format_time(time, "dd/MM/yyyy"),
        text_color  = color.new(color.gray, 30),
        text_size   = size.tiny,
        text_halign = text.align_right
    )

    // Linha 4 — Fonte
    table.cell(tbl, 0, 4, "Fonte: dadosdemercado.com.br",
        text_color  = color.new(color.gray, 60),
        text_size   = size.tiny
    )
    table.merge_cells(tbl, 0, 4, 1, 4)

// ══════════════════════════════════════════════
// ALERTAS
// ══════════════════════════════════════════════
alertcondition(
    ta.crossover(serie_acum, 0),
    title   = "Acumulado cruzou para positivo",
    message = "Fluxo estrangeiro IBOV: acumulado tornou-se positivo em {{time}}"
)
alertcondition(
    ta.crossunder(serie_acum, 0),
    title   = "Acumulado cruzou para negativo",
    message = "Fluxo estrangeiro IBOV: acumulado tornou-se negativo em {{time}}"
)
```

---

## 17. Erros Comuns e Como Evitá-los

| Erro | Causa | Solução |
|------|-------|---------|
| `Cannot call 'request.security' in local scope` | Chamada dentro de `if` ou função | Mover para escopo global |
| `Cannot use 'series' argument` | Passar série onde se espera valor simples | Usar `ta.valuewhen()` ou indexar com `[0]` |
| `Undeclared identifier` | Variável usada antes de ser declarada | Declarar antes do primeiro uso |
| `Loop is too long` | `for`/`while` com muitas iterações | Usar funções nativas `ta.*` no lugar de loops |
| `The plot index...is out of bounds` | Mais de 64 chamadas `plot()` | Reduzir número de plots |
| `Cannot modify read-only variable` | Tentar reatribuir variável sem `:=` | Usar `:=` para reatribuição: `x := x + 1` |
| `'na' cannot be used as a boolean` | Série com `na` em condição `if` | Envolver com `not na(x) and x > 0` |

---

## 18. Limitações do TradingView que o Agente Deve Conhecer

1. **Sem acesso a URLs externas:** `request.security()` só aceita símbolos registrados no TradingView. Dados de APIs externas precisam ser importados como CSV ou via UDF broker.

2. **Máximo de 64 plots** por indicador (contando `plot()`, `plotshape()`, `plotchar()`).

3. **Máximo de 500 labels/lines** renderizados simultaneamente (os mais antigos somem).

4. **`request.security()` não pode estar dentro de blocos condicionais** (`if`, `for`, funções definidas pelo usuário que contenham lógica complexa).

5. **Funções definidas pelo usuário não podem conter `var`** — use no escopo global.

6. **Pine Script é single-threaded** — não há paralelismo, callbacks, ou timers.

7. **Cálculos retroativos (lookahead):** `request.security(..., lookahead=barmerge.lookahead_on)` pode causar "pinturas" futuras. Use apenas para dados que não mudam (ex: data de dividendo já fixada).

8. **Tamanho máximo do script:** ~65 mil caracteres.

---

## 19. Checklist Antes de Publicar o Código

- [ ] Primeira linha é `//@version=5`
- [ ] `indicator()` tem `title`, `shorttitle` e `overlay` definidos
- [ ] Todo `request.security()` está no escopo global
- [ ] Tabelas usam `var` na declaração e `barstate.islast` no preenchimento
- [ ] Sem declaração de tipo em variáveis locais (`float x = ...` → `x = ...`)
- [ ] Reatribuições usam `:=`, não `=`
- [ ] `na` é tratado com `nz()` ou `not na(x)` antes de operações aritméticas
- [ ] Cores condicionais definidas como variável antes de usar em `plot()`
- [ ] Alertas com mensagens claras incluindo `{{ticker}}` e `{{time}}`
- [ ] Código compilado sem erros no Pine Editor antes de salvar

---

## 20. Referências Oficiais

- Pine Script v5 Language Reference: `https://www.tradingview.com/pine-script-reference/v5/`
- Pine Script User Manual v5: `https://www.tradingview.com/pine-script-docs/en/v5/`
- Import custom data (CSV/Spreadsheet): `https://www.tradingview.com/support/solutions/43000605432/`
- User-Defined Feeds (UDF): `https://www.tradingview.com/broker-api-docs/`
