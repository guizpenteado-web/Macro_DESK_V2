"""
Gera o arquivo FluxoEstrangeiro_IBOV_FINAL.pine com dados hardcoded.
Execute: python build_pine.py
"""

import csv, os

CSV_PATH = os.path.join(os.path.dirname(__file__), "fluxo_estrangeiro.csv")
OUT_PATH = os.path.join(os.path.dirname(__file__), "FluxoEstrangeiro_IBOV_FINAL.pine")

# ── ler CSV ──────────────────────────────────────────────────────────
rows = []
with open(CSV_PATH, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        y, m, d = r["date"].split("-")
        date_int = int(y) * 10000 + int(m) * 100 + int(d)
        close    = round(float(r["close"]), 2)
        daily    = round(float(r["close"]) - float(r["open"]), 2)
        rows.append((date_int, close, daily))

last_date = str(rows[-1][0])
last_date_fmt = "{}/{}/{}".format(last_date[6:8], last_date[4:6], last_date[:4])

# ── LINHA UNICA por array ─────────────────────────────────────────────
# Pine Script v5 NAO suporta array.from() multi-linha de nenhuma forma.
# Todos os elementos devem estar na mesma linha que array.from(.
def fmt_array(values):
    return ", ".join(str(v) for v in values)

arr_datas = fmt_array([r[0] for r in rows])
arr_acum  = fmt_array([r[1] for r in rows])
arr_dia   = fmt_array([r[2] for r in rows])

# ── template (string literal, NAO f-string, para preservar {{time}}) ─
pine = '''
//@version=5
indicator("Fluxo Acumulado - Investidor Estrangeiro IBOV", shorttitle="FluxoExt", overlay=false, scale=scale.right, max_bars_back=500)

// =====================================================================
// INPUTS
// =====================================================================
GRP_VIS = "Visual"

i_periodo   = input.string("Acumulado Total", "Periodo", options=["Acumulado Total","No Ano (YTD)","No Mes"])
i_cor_pos   = input.color(#26a69a,     "Cor Positivo",        group=GRP_VIS)
i_cor_neg   = input.color(#ef5350,     "Cor Negativo",        group=GRP_VIS)
i_cor_linha = input.color(color.black, "Cor Linha Acumulado", group=GRP_VIS)
i_linha_w   = input.int(2,             "Espessura Linha", minval=1, maxval=5, group=GRP_VIS)
i_hist      = input.bool(true,         "Mostrar Histograma",  group=GRP_VIS)
i_dia_ratio = input.float(0.30, "Escala visual Fluxo Diario (% do acumulado)", minval=0.05, maxval=1.0, step=0.05, group=GRP_VIS)

// =====================================================================
// DADOS HARDCODED  |  B3 via dadosdemercado.com.br
// Ultimo registro : __LAST_DATE__
// Total de registros : __NUM_ROWS__
// Para atualizar: python build_pine.py
// =====================================================================

var int[] DATAS = array.from(__ARR_DATAS__)

var float[] ACUM = array.from(__ARR_ACUM__)

var float[] DIA = array.from(__ARR_DIA__)

// =====================================================================
// LOOKUP: encontrar valor para a barra atual pelo date YYYYMMDD
// =====================================================================
bar_date = year(time, "America/Sao_Paulo") * 10000 + month(time, "America/Sao_Paulo") * 100 + dayofmonth(time, "America/Sao_Paulo")

idx    = array.binary_search(DATAS, bar_date)
f_acum = idx >= 0 ? array.get(ACUM, idx) : float(na)
f_dia  = idx >= 0 ? array.get(DIA,  idx) : float(na)

var float last_acum = na
if not na(f_acum)
    last_acum := f_acum

// =====================================================================
// CALCULOS PERIODICOS
// =====================================================================
var float acum_ytd = 0.0
var float acum_mes = 0.0

eh_novo_ano = not na(time[1]) and year(time)  != year(time[1])
eh_novo_mes = not na(time[1]) and month(time) != month(time[1])

if not na(f_dia)
    if eh_novo_ano
        acum_ytd := 0.0
    if eh_novo_mes
        acum_mes := 0.0
    acum_ytd += f_dia
    acum_mes += f_dia

serie_acum = switch i_periodo
    "No Ano (YTD)" => acum_ytd
    "No Mes"       => acum_mes
    =>               nz(last_acum, na)

cor_dia = nz(f_dia, 0.0) >= 0 ? i_cor_pos : i_cor_neg

// =====================================================================
// PLOTS
// =====================================================================
acum_abs_max = ta.highest(math.abs(nz(serie_acum, 0.0)), 500)
dia_abs_max  = ta.highest(math.abs(nz(f_dia,      0.0)), 500)
dia_scale    = dia_abs_max > 0 ? acum_abs_max * i_dia_ratio / dia_abs_max : 1.0

plot(i_hist and not na(f_dia) ? serie_acum : na, "Saldo Acumulado", style=plot.style_histogram, color=color.new(color.black, 0), display=display.pane)
plot(not na(f_dia) ? f_dia * dia_scale : na, "Fluxo Diario", style=plot.style_columns, color=color.new(cor_dia, 0), display=display.pane)
plot(serie_acum, "Linha Acumulado", color=i_cor_linha, linewidth=i_linha_w, display=display.pane)

hline(0, "Zero", color=color.new(color.gray, 35), linestyle=hline.style_dashed, linewidth=1)
'''.lstrip()

# Substituir placeholders
pine = pine.replace("__LAST_DATE__", last_date_fmt)
pine = pine.replace("__NUM_ROWS__",  str(len(rows)))
pine = pine.replace("__ARR_DATAS__", arr_datas)
pine = pine.replace("__ARR_ACUM__",  arr_acum)
pine = pine.replace("__ARR_DIA__",   arr_dia)

with open(OUT_PATH, "w", encoding="utf-8") as f:
    f.write(pine)

file_size = os.path.getsize(OUT_PATH)
print("Gerado: {}".format(OUT_PATH))
print("Tamanho: {:,} bytes  ({} KB)".format(file_size, file_size // 1024))
print("Registros: {}".format(len(rows)))
print("Ultimo dado: {}".format(last_date_fmt))
