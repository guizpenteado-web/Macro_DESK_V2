"""
Servico de calculo de indicadores e market breadth.
Usa pandas vetorizado para eficiencia com 80+ ativos.
"""
from __future__ import annotations
import pandas as pd
from app.database.connection import engine, get_session
from app.database.repository import (
    IndicatorRepository, BreadthRepository,
    IndexComponentRepository, IndexBreadthRepository,
)
from app.utils.logger import logger


def calculate_indicators() -> dict:
    """
    1. Carrega todos os precos do banco.
    2. Calcula SMA21/50/200 e flags above_ para cada ativo/dia.
    3. Calcula breadth diario (% acima de cada SMA).
    4. Salva tudo no banco.
    """
    df = pd.read_sql(
        """SELECT p.ticker, p.date, p.close
           FROM prices p
           JOIN assets a ON a.ticker = p.ticker
           WHERE a.is_active = 1
           ORDER BY p.ticker, p.date""",
        engine,
    )
    if df.empty:
        logger.warning("Sem precos no banco. Rode o download primeiro.")
        return {"tickers": 0, "rows": 0}

    df["date"] = pd.to_datetime(df["date"])
    pivot = df.pivot(index="date", columns="ticker", values="close")

    sma21  = pivot.rolling(21,  min_periods=21).mean()
    sma50  = pivot.rolling(50,  min_periods=50).mean()
    sma200 = pivot.rolling(200, min_periods=200).mean()

    above21  = pivot > sma21
    above50  = pivot > sma50
    above200 = pivot > sma200

    # ── RSI(14) vetorizado ───────────────────────────────────────
    delta    = pivot.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=13, min_periods=14).mean()
    avg_loss = loss.ewm(com=13, min_periods=14).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    rsi14    = 100 - (100 / (1 + rs))

    above_rsi70 = rsi14 > 70
    below_rsi30 = rsi14 < 30

    # ── Salva indicadores por ativo ──────────────────────────────
    rows_total = 0
    for ticker in pivot.columns:
        ind_rows = (
            pd.DataFrame({
                "ticker":       ticker,
                "date":         pivot.index.date,
                "close":        pivot[ticker].values,
                "sma21":        sma21[ticker].values,
                "sma50":        sma50[ticker].values,
                "sma200":       sma200[ticker].values,
                "above_sma21":  above21[ticker].values,
                "above_sma50":  above50[ticker].values,
                "above_sma200": above200[ticker].values,
                "rsi14":        rsi14[ticker].values,
                "above_rsi70":  above_rsi70[ticker].values,
                "below_rsi30":  below_rsi30[ticker].values,
            })
            .dropna(subset=["close"])
            .to_dict("records")
        )
        with get_session() as s:
            rows_total += IndicatorRepository(s).bulk_upsert(ind_rows)

    # ── Composição ponto-a-ponto (point-in-time) ─────────────────
    # Para cada data D, usamos apenas ações que JÁ EXISTIAM com
    # pelo menos 5 dias de histórico antes de D (proxy de IPO).
    # Isso evita que ações recém-listadas (RDOR3, CMIN3, VAMO3 etc.)
    # sejam contadas retroativamente em períodos anteriores ao seu IPO —
    # principal causa de divergência vs. plataformas como Sharketo.
    first_date = {}
    for ticker in pivot.columns:
        idx = pivot[ticker].first_valid_index()
        first_date[ticker] = idx  # pd.Timestamp or None

    breadth_rows = []
    for d in pivot.index:
        # Universo elegível: ação existia com pelo menos 5 dias antes de D
        eligible_cols = [
            t for t in pivot.columns
            if first_date.get(t) is not None and (d - first_date[t]).days >= 5
        ]
        if not eligible_cols:
            continue

        valid = pivot.loc[d, eligible_cols].notna()
        if not valid.any():
            continue

        # SMA21: só conta ativos com SMA21 válida
        valid21 = sma21.loc[d, eligible_cols].notna() & valid
        total21 = int(valid21.sum())
        n21 = int(above21.loc[d, eligible_cols][valid21].sum()) if total21 > 0 else 0

        # SMA50: só conta ativos com SMA50 válida
        valid50 = sma50.loc[d, eligible_cols].notna() & valid
        total50 = int(valid50.sum())
        n50 = int(above50.loc[d, eligible_cols][valid50].sum()) if total50 > 0 else 0

        # SMA200: só conta ativos com SMA200 válida
        valid200 = sma200.loc[d, eligible_cols].notna() & valid
        total200 = int(valid200.sum())
        n200 = int(above200.loc[d, eligible_cols][valid200].sum()) if total200 > 0 else 0

        # Período de aquecimento: sem dados SMA200 ainda → pula o dia
        if total200 == 0:
            continue

        # total_assets: conta de ativos elegíveis com SMA200 válida
        total = total200

        # RSI breadth (conta apenas ativos elegíveis com RSI válido)
        rsi_valid = rsi14.loc[d, eligible_cols].notna() & valid
        rsi_total = int(rsi_valid.sum())
        if rsi_total > 0:
            n_ov  = int(below_rsi30.loc[d, eligible_cols][rsi_valid].sum())
            n_ob  = int(above_rsi70.loc[d, eligible_cols][rsi_valid].sum())
            n_nt  = rsi_total - n_ov - n_ob
        else:
            n_ov = n_ob = n_nt = 0

        breadth_rows.append({
            "date":         d.date(),
            "total_assets": total,
            "above_sma21":  n21,
            "above_sma50":  n50,
            "above_sma200": n200,
            "pct_sma21":    round(n21  / total21  * 100, 2) if total21  > 0 else 0.0,
            "pct_sma50":    round(n50  / total50  * 100, 2) if total50  > 0 else 0.0,
            "pct_sma200":   round(n200 / total200 * 100, 2),
            "count_rsi_oversold":   n_ov,
            "count_rsi_neutral":    n_nt,
            "count_rsi_overbought": n_ob,
            "pct_rsi_oversold":   round(n_ov / rsi_total * 100, 2) if rsi_total else 0.0,
            "pct_rsi_neutral":    round(n_nt / rsi_total * 100, 2) if rsi_total else 0.0,
            "pct_rsi_overbought": round(n_ob / rsi_total * 100, 2) if rsi_total else 0.0,
        })

    with get_session() as s:
        repo = BreadthRepository(s)
        for row in breadth_rows:
            repo.upsert(row)

    logger.success(
        f"Indicadores: {len(pivot.columns)} ativos | "
        f"{rows_total} registros | {len(breadth_rows)} dias de breadth"
    )
    return {"tickers": len(pivot.columns), "rows": rows_total, "breadth_days": len(breadth_rows)}


def calculate_index_breadth() -> dict:
    """
    Calcula breadth para IDIV, IFNC, EWZ, IBLV usando os precos ja no banco.
    Aplica a mesma logica ponto-a-ponto do calculo IBOV.
    """
    # Coleta todos os tickers dos sub-indices
    with get_session() as s:
        comp_df = pd.read_sql(
            "SELECT index_code, ticker FROM index_components", engine
        )

    if comp_df.empty:
        logger.warning("Sem componentes de indices. Rode sync_index_components() primeiro.")
        return {}

    all_tickers = comp_df["ticker"].unique().tolist()
    tickers_sql = "','".join(all_tickers)

    df = pd.read_sql(
        f"SELECT ticker, date, close FROM prices WHERE ticker IN ('{tickers_sql}') ORDER BY ticker, date",
        engine,
    )
    if df.empty:
        logger.warning("Sem precos para os componentes dos sub-indices.")
        return {}

    df["date"] = pd.to_datetime(df["date"])
    pivot = df.pivot(index="date", columns="ticker", values="close")

    # Calcula SMAs e RSI para todos os tickers dos indices
    sma21  = pivot.rolling(21,  min_periods=21).mean()
    sma50  = pivot.rolling(50,  min_periods=50).mean()
    sma200 = pivot.rolling(200, min_periods=200).mean()
    above21  = pivot > sma21
    above50  = pivot > sma50
    above200 = pivot > sma200

    delta    = pivot.diff()
    gain     = delta.clip(lower=0)
    loss     = (-delta).clip(lower=0)
    avg_gain = gain.ewm(com=13, min_periods=14).mean()
    avg_loss = loss.ewm(com=13, min_periods=14).mean()
    rs       = avg_gain / avg_loss.replace(0, float("nan"))
    rsi14    = 100 - (100 / (1 + rs))
    above_rsi70 = rsi14 > 70
    below_rsi30 = rsi14 < 30

    results: dict[str, int] = {}

    for index_code, group in comp_df.groupby("index_code"):
        tickers = [t for t in group["ticker"].tolist() if t in pivot.columns]
        if not tickers:
            logger.warning(f"{index_code}: nenhum ticker com dados de preco.")
            continue

        sub = pivot[tickers]
        first_date = {t: sub[t].first_valid_index() for t in tickers}

        breadth_rows = []
        for d in sub.index:
            eligible = [
                t for t in tickers
                if first_date.get(t) is not None and (d - first_date[t]).days >= 5
            ]
            if not eligible:
                continue

            valid = sub.loc[d, eligible].notna()
            if not valid.any():
                continue

            v200 = sma200.loc[d, eligible].notna() & valid
            total200 = int(v200.sum())
            if total200 == 0:
                continue

            v21 = sma21.loc[d, eligible].notna() & valid
            v50 = sma50.loc[d, eligible].notna() & valid
            t21 = int(v21.sum()); t50 = int(v50.sum())

            n21  = int(above21.loc[d, eligible][v21].sum())  if t21  > 0 else 0
            n50  = int(above50.loc[d, eligible][v50].sum())  if t50  > 0 else 0
            n200 = int(above200.loc[d, eligible][v200].sum())

            rv = rsi14.loc[d, eligible].notna() & valid
            rtot = int(rv.sum())
            n_ov = int(below_rsi30.loc[d, eligible][rv].sum()) if rtot > 0 else 0
            n_ob = int(above_rsi70.loc[d, eligible][rv].sum()) if rtot > 0 else 0
            n_nt = rtot - n_ov - n_ob if rtot > 0 else 0

            breadth_rows.append({
                "index_code":         index_code,
                "date":               d.date(),
                "total_assets":       total200,
                "pct_sma21":  round(n21  / t21   * 100, 2) if t21   > 0 else 0.0,
                "pct_sma50":  round(n50  / t50   * 100, 2) if t50   > 0 else 0.0,
                "pct_sma200": round(n200 / total200 * 100, 2),
                "pct_rsi_oversold":   round(n_ov / rtot * 100, 2) if rtot else 0.0,
                "pct_rsi_neutral":    round(n_nt / rtot * 100, 2) if rtot else 0.0,
                "pct_rsi_overbought": round(n_ob / rtot * 100, 2) if rtot else 0.0,
            })

        with get_session() as s:
            repo = IndexBreadthRepository(s)
            for row in breadth_rows:
                repo.upsert(row)

        results[index_code] = len(breadth_rows)
        logger.success(f"Breadth {index_code}: {len(breadth_rows)} dias")

    # Salva indicador mais recente por ticker para exibicao nas tabelas
    ind_rows = []
    for ticker in all_tickers:
        if ticker not in pivot.columns:
            continue
        last_idx = pivot[ticker].last_valid_index()
        if last_idx is None:
            continue
        d   = last_idx
        c   = float(pivot.loc[d, ticker])
        s21 = float(sma21.loc[d, ticker])   if pd.notna(sma21.loc[d, ticker])  else None
        s50 = float(sma50.loc[d, ticker])   if pd.notna(sma50.loc[d, ticker])  else None
        s200= float(sma200.loc[d, ticker])  if pd.notna(sma200.loc[d, ticker]) else None
        r   = float(rsi14.loc[d, ticker])   if pd.notna(rsi14.loc[d, ticker])  else None
        ind_rows.append({
            "ticker":       ticker,
            "date":         d.date(),
            "close":        c,
            "sma21":        s21,
            "sma50":        s50,
            "sma200":       s200,
            "above_sma21":  bool(c > s21)   if s21  is not None else None,
            "above_sma50":  bool(c > s50)   if s50  is not None else None,
            "above_sma200": bool(c > s200)  if s200 is not None else None,
            "rsi14":        r,
            "above_rsi70":  bool(r > 70)    if r is not None else None,
            "below_rsi30":  bool(r < 30)    if r is not None else None,
        })

    if ind_rows:
        with get_session() as s:
            IndicatorRepository(s).bulk_upsert(ind_rows)
        logger.success(f"Indicadores sub-indices: {len(ind_rows)} tickers atualizados")

    return results