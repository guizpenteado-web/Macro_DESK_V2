"""
Gerador do dashboard HTML com Plotly.
Produz arquivo standalone que pode ser aberto diretamente no navegador.
"""
from __future__ import annotations
import json
import math
from datetime import datetime
from pathlib import Path

import pandas as pd


def _safe_list(series: pd.Series, decimals: int = 1) -> list:
    """Converte NaN → None para que json.dumps produza null (gap no Plotly)."""
    lst = series.round(decimals).tolist()
    return [None if (v is None or (isinstance(v, float) and math.isnan(v))) else v for v in lst]

from app.config.settings import settings
from app.database.connection import engine
from app.utils.logger import logger


# Mapeamento setor → lista de tickers (fallback se DB estiver vazio)
_SECTORS_FALLBACK: dict[str, list[str]] = {
    "IFNC": ["AXIA3","B3SA3","BBAS3","BBDC3","BBDC4","BBSE3","BPAC11","BRAP4","CXSE3","ITSA4","ITUB4","PSSA3","SANB11"],
    "IEEX": ["AURE3","CEAB3","CMIG4","CPFE3","CPLE3","EGIE3","ENEV3","ENGI11","EQTL3","ISAE4","TAEE11"],
    "IMOB": ["ALOS3","CURY3","CYRE3","DIRR3","IGTI11","MRVE3","MULT3","SMFT3"],
    "ICON": ["ABEV3","ASAI3","AZZA3","BEEF3","CSAN3","HYPE3","LREN3","MGLU3","NATU3","RADL3","RENT3","SLCE3","UGPA3","VBBR3","VIVA3","YDUQ3"],
    "IMAT": ["BRAV3","BRKM5","CMIN3","CSNA3","GGBR4","GOAU4","KLBN11","PETR3","PETR4","PRIO3","RECV3","SUZB3","USIM5","VALE3"],
    "UTIL": ["CSMG3","SBSP3"],
    "SMALL":["COGN3","FLRY3","HAPV3","MOTV3","RDOR3"],
    "INDX": ["WEGE3","RAIL3","EMBR3","EMBJ3","TGMA3","CMIN3","POMO4","VAMO3","ROMI3","FRAS3","CSNA3","GGBR4","GOAU4","USIM5"],
    "IDIV": ["BBAS3","BBDC3","BBDC4","BEEF3","CMIG4","CPFE3","EGIE3","ENGI11","EQTL3","ISAE4","ITSA4","ITUB4","KLBN11","PETR3","PETR4","PSSA3","SANB11","TAEE11","TIMS3","VALE3","VIVT3","BBSE3","CSMG3","WEGE3"],
    "IBLV": ["ABEV3","AURE3","BBSE3","CMIG4","CPFE3","CPLE3","CSMG3","CXSE3","EGIE3","ENGI11","EQTL3","ISAE4","ITSA4","KLBN11","PSSA3","SBSP3","TAEE11","TIMS3","VIVT3","WEGE3"],
}
_TICKER_SECTOR_FALLBACK: dict[str, str] = {
    t: s for s, tickers in _SECTORS_FALLBACK.items() for t in tickers
}

# Ordem de prioridade para setor primario (ticker pode estar em multiplos indices)
_SECTOR_PRIORITY = ["IFNC","IEEX","IMOB","ICON","IMAT","UTIL","SMLL","INDX","IDIV","IBLV"]
_ALL_SECTOR_CODES = "'IFNC','IEEX','IMOB','ICON','IMAT','UTIL','SMLL','INDX','IDIV','IBLV'"
# B3 usa "SMLL" para Small Cap; exibimos como "SMALL" na interface
_SECTOR_ALIAS = {"SMLL": "SMALL"}


def _load_sector_map() -> dict[str, str]:
    """Carrega {ticker: label_setor_primario} da tabela index_components."""
    try:
        df = pd.read_sql(
            f"SELECT ticker, index_code FROM index_components WHERE index_code IN ({_ALL_SECTOR_CODES})",
            engine,
        )
        if df.empty:
            return _TICKER_SECTOR_FALLBACK
        priority = {c: i for i, c in enumerate(_SECTOR_PRIORITY)}
        df["pri"] = df["index_code"].map(priority).fillna(99)
        df = df.sort_values("pri").drop_duplicates(subset="ticker", keep="first")
        df["display"] = df["index_code"].map(lambda x: _SECTOR_ALIAS.get(x, x))
        return dict(zip(df["ticker"], df["display"]))
    except Exception:
        return _TICKER_SECTOR_FALLBACK


def _load_sector_groups() -> dict[str, set[str]]:
    """Carrega {ticker: {todos os indices a que pertence}} para filtragem multi-indice."""
    try:
        df = pd.read_sql(
            f"SELECT ticker, index_code FROM index_components WHERE index_code IN ({_ALL_SECTOR_CODES})",
            engine,
        )
        result: dict[str, set[str]] = {}
        for _, row in df.iterrows():
            t = row["ticker"]
            code = row["index_code"]
            display = _SECTOR_ALIAS.get(code, code)
            result.setdefault(t, set()).add(display)
        return result
    except Exception:
        return {}


def _color_pct(pct: float) -> str:
    if pct >= 70: return "#22c55e"
    if pct >= 50: return "#f0b429"
    if pct >= 30: return "#d97706"
    return "#f05a5a"


def _rsi_zone(rsi_val) -> str:
    try:
        v = float(rsi_val)
    except (TypeError, ValueError):
        return '<span class="pill neutral">-</span>'
    if v > 70:
        return '<span class="pill overbought">SOBCOMPRADO</span>'
    if v < 30:
        return '<span class="pill oversold">SOBREVENDIDO</span>'
    return '<span class="pill neutral">NEUTRO</span>'


def _rsi_bar(rsi_val) -> str:
    try:
        v = max(0.0, min(100.0, float(rsi_val)))
    except (TypeError, ValueError):
        return "—"
    if v > 70:
        color = "#f05a5a"
    elif v < 30:
        color = "#22c55e"
    else:
        color = "#f0b429"
    pct = int(v)
    return (
        f'<div style="display:flex;align-items:center;gap:8px">'
        f'<div style="flex:1;background:rgba(255,255,255,0.04);border-radius:4px;height:5px;overflow:hidden">'
        f'<div style="width:{pct}%;background:{color};height:100%;opacity:.8"></div></div>'
        f'<span style="color:{color};font-size:11px;min-width:32px;font-family:\'DM Mono\',monospace">{v:.1f}</span>'
        f'</div>'
    )


def _sma_cell(close_val, sma_val, period: str) -> str:
    try:
        c   = float(close_val)
        s   = float(sma_val)
        pct = (c - s) / s * 100
        cls   = "acima"  if pct >= 0 else "abaixo"
        arrow = "▲"      if pct >= 0 else "▼"
        sign  = "+"      if pct >= 0 else ""
        return (
            f'<div style="display:flex;flex-direction:column;align-items:flex-start;gap:2px">'
            f'<span class="pill {cls}">{arrow} SMA{period} &nbsp;{sign}{pct:.1f}%</span>'
            f'<span style="color:#3a5060;font-size:10px;font-family:\'DM Mono\',monospace">{s:,.0f}</span>'
            f'</div>'
        )
    except Exception:
        return f'<span class="pill na">SMA{period} —</span>'


def _score_bar(row) -> str:
    score = sum([
        bool(row.get("above_sma21")),
        bool(row.get("above_sma50")),
        bool(row.get("above_sma200")),
    ])
    colors = {0: "#f05a5a", 1: "#d97706", 2: "#f0b429", 3: "#22c55e"}
    labels = {0: "BAIXISTA", 1: "FRACO", 2: "FORTE", 3: "TOURO"}
    glows  = {0: "rgba(240,90,90,.22)", 1: "rgba(217,119,6,.22)",
              2: "rgba(240,180,41,.22)", 3: "rgba(34,197,94,.22)"}
    c = colors[score]
    dots = "".join([
        f'<span style="width:14px;height:14px;border-radius:50%;display:inline-block;'
        f'background:{c if i < score else "transparent"};'
        f'border:2px solid {c if i < score else "#484f58"};'
        f'{"box-shadow:0 0 6px " + glows[score] if i < score else ""}"></span>'
        for i in range(3)
    ])
    return (
        f'<div style="display:flex;flex-direction:column;align-items:flex-start;gap:5px;min-width:100px">'
        f'<div style="display:flex;gap:5px">{dots}</div>'
        f'<span style="color:{c};font-size:10px;font-weight:700;letter-spacing:.8px;text-transform:uppercase">{score}/3 {labels[score]}</span>'
        f'</div>'
    )


def _load_breadth() -> pd.DataFrame:
    return pd.read_sql(
        "SELECT * FROM breadth ORDER BY date DESC LIMIT 2520", engine
    )


def _load_ibov() -> tuple[list[str], list[float]]:
    df = pd.read_sql(
        "SELECT date, close FROM prices WHERE ticker='IBOV' ORDER BY date",
        engine,
    )
    if df.empty:
        return [], []
    df["date"] = pd.to_datetime(df["date"])
    return df["date"].dt.strftime("%Y-%m-%d").tolist(), df["close"].round(0).tolist()


def _load_index_breadth() -> dict:
    """Retorna {index_code: {dates, sma200, sma50, sma21, rsi, rsi_overbought}} para o JS."""
    try:
        df = pd.read_sql(
            "SELECT * FROM index_breadth ORDER BY index_code, date", engine
        )
        if df.empty:
            return {}
        result = {}
        for code, g in df.groupby("index_code"):
            g = g.sort_values("date")
            result[code] = {
                "dates":  g["date"].astype(str).tolist(),
                "sma200": g["pct_sma200"].fillna(0).round(1).tolist(),
                "sma50":  g["pct_sma50"].fillna(0).round(1).tolist(),
                "sma21":  g["pct_sma21"].fillna(0).round(1).tolist(),
                "rsi":    g["pct_rsi_oversold"].fillna(0).round(1).tolist(),
                "rsi_overbought": g["pct_rsi_overbought"].fillna(0).round(1).tolist(),
            }
        return result
    except Exception:
        return {}


def _load_latest_indicators() -> pd.DataFrame:
    """
    Carrega o indicador mais recente por ticker.
    Inclui: (1) ativos ativos do IBOV e (2) todos os tickers dos indices de setor.
    """
    return pd.read_sql(
        f"""
        SELECT i.ticker, i.date, i.close, i.sma21, i.sma50, i.sma200,
               i.above_sma21, i.above_sma50, i.above_sma200,
               i.rsi14, i.above_rsi70, i.below_rsi30,
               a.name, a.weight, a.is_active,
               COALESCE(a.weight, (
                   SELECT MAX(ic2.weight) FROM index_components ic2
                   WHERE ic2.ticker = i.ticker
               )) AS liq_score
        FROM indicators i
        LEFT JOIN assets a ON a.ticker = i.ticker
        WHERE i.date = (SELECT MAX(date) FROM indicators WHERE ticker = i.ticker)
          AND (
            a.is_active = 1
            OR i.ticker IN (
              SELECT DISTINCT ticker FROM index_components
              WHERE index_code IN ({_ALL_SECTOR_CODES})
            )
          )
        ORDER BY liq_score DESC NULLS LAST, i.ticker
        """,
        engine,
    )


def generate_dashboard() -> Path:
    breadth = _load_breadth()
    ind = _load_latest_indicators()

    if breadth.empty:
        logger.warning("Sem dados de breadth. Calcule os indicadores primeiro.")
        return settings.dashboard_output

    latest = breadth.iloc[0]
    b_chart = breadth.sort_values("date")
    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    dates_str = b_chart["date"].astype(str).tolist()

    sma_traces = [
        {"name": "% Acima SMA21",  "y": b_chart["pct_sma21"].round(1).tolist(),  "color": "#00BFFF"},
        {"name": "% Acima SMA50",  "y": b_chart["pct_sma50"].round(1).tolist(),  "color": "#FFD700"},
        {"name": "% Acima SMA200", "y": b_chart["pct_sma200"].round(1).tolist(), "color": "#FF6B6B"},
    ]

    rsi_oversold_y   = b_chart["pct_rsi_oversold"].fillna(0).round(1).tolist()
    rsi_overbought_y = b_chart["pct_rsi_overbought"].fillna(0).round(1).tolist()
    ibov_dates, ibov_prices = _load_ibov()

    p21  = float(latest["pct_sma21"])
    p50  = float(latest["pct_sma50"])
    p200 = float(latest["pct_sma200"])
    total = int(latest["total_assets"])
    last_date = str(latest["date"])

    sma_cards_html = f"""
    <div class="cards">
      <div class="card">
        <div class="val" style="color:{_color_pct(p21)}">{p21:.1f}%</div>
        <div class="lbl">Acima da SMA21</div>
        <div class="sub2">{int(latest["above_sma21"])} de {total} ativos</div>
      </div>
      <div class="card">
        <div class="val" style="color:{_color_pct(p50)}">{p50:.1f}%</div>
        <div class="lbl">Acima da SMA50</div>
        <div class="sub2">{int(latest["above_sma50"])} de {total} ativos</div>
      </div>
      <div class="card">
        <div class="val" style="color:{_color_pct(p200)}">{p200:.1f}%</div>
        <div class="lbl">Acima da SMA200</div>
        <div class="sub2">{int(latest["above_sma200"])} de {total} ativos</div>
      </div>
      <div class="card">
        <div class="val" style="color:#ddeeff">{total}</div>
        <div class="lbl">Total de Ativos</div>
        <div class="sub2">componentes IBOVESPA</div>
      </div>
    </div>"""

    pov  = float(latest.get("pct_rsi_oversold") or 0)
    pnt  = float(latest.get("pct_rsi_neutral") or 0)
    pob  = float(latest.get("pct_rsi_overbought") or 0)
    cov  = int(latest.get("count_rsi_oversold") or 0)
    cnt  = int(latest.get("count_rsi_neutral") or 0)
    cob  = int(latest.get("count_rsi_overbought") or 0)
    rtot = cov + cnt + cob

    rsi_cards_html = f"""
    <div class="cards">
      <div class="card">
        <div class="val" style="color:#22c55e">{pov:.1f}%</div>
        <div class="lbl">Sobrevendidos <span style="color:#3a5060;font-size:10px">(RSI &lt; 30)</span></div>
        <div class="sub2">{cov} de {rtot} ativos</div>
      </div>
      <div class="card">
        <div class="val" style="color:#f0b429">{pnt:.1f}%</div>
        <div class="lbl">Zona Neutra <span style="color:#3a5060;font-size:10px">(30–70)</span></div>
        <div class="sub2">{cnt} de {rtot} ativos</div>
      </div>
      <div class="card">
        <div class="val" style="color:#f05a5a">{pob:.1f}%</div>
        <div class="lbl">Sobrecomprados <span style="color:#3a5060;font-size:10px">(RSI &gt; 70)</span></div>
        <div class="sub2">{cob} de {rtot} ativos</div>
      </div>
      <div class="card">
        <div class="val" style="color:#ddeeff">{rtot}</div>
        <div class="lbl">Ativos c/ RSI</div>
        <div class="sub2">periodo 14</div>
      </div>
    </div>"""

    # ── Asset tables ─────────────────────────────────────────────
    sma_table_rows = ""
    rsi_table_rows = ""

    ticker_sector = _load_sector_map()
    ticker_groups = _load_sector_groups()

    if not ind.empty:
        for _, row in ind.iterrows():
            ticker = row["ticker"]
            _name_raw = row.get("name")
            name   = str(_name_raw).strip() if _name_raw and str(_name_raw) != "nan" else ""
            c      = float(row["close"]) if row["close"] else 0
            weight = float(row.get("weight") or 0)
            wt     = f"{weight:.2f}%" if weight else "—"

            ticker_cell = (
                f'<div style="display:flex;flex-direction:column;gap:2px">'
                f'<b style="font-size:14px;letter-spacing:.2px;font-family:\'DM Mono\',monospace;color:#d4e8f8">{ticker}</b>'
                f'<span style="color:#6a8aaa;font-size:10px">{wt}</span>'
                f'</div>'
            )
            name_cell  = f'<span style="color:#5a7090;font-size:12px">{name}</span>' if name else ""
            price_cell = f'<b style="font-family:\'DM Mono\',monospace;color:#c4d4e4">R$ {c:,.2f}</b>'

            sector_key   = ticker_sector.get(ticker, "")
            sector_badge = (
                f'<span class="sector-badge sect-{sector_key.lower()}">{sector_key}</span>'
                if sector_key else ""
            )

            a21  = bool(row.get("above_sma21"))
            a50  = bool(row.get("above_sma50"))
            a200 = bool(row.get("above_sma200"))
            score = int(a21) + int(a50) + int(a200)

            # Grupos multi-indice (permite filtrar IDIV/IBLV/IBOV mesmo com badge de outro setor)
            groups = set(ticker_groups.get(ticker, set()))
            is_active = row.get("is_active")
            if is_active and not (isinstance(is_active, float) and __import__("math").isnan(is_active)):
                groups.add("IBOV")
            groups_str = " ".join(sorted(groups))

            # Liquidez: peso IBOV se disponível, senão maior peso em índice setorial
            liq_raw = row.get("liq_score")
            liq = 0.0
            try:
                if liq_raw is not None:
                    liq = float(liq_raw)
                    if __import__("math").isnan(liq):
                        liq = 0.0
            except Exception:
                pass

            sma_table_rows += (
                f'<tr data-sma21="{"above" if a21 else "below"}"'
                f' data-sma50="{"above" if a50 else "below"}"'
                f' data-sma200="{"above" if a200 else "below"}"'
                f' data-score="{score}"'
                f' data-sector="{sector_key}"'
                f' data-groups="{groups_str}"'
                f' data-liq="{liq:.4f}">'
                f"<td>{ticker_cell}</td>"
                f"<td>{name_cell} {sector_badge}</td>"
                f"<td style='text-align:right'>{price_cell}</td>"
                f"<td>{_sma_cell(row['close'],row['sma21'],'21')}</td>"
                f"<td>{_sma_cell(row['close'],row['sma50'],'50')}</td>"
                f"<td>{_sma_cell(row['close'],row['sma200'],'200')}</td>"
                f"<td>{_score_bar(row)}</td>"
                f"</tr>"
            )

            rsi_val = row.get("rsi14")
            try:
                rv = float(rsi_val)
                zone_key = "overbought" if rv > 70 else ("oversold" if rv < 30 else "neutral")
            except Exception:
                zone_key = "neutral"

            rsi_table_rows += (
                f'<tr data-zone="{zone_key}" data-sector="{sector_key}" data-groups="{groups_str}" data-liq="{liq:.4f}">'
                f"<td>{ticker_cell}</td>"
                f"<td>{name_cell} {sector_badge}</td>"
                f"<td style='text-align:right'>{price_cell}</td>"
                f"<td style='min-width:160px'>{_rsi_bar(rsi_val)}</td>"
                f"<td style='text-align:center'>{_rsi_zone(rsi_val)}</td>"
                f"</tr>"
            )

    # Index breadth — adiciona IBOV como referencia
    idx_breadth = _load_index_breadth()
    idx_breadth["IBOV"] = {
        "dates":  dates_str,
        "sma200": b_chart["pct_sma200"].round(1).tolist(),
        "sma50":  b_chart["pct_sma50"].round(1).tolist(),
        "sma21":  b_chart["pct_sma21"].round(1).tolist(),
        "rsi":    b_chart["pct_rsi_oversold"].fillna(0).round(1).tolist(),
        "rsi_overbought": b_chart["pct_rsi_overbought"].fillna(0).round(1).tolist(),
    }

    sma_traces_json    = json.dumps(sma_traces)
    rsi_oversold_json  = json.dumps(rsi_oversold_y)
    rsi_overbought_json = json.dumps(rsi_overbought_y)
    ibov_dates_json    = json.dumps(ibov_dates)
    ibov_prices_json  = json.dumps(ibov_prices)
    dates_json        = json.dumps(dates_str)
    idx_breadth_json  = json.dumps(idx_breadth)

    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<title>IBOV Market Breadth — {now}</title>
<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#070d14;--bg2:#0b1520;--bg3:#0f1c2b;--bg4:#132030;
  --border:rgba(255,255,255,0.06);--border2:rgba(255,255,255,0.09);
  --txt:#c4d4e4;--txt2:#6a8099;--txt3:#3a5060;
  --accent:#2d7bbf;--accent2:rgba(45,123,191,0.15);
  --green:#22c55e;--green2:rgba(34,197,94,0.12);--green3:rgba(34,197,94,0.22);
  --red:#f05a5a;--red2:rgba(240,90,90,0.12);--red3:rgba(240,90,90,0.22);
  --amber:#f0b429;--amber2:rgba(240,180,41,0.12);--amber3:rgba(240,180,41,0.22);
}}
body{{
  background:var(--bg);color:var(--txt);
  font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
  font-size:13px;-webkit-font-smoothing:antialiased;
}}
/* ─── HEADER ─── */
.header{{
  background:linear-gradient(180deg,#0e1b2a 0%,#0b1520 100%);
  border-bottom:1px solid var(--border);
  padding:15px 28px;
  display:flex;align-items:center;justify-content:space-between;
}}
.header h1{{
  font-size:16px;font-weight:700;
  color:#ddeeff;letter-spacing:-0.3px;
}}
.header h1 span{{
  background:linear-gradient(90deg,#60aaee,#8bceff);
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
}}
.header .sub{{font-size:11px;color:var(--txt3);margin-top:3px;letter-spacing:0.2px}}
/* ─── TABS ─── */
.tabs{{
  display:flex;gap:0;padding:0 28px;
  background:#080f18;border-bottom:1px solid var(--border);
}}
.tab-btn{{
  padding:12px 22px;font-size:11px;font-weight:600;
  color:var(--txt3);background:none;border:none;
  border-bottom:2px solid transparent;cursor:pointer;
  transition:all .18s;letter-spacing:0.5px;text-transform:uppercase;
}}
.tab-btn:hover{{color:#8ab5d4}}
.tab-btn.active{{color:#c8e4f8;border-bottom-color:var(--accent)}}
.tab-btn.tab-rsi{{color:#1d7a3a}}
.tab-btn.tab-rsi:hover{{color:#22c55e}}
.tab-btn.tab-rsi.active{{color:#22c55e;border-bottom-color:#16a34a}}
.tab-btn.tab-idx{{color:#5a3a8a}}
.tab-btn.tab-idx:hover{{color:#a87ef8}}
.tab-btn.tab-idx.active{{color:#a87ef8;border-bottom-color:#7c3aed}}
.tab-btn.tab-gamma{{color:#b8860b;text-decoration:none;display:inline-flex;align-items:center}}
.tab-btn.tab-gamma:hover{{color:#f0b429}}
.tab-content{{display:none}}
.tab-content.active{{display:block}}
/* ─── CARDS ─── */
.cards{{display:flex;gap:12px;padding:16px 28px;flex-wrap:wrap}}
#idx-cards{{display:grid;grid-template-columns:repeat(12,1fr);gap:6px}}
.card{{
  background:linear-gradient(145deg,var(--bg3) 0%,var(--bg2) 100%);
  border:1px solid var(--border);border-radius:12px;
  padding:20px 22px;flex:1;min-width:175px;text-align:center;
  box-shadow:0 2px 16px rgba(0,0,0,0.35),inset 0 1px 0 rgba(255,255,255,0.04);
  transition:border-color .2s;
}}
.card:hover{{border-color:var(--border2)}}
.card .val{{
  font-size:34px;font-weight:800;line-height:1;
  letter-spacing:-1.5px;font-variant-numeric:tabular-nums;
  font-family:'Inter',sans-serif;
}}
.card .lbl{{font-size:10px;color:var(--txt2);margin-top:6px;letter-spacing:0.6px;text-transform:uppercase;font-weight:600}}
.card .sub2{{font-size:10px;color:var(--txt3);margin-top:3px}}
/* ─── SECTIONS ─── */
.section{{padding:8px 28px 0}}
.section h2{{
  font-size:10px;font-weight:700;color:var(--txt3);
  text-transform:uppercase;letter-spacing:0.9px;margin-bottom:8px;
}}
.chart-wrap{{padding:0 28px 12px}}
.chart-box{{width:100%;height:380px}}
/* ─── TABLE ─── */
.table-wrap{{padding:4px 28px 28px;overflow-x:auto}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;table-layout:auto}}
th{{
  background:#080f18;
  color:var(--txt3);
  padding:9px 16px;
  text-align:left;
  border-bottom:1px solid var(--border2);
  white-space:nowrap;position:sticky;top:0;z-index:1;
  font-size:10px;text-transform:uppercase;letter-spacing:0.8px;font-weight:700;
}}
td{{
  padding:11px 16px;
  border-bottom:1px solid rgba(255,255,255,0.025);
  vertical-align:middle;
}}
tr:hover td{{
  background:rgba(45,123,191,0.045);
  transition:background .1s;
}}
/* ─── PILLS ─── */
.pill{{
  display:inline-flex;align-items:center;gap:3px;
  padding:3px 10px;border-radius:20px;
  font-size:10px;font-weight:600;letter-spacing:0.3px;white-space:nowrap;
}}
.pill.acima{{background:var(--green2);color:var(--green);border:1px solid rgba(34,197,94,.25)}}
.pill.abaixo{{background:var(--red2);color:var(--red);border:1px solid rgba(240,90,90,.25)}}
.pill.na{{background:rgba(100,120,140,.07);color:var(--txt3);border:1px solid rgba(100,120,140,.12)}}
.pill.overbought{{background:var(--red3);color:var(--red);border:1px solid rgba(240,90,90,.35)}}
.pill.oversold{{background:var(--green3);color:var(--green);border:1px solid rgba(34,197,94,.35)}}
.pill.neutral{{background:var(--amber2);color:var(--amber);border:1px solid rgba(240,180,41,.28)}}
/* ─── FILTER BAR ─── */
.filter-bar{{
  display:flex;flex-wrap:wrap;gap:8px;align-items:center;
  padding:9px 28px;
  background:#060c14;
  border-bottom:1px solid var(--border);
}}
.filter-group{{display:flex;align-items:center;gap:5px;flex-wrap:wrap}}
.filter-label{{
  font-size:9px;font-weight:700;color:var(--txt3);
  text-transform:uppercase;letter-spacing:0.7px;white-space:nowrap;margin-right:2px;
}}
.fbtn{{
  padding:3px 11px;border-radius:20px;font-size:10.5px;font-weight:500;
  cursor:pointer;border:1px solid rgba(255,255,255,0.07);
  background:transparent;color:var(--txt2);
  transition:all .15s;white-space:nowrap;letter-spacing:0.2px;
}}
.fbtn:hover{{border-color:rgba(255,255,255,0.14);color:#98bcd8}}
.fbtn.active{{background:var(--accent2);border-color:rgba(45,123,191,.45);color:#7bbde8}}
/* SMA position filter */
.fbtn.f-sma21.active{{background:rgba(0,180,255,.15);border-color:rgba(0,180,255,.45);color:#00c8ff}}
.fbtn.f-sma50.active{{background:rgba(240,180,41,.15);border-color:rgba(240,180,41,.45);color:#f0c050}}
.fbtn.f-sma200.active{{background:rgba(240,90,90,.15);border-color:rgba(240,90,90,.45);color:#f08080}}
/* Zone filter */
.fbtn.f-ov.active{{background:var(--green3);border-color:#16a34a;color:var(--green)}}
.fbtn.f-ob.active{{background:var(--red3);border-color:var(--red);color:var(--red)}}
.fbtn.f-nt.active{{background:var(--amber3);border-color:var(--amber);color:var(--amber)}}
/* Sector filter */
.fbtn.f-ibov.active{{background:rgba(96,170,238,.18);border-color:rgba(96,170,238,.5);color:#60aaee}}
.fbtn.f-ifnc.active{{background:rgba(88,166,255,.18);border-color:rgba(88,166,255,.5);color:#58a6ff}}
.fbtn.f-ieex.active{{background:rgba(250,200,0,.18);border-color:rgba(250,200,0,.5);color:#fac800}}
.fbtn.f-imob.active{{background:rgba(163,126,248,.18);border-color:rgba(163,126,248,.5);color:#a37ef8}}
.fbtn.f-icon.active{{background:rgba(255,130,80,.18);border-color:rgba(255,130,80,.5);color:#ff8250}}
.fbtn.f-imat.active{{background:rgba(224,164,64,.18);border-color:rgba(224,164,64,.5);color:#e0a440}}
.fbtn.f-util.active{{background:rgba(57,168,150,.18);border-color:rgba(57,168,150,.5);color:#39a896}}
.fbtn.f-indx.active{{background:rgba(199,120,221,.18);border-color:rgba(199,120,221,.5);color:#c778dd}}
.fbtn.f-small.active{{background:rgba(140,148,158,.18);border-color:rgba(140,148,158,.5);color:#9db0be}}
.fbtn.f-idiv.active{{background:rgba(52,211,153,.18);border-color:rgba(52,211,153,.5);color:#34d399}}
.fbtn.f-iblv.active{{background:rgba(245,158,11,.18);border-color:rgba(245,158,11,.5);color:#f59e0b}}
/* ─── SMA STATS BAR ─── */
#sma-stat-bar{{
  display:flex;align-items:center;gap:6px;
  padding:5px 28px;
  background:#050b12;border-bottom:1px solid rgba(255,255,255,0.03);
  font-size:11.5px;flex-wrap:wrap;
}}
.sst-lbl{{font-size:9px;font-weight:700;color:var(--txt3);text-transform:uppercase;letter-spacing:0.7px;margin-right:1px}}
.sst-up{{color:var(--green);font-weight:700}}
.sst-up em{{color:#16a34a;font-style:normal;font-size:10px;font-weight:400}}
.sst-dn{{color:var(--red);font-weight:700}}
.sst-dn em{{color:#b91c1c;font-style:normal;font-size:10px;font-weight:400}}
.sst-sep{{color:rgba(255,255,255,0.08);margin:0 5px;font-size:14px}}
/* ─── SECTOR BADGES ─── */
.sector-badge{{
  display:inline-block;padding:1px 6px;border-radius:4px;
  font-size:9px;font-weight:700;letter-spacing:0.5px;
  margin-left:5px;vertical-align:middle;
}}
.sect-ifnc{{background:rgba(88,166,255,.12);color:#58a6ff;border:1px solid rgba(88,166,255,.25)}}
.sect-ieex{{background:rgba(250,200,0,.12);color:#fac800;border:1px solid rgba(250,200,0,.25)}}
.sect-imob{{background:rgba(163,126,248,.12);color:#a37ef8;border:1px solid rgba(163,126,248,.25)}}
.sect-icon{{background:rgba(255,130,80,.12);color:#ff8250;border:1px solid rgba(255,130,80,.25)}}
.sect-imat{{background:rgba(224,164,64,.12);color:#e0a440;border:1px solid rgba(224,164,64,.25)}}
.sect-util{{background:rgba(57,168,150,.12);color:#39a896;border:1px solid rgba(57,168,150,.25)}}
.sect-indx{{background:rgba(199,120,221,.12);color:#c778dd;border:1px solid rgba(199,120,221,.25)}}
.sect-small{{background:rgba(140,148,158,.12);color:#9db0be;border:1px solid rgba(140,148,158,.25)}}
.sect-idiv{{background:rgba(52,211,153,.12);color:#34d399;border:1px solid rgba(52,211,153,.25)}}
.sect-iblv{{background:rgba(245,158,11,.12);color:#f59e0b;border:1px solid rgba(245,158,11,.25)}}
/* ─── FOOTER / UPDATE BTN ─── */
.footer{{text-align:center;color:var(--txt3);font-size:10px;padding:14px}}
#update-btn{{
  display:flex;align-items:center;gap:8px;
  background:linear-gradient(135deg,#1a5c32,#166027);
  border:1px solid rgba(34,197,94,.3);color:#a3e8c0;
  padding:7px 16px;border-radius:8px;
  font-size:11px;font-weight:600;cursor:pointer;
  transition:all .18s;white-space:nowrap;letter-spacing:0.2px;
}}
#update-btn:hover{{background:linear-gradient(135deg,#1f6e3c,#1a7030);border-color:rgba(34,197,94,.5);color:#d1f5e0}}
#update-btn:disabled{{background:#0d1a25;border-color:rgba(255,255,255,0.07);color:var(--txt3);cursor:not-allowed}}
.spinner{{display:inline-block;width:11px;height:11px;border:2px solid rgba(255,255,255,.2);border-top-color:#a3e8c0;border-radius:50%;animation:spin .7s linear infinite}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
#update-status{{font-size:10px;color:var(--txt3);margin-top:3px}}
/* ─── PLOTLY OVERRIDE ─── */
.modebar-btn svg{{fill:var(--txt3)!important}}
.modebar-btn:hover svg{{fill:var(--txt)!important}}
.modebar{{background:rgba(8,15,24,0.9)!important;border-radius:6px!important}}
/* ─── Y-SCALE HANDLES ─── */
.chart-area{{display:flex;align-items:stretch;padding:0 28px 12px}}
.chart-area .chart-box{{flex:1;height:380px;width:0}}
#chart-idx{{height:280px}}
.y-scale-handle{{
  width:22px;flex-shrink:0;cursor:ns-resize;
  display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px;
  background:#0a1420;color:var(--txt3);font-size:10px;line-height:1;
  user-select:none;transition:all .15s;
}}
.y-scale-handle:hover{{background:var(--bg3);color:var(--accent)}}
.y-left{{border-right:1px dashed rgba(255,255,255,0.07);border-radius:4px 0 0 4px}}
.y-left:hover{{border-right-color:var(--accent)}}
.y-right{{border-left:1px dashed rgba(255,255,255,0.07);border-radius:0 4px 4px 0}}
.y-right:hover{{border-left-color:var(--accent)}}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>IBOV <span>Market Breadth</span></h1>
    <div class="sub">Referencia: {last_date} &nbsp;&middot;&nbsp; {total} ativos analisados &nbsp;&middot;&nbsp; Historico desde 2017</div>
  </div>
  <div style="display:flex;flex-direction:column;align-items:flex-end;gap:4px">
    <button id="update-btn" onclick="triggerUpdate()">
      <span id="btn-icon">&#8635;</span>
      <span id="btn-label">Atualizar Dados</span>
    </button>
    <div id="update-status">Atualizado: {now}</div>
  </div>
</div>

<div class="tabs">
  <button class="tab-btn active" onclick="showTab('sma',this)">Medias Moveis</button>
  <button class="tab-btn tab-rsi" onclick="showTab('rsi',this)">RSI Breadth</button>
  <button class="tab-btn tab-idx" onclick="showTab('idx',this)">Amplitude por Indices</button>
  <button class="tab-btn tab-gamma" onclick="showTab('gamma',this)">Gamma Screener</button>
</div>

<!-- ═══════════════════════════════════════════════════ TAB SMA -->
<div id="tab-sma" class="tab-content active">

  {sma_cards_html}

  <div class="section"><h2>Historico — % Ativos Acima das Medias (desde 2017)</h2></div>
  <div class="chart-area">
    <div class="y-scale-handle y-left" onmousedown="startYScale(event,'chart-sma','y')" title="Arraste: escala breadth %">&#9650;<br>&#9632;<br>&#9660;</div>
    <div id="chart-sma" class="chart-box"></div>
    <div class="y-scale-handle y-right" onmousedown="startYScale(event,'chart-sma','y2')" title="Arraste: escala IBOV">&#9650;<br>&#9632;<br>&#9660;</div>
  </div>

  <!-- Filtros da tabela SMA -->
  <div class="filter-bar">
    <div class="filter-group">
      <span class="filter-label">Posicao</span>
      <button class="fbtn active"   id="sp-all"    onclick="setSMAFilter('pos','all',      this)">Todos</button>
      <button class="fbtn f-sma21"  id="sp-a21"    onclick="setSMAFilter('pos','above21',  this)">&#9650; MA21</button>
      <button class="fbtn f-sma21"  id="sp-b21"    onclick="setSMAFilter('pos','below21',  this)">&#9660; MA21</button>
      <button class="fbtn f-sma50"  id="sp-a50"    onclick="setSMAFilter('pos','above50',  this)">&#9650; MA50</button>
      <button class="fbtn f-sma50"  id="sp-b50"    onclick="setSMAFilter('pos','below50',  this)">&#9660; MA50</button>
      <button class="fbtn f-sma200" id="sp-a200"   onclick="setSMAFilter('pos','above200', this)">&#9650; MA200</button>
      <button class="fbtn f-sma200" id="sp-b200"   onclick="setSMAFilter('pos','below200', this)">&#9660; MA200</button>
    </div>
    <div style="width:1px;background:#30363d;height:20px;margin:0 2px"></div>
    <div class="filter-group">
      <span class="filter-label">Setor</span>
      <button class="fbtn active"  id="ss-all"   onclick="setSMAFilter('sector','',     this)">Todos</button>
      <button class="fbtn f-ibov"  id="ss-ibov"  onclick="setSMAFilter('sector','IBOV', this)">IBOV</button>
      <button class="fbtn f-ifnc"  id="ss-ifnc"  onclick="setSMAFilter('sector','IFNC', this)">IFNC</button>
      <button class="fbtn f-ieex"  id="ss-ieex"  onclick="setSMAFilter('sector','IEEX', this)">IEEX</button>
      <button class="fbtn f-imob"  id="ss-imob"  onclick="setSMAFilter('sector','IMOB', this)">IMOB</button>
      <button class="fbtn f-icon"  id="ss-icon"  onclick="setSMAFilter('sector','ICON', this)">ICON</button>
      <button class="fbtn f-imat"  id="ss-imat"  onclick="setSMAFilter('sector','IMAT', this)">IMAT</button>
      <button class="fbtn f-util"  id="ss-util"  onclick="setSMAFilter('sector','UTIL', this)">UTIL</button>
      <button class="fbtn f-indx"  id="ss-indx"  onclick="setSMAFilter('sector','INDX', this)">INDX</button>
      <button class="fbtn f-small" id="ss-small" onclick="setSMAFilter('sector','SMALL',this)">SMALL</button>
      <button class="fbtn f-idiv"  id="ss-idiv"  onclick="setSMAFilter('sector','IDIV', this)">IDIV</button>
      <button class="fbtn f-iblv"  id="ss-iblv"  onclick="setSMAFilter('sector','IBLV', this)">IBLV</button>
    </div>
    <div id="sma-filter-count" style="margin-left:auto;font-size:11px;color:#484f58"></div>
  </div>

  <!-- Legenda de contagem por SMA -->
  <div id="sma-stat-bar"></div>

  <div class="table-wrap">
    <div class="section" style="margin-bottom:8px"><h2>Posicao dos Ativos vs SMAs</h2></div>
    <table>
      <thead>
        <tr>
          <th>Ticker</th><th>Nome / Setor</th><th style="text-align:right">Fechamento</th>
          <th>SMA21 &amp; Distancia</th><th>SMA50 &amp; Distancia</th><th>SMA200 &amp; Distancia</th>
          <th>Score</th>
        </tr>
      </thead>
      <tbody id="sma-tbody">{sma_table_rows}</tbody>
    </table>
  </div>

</div>

<!-- ═══════════════════════════════════════════════════ TAB RSI -->
<div id="tab-rsi" class="tab-content">

  {rsi_cards_html}

  <div class="section">
    <h2>RSI Market Breadth &mdash; <span style="color:#2ea043">Sobrevendidos (RSI &lt; 30)</span> &amp; <span style="color:#f85149">Sobrecomprados (RSI &gt; 70)</span></h2>
  </div>
  <div class="chart-area">
    <div class="y-scale-handle y-left" onmousedown="startYScale(event,'chart-rsi','y')" title="Arraste: escala RSI %">&#9650;<br>&#9632;<br>&#9660;</div>
    <div id="chart-rsi" class="chart-box"></div>
    <div class="y-scale-handle y-right" onmousedown="startYScale(event,'chart-rsi','y2')" title="Arraste: escala IBOV">&#9650;<br>&#9632;<br>&#9660;</div>
  </div>

  <!-- Filtros da tabela RSI -->
  <div class="filter-bar">
    <div class="filter-group">
      <span class="filter-label">Zona</span>
      <button class="fbtn active" id="fz-all"  onclick="setFilter('zone','all',       this)">Todos</button>
      <button class="fbtn f-ov"   id="fz-ov"   onclick="setFilter('zone','oversold',   this)">&#128994; Sobrevendido</button>
      <button class="fbtn f-nt"   id="fz-nt"   onclick="setFilter('zone','neutral',    this)">&#128993; Neutro</button>
      <button class="fbtn f-ob"   id="fz-ob"   onclick="setFilter('zone','overbought', this)">&#128308; Sobrecomprado</button>
    </div>
    <div style="width:1px;background:#30363d;height:20px;margin:0 2px"></div>
    <div class="filter-group">
      <span class="filter-label">Setor</span>
      <button class="fbtn active"  id="fs-all"   onclick="setFilter('sector','',     this)">Todos</button>
      <button class="fbtn f-ibov"  id="fs-ibov"  onclick="setFilter('sector','IBOV', this)">IBOV</button>
      <button class="fbtn f-ifnc"  id="fs-ifnc"  onclick="setFilter('sector','IFNC', this)">IFNC</button>
      <button class="fbtn f-ieex"  id="fs-ieex"  onclick="setFilter('sector','IEEX', this)">IEEX</button>
      <button class="fbtn f-imob"  id="fs-imob"  onclick="setFilter('sector','IMOB', this)">IMOB</button>
      <button class="fbtn f-icon"  id="fs-icon"  onclick="setFilter('sector','ICON', this)">ICON</button>
      <button class="fbtn f-imat"  id="fs-imat"  onclick="setFilter('sector','IMAT', this)">IMAT</button>
      <button class="fbtn f-util"  id="fs-util"  onclick="setFilter('sector','UTIL', this)">UTIL</button>
      <button class="fbtn f-indx"  id="fs-indx"  onclick="setFilter('sector','INDX', this)">INDX</button>
      <button class="fbtn f-small" id="fs-small" onclick="setFilter('sector','SMALL',this)">SMALL</button>
      <button class="fbtn f-idiv"  id="fs-idiv"  onclick="setFilter('sector','IDIV', this)">IDIV</button>
      <button class="fbtn f-iblv"  id="fs-iblv"  onclick="setFilter('sector','IBLV', this)">IBLV</button>
    </div>
    <div id="filter-count" style="margin-left:auto;font-size:11px;color:#484f58"></div>
  </div>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Ticker</th><th>Nome / Setor</th><th style="text-align:right">Fechamento</th>
          <th>RSI(14)</th><th>Zona</th>
        </tr>
      </thead>
      <tbody id="rsi-tbody">{rsi_table_rows}</tbody>
    </table>
  </div>

</div>

<!-- ═══════════════════════════════════════════ TAB INDICES -->
<div id="tab-idx" class="tab-content">

  <div class="filter-bar" style="border-top:1px solid #21262d">
    <div class="filter-group">
      <span class="filter-label">Indicador</span>
      <button class="fbtn f-sma200 active" id="im-200" onclick="switchIdxMetric('sma200',this)">% Acima SMA200</button>
      <button class="fbtn f-sma50"         id="im-50"  onclick="switchIdxMetric('sma50', this)">% Acima SMA50</button>
      <button class="fbtn f-sma21"         id="im-21"  onclick="switchIdxMetric('sma21', this)">% Acima SMA21</button>
      <button class="fbtn f-ov"            id="im-rsi" onclick="switchIdxMetric('rsi',   this)">RSI Sobrevendido</button>
      <button class="fbtn f-ov"            id="im-rsiob" onclick="switchIdxMetric('rsi_overbought', this)">RSI Sobrecomprado</button>
    </div>
    <div style="margin-left:auto;font-size:11px;color:#484f58">Ative/desative indices clicando na legenda</div>
  </div>

  <div class="section" style="margin-top:8px"><h2>Amplitude comparada entre indices</h2></div>
  <div class="chart-area">
    <div class="y-scale-handle y-left" onmousedown="startYScale(event,'chart-idx','y')" title="Arraste: escala %">&#9650;<br>&#9632;<br>&#9660;</div>
    <div id="chart-idx" class="chart-box"></div>
    <div class="y-scale-handle y-right" style="visibility:hidden">&#9650;<br>&#9632;<br>&#9660;</div>
  </div>

  <div class="cards" style="padding-top:4px" id="idx-cards"></div>

</div>

<div id="tab-gamma" class="tab-content">
  <iframe id="gamma-iframe" src="" style="width:100%;height:calc(100vh - 210px);border:none;display:block;background:#0d1117"></iframe>
</div>

<div class="footer">IBOV Market Breadth &mdash; dados via Yahoo Finance / B3 &mdash; {now}</div>

<script>
var dates        = {dates_json};
var smaTraces    = {sma_traces_json};
var rsiOversold   = {rsi_oversold_json};
var rsiOverbought = {rsi_overbought_json};
var ibovDates     = {ibov_dates_json};
var ibovPrices   = {ibov_prices_json};
var idxBreadth   = {idx_breadth_json};
var chartsMade   = {{}};

// Configuracao Plotly: scroll do mouse = zoom proporcional em X e Y
var plotConfig = {{
  responsive: true,
  scrollZoom: true,
  displayModeBar: true,
  modeBarButtonsToRemove: ["select2d","lasso2d","toImage",
                            "hoverClosestCartesian","hoverCompareCartesian","toggleSpikelines"],
  displaylogo: false
}};

var layoutBase = {{
  paper_bgcolor:"#0b1520", plot_bgcolor:"#070d14",
  font:{{color:"#6a8099",size:11,family:"Inter,sans-serif"}},
  margin:{{t:10,r:20,b:40,l:50}},
  dragmode:"pan",
  xaxis:{{gridcolor:"rgba(255,255,255,0.04)",linecolor:"rgba(255,255,255,0.07)",rangeslider:{{visible:false}}}},
  yaxis:{{gridcolor:"rgba(255,255,255,0.04)",linecolor:"rgba(255,255,255,0.07)",ticksuffix:"%",fixedrange:false}},
  legend:{{bgcolor:"rgba(0,0,0,0)",bordercolor:"rgba(255,255,255,0.07)",borderwidth:1}},
  hovermode:"x unified"
}};

// ── Legenda de contagem SMA ──────────────────────────────────
function updateSMAStats() {{
  var rows = document.querySelectorAll("#sma-tbody tr");
  var a21=0,b21=0,a50=0,b50=0,a200=0,b200=0,tot=0;
  rows.forEach(function(r) {{
    if (!_inGroups(r, _fSMASector)) return;
    tot++;
    if (r.dataset.sma21  === "above") a21++;  else b21++;
    if (r.dataset.sma50  === "above") a50++;  else b50++;
    if (r.dataset.sma200 === "above") a200++; else b200++;
  }});
  function pct(n) {{ return tot > 0 ? Math.round(n / tot * 100) : 0; }}
  var el = document.getElementById("sma-stat-bar");
  if (!el) return;
  el.innerHTML =
    '<span class="sst-lbl">SMA21</span>' +
    '<span class="sst-up">&#9650; ' + a21  + ' <em>(' + pct(a21)  + '%)</em></span>' +
    '<span class="sst-dn">&#9660; ' + b21  + ' <em>(' + pct(b21)  + '%)</em></span>' +
    '<span class="sst-sep">|</span>' +
    '<span class="sst-lbl">SMA50</span>' +
    '<span class="sst-up">&#9650; ' + a50  + ' <em>(' + pct(a50)  + '%)</em></span>' +
    '<span class="sst-dn">&#9660; ' + b50  + ' <em>(' + pct(b50)  + '%)</em></span>' +
    '<span class="sst-sep">|</span>' +
    '<span class="sst-lbl">SMA200</span>' +
    '<span class="sst-up">&#9650; ' + a200 + ' <em>(' + pct(a200) + '%)</em></span>' +
    '<span class="sst-dn">&#9660; ' + b200 + ' <em>(' + pct(b200) + '%)</em></span>' +
    '<span style="margin-left:8px;font-size:10px;color:#484f58">de ' + tot + ' ativos</span>';
}}

// ── Filtros SMA ──────────────────────────────────────────────
var _fSMAPos = "all", _fSMASector = "";

function _inGroups(row, val) {{
  if (val === "") return true;
  var groups = (row.dataset.groups || "").split(" ");
  return groups.indexOf(val) !== -1;
}}

function _sortByLiq(tbodyId) {{
  var tbody = document.getElementById(tbodyId);
  if (!tbody) return;
  var rows = Array.from(tbody.querySelectorAll("tr"));
  rows.sort(function(a, b) {{
    return parseFloat(b.dataset.liq || 0) - parseFloat(a.dataset.liq || 0);
  }});
  rows.forEach(function(r) {{ tbody.appendChild(r); }});
}}

function setSMAFilter(type, val, btn) {{
  if (type === "pos")    _fSMAPos    = val;
  if (type === "sector") _fSMASector = val;

  var prefix = type === "pos" ? "sp-" : "ss-";
  document.querySelectorAll("[id^='" + prefix + "']").forEach(function(b) {{
    b.classList.remove("active");
  }});
  btn.classList.add("active");

  var rows  = document.querySelectorAll("#sma-tbody tr");
  var shown = 0;
  rows.forEach(function(row) {{
    var p = _fSMAPos;
    var posOk = p === "all" ||
      (p === "above21"  && row.dataset.sma21  === "above") ||
      (p === "below21"  && row.dataset.sma21  === "below") ||
      (p === "above50"  && row.dataset.sma50  === "above") ||
      (p === "below50"  && row.dataset.sma50  === "below") ||
      (p === "above200" && row.dataset.sma200 === "above") ||
      (p === "below200" && row.dataset.sma200 === "below");
    var secOk = _inGroups(row, _fSMASector);
    var ok    = posOk && secOk;
    row.style.display = ok ? "" : "none";
    if (ok) shown++;
  }});
  document.getElementById("sma-filter-count").textContent =
    shown + " ativo" + (shown !== 1 ? "s" : "");
  _sortByLiq("sma-tbody");
  if (type === "sector") updateSMAStats();
}}

// ── Filtros RSI ──────────────────────────────────────────────
var _fZone = "all", _fSector = "";

function setFilter(type, val, btn) {{
  if (type === "zone")   _fZone   = val;
  if (type === "sector") _fSector = val;

  var prefix = type === "zone" ? "fz-" : "fs-";
  document.querySelectorAll("[id^='" + prefix + "']").forEach(function(b) {{
    b.classList.remove("active");
  }});
  btn.classList.add("active");

  var rows  = document.querySelectorAll("#rsi-tbody tr");
  var shown = 0;
  rows.forEach(function(row) {{
    var zoneOk   = _fZone === "all" || row.dataset.zone === _fZone;
    var sectorOk = _inGroups(row, _fSector);
    var ok = zoneOk && sectorOk;
    row.style.display = ok ? "" : "none";
    if (ok) shown++;
  }});
  document.getElementById("filter-count").textContent =
    shown + " ativo" + (shown !== 1 ? "s" : "");
  _sortByLiq("rsi-tbody");
}}

// Shapes SMA
var smaShapes = [
  {{type:"rect",xref:"paper",yref:"y",x0:0,x1:1,y0:40,y1:60,
    fillcolor:"rgba(255,255,255,0.04)",layer:"below",line:{{width:0}}}},
  {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:60,y1:60,
    line:{{color:"rgba(255,255,255,0.13)",width:1,dash:"dot"}}}},
  {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:40,y1:40,
    line:{{color:"rgba(255,255,255,0.13)",width:1,dash:"dot"}}}},
  {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:80,y1:80,
    line:{{color:"rgba(248,81,73,0.35)",width:1,dash:"dash"}}}},
  {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:20,y1:20,
    line:{{color:"rgba(46,160,67,0.35)",width:1,dash:"dash"}}}}
];

// Shapes RSI
var rsiShapes = [
  {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:80,y1:80,
    line:{{color:"rgba(248,81,73,0.3)",width:1,dash:"dash"}}}},
  {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:50,y1:50,
    line:{{color:"rgba(255,255,255,0.08)",width:1,dash:"dot"}}}},
  {{type:"line",xref:"paper",yref:"y",x0:0,x1:1,y0:20,y1:20,
    line:{{color:"rgba(46,160,67,0.3)",width:1,dash:"dash"}}}}
];

function buildSMATraces(){{
  // SMA breadth traces — painel inferior (y)
  // SMA50 ativo por padrão; SMA21 e SMA200 desativados (legendonly)
  var traces = smaTraces.map(function(t){{
    var ativa = t.name.indexOf("SMA50") !== -1;
    return {{x:dates, y:t.y, name:t.name, type:"scatter", mode:"lines",
             line:{{color:t.color, width:2}},
             yaxis:"y", xaxis:"x",
             visible: ativa ? true : "legendonly",
             hovertemplate:"%{{x}}<br>"+t.name+": %{{y:.1f}}%<extra></extra>"}};
  }});
  // IBOV — painel superior (y2), sempre visível
  traces.push({{
    x: ibovDates, y: ibovPrices,
    name: "IBOVESPA",
    type: "scatter", mode: "lines",
    line: {{color:"rgba(88,166,255,0.65)", width:1.5}},
    yaxis: "y2", xaxis: "x",
    hovertemplate: "%{{x}}<br>IBOV: %{{y:,.0f}}<extra></extra>"
  }});
  return traces;
}}

function buildSMALayout(){{
  return {{
    paper_bgcolor:"#0b1520", plot_bgcolor:"#070d14",
    font:{{color:"#6a8099",size:11,family:"Inter,sans-serif"}},
    margin:{{t:10,r:60,b:40,l:55}},
    // Eixo X compartilhado pelos dois painéis
    xaxis:{{
      gridcolor:"rgba(255,255,255,0.04)",linecolor:"rgba(255,255,255,0.07)",
      rangeslider:{{visible:false}},
      domain:[0,1], anchor:"y"
    }},
    // Painel inferior — % Acima das Médias (30% da altura)
    yaxis:{{
      domain:[0,0.30],
      gridcolor:"rgba(255,255,255,0.04)",linecolor:"rgba(255,255,255,0.07)",
      ticksuffix:"%", fixedrange:false, range:[0,105],
      title:{{text:"% Acima MMs",font:{{size:10,color:"#3a5060"}}}}
    }},
    // Painel superior — IBOVESPA (67% da altura)
    yaxis2:{{
      domain:[0.35,1.0],
      gridcolor:"rgba(255,255,255,0.04)",linecolor:"rgba(255,255,255,0.07)",
      anchor:"x", fixedrange:false, tickformat:",.0f",
      title:{{text:"IBOVESPA",font:{{size:10,color:"#3a5060"}}}}
    }},
    legend:{{bgcolor:"rgba(0,0,0,0)",bordercolor:"rgba(255,255,255,0.07)",borderwidth:1}},
    hovermode:"x unified",
    dragmode:"pan",
    shapes: smaShapes
  }};
}}

function showTab(id, btn){{
  document.querySelectorAll(".tab-content").forEach(function(el){{el.classList.remove("active")}});
  document.querySelectorAll(".tab-btn").forEach(function(el){{el.classList.remove("active")}});
  document.getElementById("tab-"+id).classList.add("active");
  btn.classList.add("active");

  if(!chartsMade[id]){{
    chartsMade[id] = true;
    if(id==="sma"){{
      Plotly.newPlot("chart-sma", buildSMATraces(), buildSMALayout(), plotConfig)
        .then(function() {{ _smaLegendReady(); _addCtrlZoom("chart-sma"); }});
    }} else if(id==="rsi"){{
      buildRsiChart();
    }} else if(id==="idx"){{
      buildIdxChart();
    }} else if(id==="gamma"){{
      document.getElementById("gamma-iframe").src = "../gamma/";
    }}
  }}
}}

// ── RSI chart — subplots (IBOV topo, RSI breadth baixo) ─────
function buildRsiChart() {{
  // Painel inferior: sobrevendidos (verde) + sobrecomprados (vermelho)
  var oversoldTrace = {{
    x: dates, y: rsiOversold,
    name: "% Sobrevendido (RSI<30)",
    type: "scatter", mode: "lines",
    line: {{color:"#2ea043", width:2}},
    yaxis: "y", xaxis: "x",
    hovertemplate: "%{{x}}<br>Sobrevendido: %{{y:.1f}}%<extra></extra>"
  }};
  var overboughtTrace = {{
    x: dates, y: rsiOverbought,
    name: "% Sobrecomprado (RSI>70)",
    type: "scatter", mode: "lines",
    line: {{color:"#f85149", width:2}},
    yaxis: "y", xaxis: "x",
    hovertemplate: "%{{x}}<br>Sobrecomprado: %{{y:.1f}}%<extra></extra>"
  }};
  // Painel superior: IBOVESPA — sempre visível
  var ibovTrace = {{
    x: ibovDates, y: ibovPrices,
    name: "IBOVESPA",
    type: "scatter", mode: "lines",
    line: {{color:"rgba(88,166,255,0.65)", width:1.5}},
    yaxis: "y2", xaxis: "x",
    hovertemplate: "%{{x}}<br>IBOV: %{{y:,.0f}}<extra></extra>"
  }};
  var rsiLayout = {{
    paper_bgcolor:"#0b1520", plot_bgcolor:"#070d14",
    font: {{color:"#6a8099", size:11, family:"Inter,sans-serif"}},
    margin: {{t:10, r:60, b:40, l:55}},
    xaxis: {{
      gridcolor:"rgba(255,255,255,0.04)", linecolor:"rgba(255,255,255,0.07)",
      rangeslider:{{visible:false}}, domain:[0,1], anchor:"y"
    }},
    // Painel inferior — RSI breadth (30% da altura)
    yaxis: {{
      domain:[0,0.30],
      gridcolor:"rgba(255,255,255,0.04)", linecolor:"rgba(255,255,255,0.07)",
      ticksuffix:"%", fixedrange:false, range:[0,105],
      title:{{text:"% Ativos",font:{{size:10,color:"#3a5060"}}}}
    }},
    // Painel superior — IBOVESPA (67% da altura)
    yaxis2: {{
      domain:[0.35,1.0],
      gridcolor:"rgba(255,255,255,0.04)", linecolor:"rgba(255,255,255,0.07)",
      anchor:"x", fixedrange:false, tickformat:",.0f",
      title:{{text:"IBOVESPA",font:{{size:10,color:"#3a5060"}}}}
    }},
    legend: {{bgcolor:"rgba(0,0,0,0)", bordercolor:"rgba(255,255,255,0.07)", borderwidth:1}},
    hovermode: "x unified",
    dragmode: "pan",
    shapes: rsiShapes
  }};
  Plotly.newPlot("chart-rsi", [oversoldTrace, overboughtTrace, ibovTrace], rsiLayout, plotConfig)
    .then(function() {{ _addCtrlZoom("chart-rsi"); }});
}}

// IBOV sempre visível no painel superior
function toggleIbov(show) {{}}

// IBOV sempre visível no painel superior — não precisa de toggle de eixo
function _smaLegendReady() {{}}

// ── Indices breadth chart ────────────────────────────────────
var _idxCfg = [
  {{code:"IBOV", color:"#8b949e", width:1.5, dash:"dot",   label:"IBOV (ref)"}},
  {{code:"IDIV", color:"#58a6ff", width:2,   dash:"solid", label:"IDIV"}},
  {{code:"IFNC", color:"#ffc400", width:2,   dash:"solid", label:"IFNC"}},
  {{code:"EWZ",  color:"#ff794d", width:2,   dash:"solid", label:"EWZ"}},
  {{code:"IBLV", color:"#a371f7", width:2,   dash:"solid", label:"IBLV"}},
  {{code:"IEEX", color:"#3fb950", width:2,   dash:"solid", label:"IEEX"}},
  {{code:"IMOB", color:"#f778ba", width:2,   dash:"solid", label:"IMOB"}},
  {{code:"ICON", color:"#39c5cf", width:2,   dash:"solid", label:"ICON"}},
  {{code:"IMAT", color:"#f85149", width:2,   dash:"solid", label:"IMAT"}},
  {{code:"UTIL", color:"#d29922", width:2,   dash:"solid", label:"UTIL"}},
  {{code:"SMLL", color:"#7ee787", width:2,   dash:"solid", label:"SMALL"}},
  {{code:"INDX", color:"#bc8cff", width:2,   dash:"solid", label:"INDX"}},
];

function buildIdxChart() {{
  var codes = Object.keys(idxBreadth);
  if (codes.length === 0) {{
    document.getElementById("chart-idx").innerHTML =
      '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#484f58;font-size:13px">'
      + 'Clique em "Atualizar Dados" para calcular o breadth dos indices.</div>';
    return;
  }}

  var metric = "sma200";
  var traces = _idxCfg
    .filter(function(c) {{ return idxBreadth[c.code]; }})
    .map(function(c) {{
      var d = idxBreadth[c.code];
      return {{
        x: d.dates, y: d[metric],
        name: c.label,
        type:"scatter", mode:"lines",
        line:{{color:c.color, width:c.width, dash:c.dash}},
        visible: c.code === "IBOV" ? true : "legendonly",
        hovertemplate:"%{{x}}<br>" + c.label + ": %{{y:.1f}}%<extra></extra>"
      }};
    }});

  var layout = Object.assign({{}}, layoutBase, {{
    shapes: smaShapes,
    yaxis: Object.assign({{}}, layoutBase.yaxis, {{range:[0,105]}})
  }});

  Plotly.newPlot("chart-idx", traces, layout, plotConfig)
    .then(function() {{
      _addCtrlZoom("chart-idx");
      _buildIdxCards("sma200");
    }});
}}

function switchIdxMetric(metric, btn) {{
  document.querySelectorAll("[id^='im-']").forEach(function(b){{b.classList.remove("active")}});
  btn.classList.add("active");
  var el = document.getElementById("chart-idx");
  if (!el || !el.data || !el.data.length) return;
  var active = _idxCfg.filter(function(c){{return idxBreadth[c.code];}});
  var newY = active.map(function(c){{return idxBreadth[c.code][metric];}});
  var newX = active.map(function(c){{return idxBreadth[c.code].dates;}});
  Plotly.restyle("chart-idx", {{x:newX, y:newY}});
  _buildIdxCards(metric);
}}

function _buildIdxCards(metric) {{
  var labels = {{sma200:"% Acima SMA200", sma50:"% Acima SMA50", sma21:"% Acima SMA21", rsi:"RSI Sobrevendido", rsi_overbought:"RSI Sobrecomprado"}};
  var container = document.getElementById("idx-cards");
  if (!container) return;
  var html = "";
  _idxCfg.forEach(function(c) {{
    if (!idxBreadth[c.code]) return;
    var arr = idxBreadth[c.code][metric];
    var val = arr && arr.length ? arr[arr.length-1] : null;
    var disp = val !== null ? val.toFixed(1) + "%" : "—";
    var color = val === null ? "#484f58" :
                val >= 70 ? "#2ea043" : val >= 50 ? "#e3b341" :
                val >= 30 ? "#d29922" : "#f85149";
    html += '<div class="card" style="border-left:3px solid ' + c.color + ';min-width:0;padding:12px 6px">'
          + '<div class="val" style="color:' + color + ';font-size:19px">' + disp + '</div>'
          + '<div class="lbl" style="color:' + c.color + ';font-weight:700">' + c.label + '</div>'
          + '<div class="sub2">' + labels[metric] + '</div>'
          + '</div>';
  }});
  container.innerHTML = html;
}}

// ── Y-axis scale handles (esquerdo=breadth %, direito=IBOV) ──
// Arraste CIMA = zoom in, BAIXO = zoom out | Ctrl+scroll = lupa
var _yscaling = null;
function startYScale(e, chartId, axis) {{
  e.preventDefault();
  var el  = document.getElementById(chartId);
  var ly  = el.layout || {{}};
  var axCfg = (axis === "y2") ? ly.yaxis2 : ly.yaxis;
  var fallback = (axis === "y2") ? [40000, 140000] : [0, 100];
  var cur = (axCfg && axCfg.range) ? axCfg.range : fallback;
  _yscaling = {{ chartId:chartId, startY:e.clientY, startRange:[cur[0],cur[1]], axis:axis }};
  document.addEventListener("mousemove", doYScale);
  document.addEventListener("mouseup",   stopYScale);
}}
function doYScale(e) {{
  if (!_yscaling) return;
  var delta  = e.clientY - _yscaling.startY;
  var factor = Math.pow(1.006, delta);
  var lo = _yscaling.startRange[0], hi = _yscaling.startRange[1];
  var center = (lo + hi) / 2;
  var half   = (hi - lo) / 2 * factor;
  var key = (_yscaling.axis === "y2") ? "yaxis2.range" : "yaxis.range";
  Plotly.relayout(_yscaling.chartId, {{ [key]: [center-half, center+half] }});
}}
function stopYScale() {{
  _yscaling = null;
  document.removeEventListener("mousemove", doYScale);
  document.removeEventListener("mouseup",   stopYScale);
}}

// Ctrl+scroll: zoom proporcional em X e Y (lupa)
// O eixo X usa strings de data — converte para ms antes da aritmética
function _addCtrlZoom(chartId) {{
  var el = document.getElementById(chartId);
  if (!el) return;
  el.addEventListener("wheel", function(e) {{
    if (!e.ctrlKey) return;
    e.preventDefault();
    e.stopPropagation();
    var ly = el.layout || {{}};
    var factor = e.deltaY > 0 ? 1.15 : 1/1.15;
    var upd = {{}};
    // Zoom Y (sempre numérico)
    var yr = (ly.yaxis && ly.yaxis.range) ? ly.yaxis.range : [0, 100];
    var yc = (yr[0]+yr[1])/2, yh = (yr[1]-yr[0])/2*factor;
    upd["yaxis.range"] = [yc-yh, yc+yh];
    // Zoom X (eixo de datas — converte string→ms→string)
    if (ly.xaxis && ly.xaxis.range) {{
      var xr = ly.xaxis.range;
      var x0 = typeof xr[0]==="string" ? new Date(xr[0]).getTime() : xr[0];
      var x1 = typeof xr[1]==="string" ? new Date(xr[1]).getTime() : xr[1];
      var xc = (x0+x1)/2, xh = (x1-x0)/2*factor;
      upd["xaxis.range"] = [
        new Date(xc-xh).toISOString().slice(0,10),
        new Date(xc+xh).toISOString().slice(0,10)
      ];
    }}
    Plotly.relayout(chartId, upd);
  }}, {{passive:false, capture:true}});
}}

// Inicializa SMA chart
chartsMade["sma"] = true;
Plotly.newPlot("chart-sma", buildSMATraces(), buildSMALayout(), plotConfig)
  .then(function() {{ _smaLegendReady(); _addCtrlZoom("chart-sma"); }});

// Ordena por liquidez no carregamento inicial
_sortByLiq("sma-tbody");
_sortByLiq("rsi-tbody");

// Popula legenda de contagem SMA no load
updateSMAStats();

// ── Botao de atualizacao ─────────────────────────────────────
var _pollTimer = null;

function setUpdating(yes, step) {{
  var btn   = document.getElementById("update-btn");
  var icon  = document.getElementById("btn-icon");
  var label = document.getElementById("btn-label");
  var status = document.getElementById("update-status");
  if (yes) {{
    btn.disabled = true;
    icon.outerHTML = '<span id="btn-icon" class="spinner"></span>';
    label.textContent = "Atualizando...";
    status.textContent = step || "Iniciando pipeline...";
  }} else {{
    btn.disabled = false;
    document.getElementById("btn-icon").outerHTML = '<span id="btn-icon">&#8635;</span>';
    label.textContent = "Atualizar Dados";
  }}
}}

function pollStatus() {{
  fetch("/api/status")
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      if (d.running) {{
        document.getElementById("update-status").textContent = d.step || "Processando...";
      }} else {{
        clearInterval(_pollTimer);
        if (d.error) {{
          setUpdating(false);
          document.getElementById("update-status").textContent = "Erro: " + d.error;
        }} else {{
          document.getElementById("update-status").textContent = "Concluido! Recarregando...";
          setTimeout(function() {{ location.reload(); }}, 800);
        }}
      }}
    }})
    .catch(function() {{ clearInterval(_pollTimer); setUpdating(false); }});
}}

function triggerUpdate() {{
  setUpdating(true, "Conectando ao servidor...");
  fetch("/api/update", {{method:"POST"}})
    .then(function(r) {{ return r.json(); }})
    .then(function(d) {{
      _pollTimer = setInterval(pollStatus, 2000);
    }})
    .catch(function() {{
      setUpdating(false);
      document.getElementById("update-status").textContent =
        "Servidor nao encontrado. Execute start.bat primeiro.";
    }});
}}

fetch("/api/status")
  .then(function(r) {{ return r.json(); }})
  .then(function(d) {{
    if (d.running) {{ setUpdating(true, d.step); _pollTimer = setInterval(pollStatus, 2000); }}
    if (d.last_update) {{ document.getElementById("update-status").textContent = "Atualizado: " + d.last_update; }}
  }})
  .catch(function() {{}});
</script>
</body>
</html>"""

    out = settings.dashboard_output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    logger.success(f"Dashboard gerado: {out}")
    return out
