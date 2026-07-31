"""Backfill de ~12 meses de historico de Gamma Flip, um ponto por mes.

Roda uma vez (manual, `python backfill_history.py`) pra reconstruir o
passado usando dado real: OI oficial da B3 de cada mes (arquivo publico
historico, confirmado disponivel voltando 12+ meses) + preco de fechamento
real do ativo naquela data (yfinance) + volatilidade realizada (desvio
padrao anualizado dos retornos dos ultimos ~21 pregoes ate a data de
referencia, calculada a partir de preco real -- nao inventada) como proxy
de IV, ja que IV implicita historica nao esta disponivel de graca em
nenhuma fonte.

Pra frente, o warmer em server.py adiciona o ponto do dia corrente usando
IV *real* (ao vivo, OpLab) -- so o passado usa o proxy, e cada ponto fica
marcado com `iv_source` pra deixar isso rastreavel/transparente na UI.
"""

import sys
import time
import traceback
from datetime import date, timedelta

import numpy as np
import yfinance as yf

import b3_oi_client
import history_store
from gex_engine import flatten_legs_from_oi, gex_profile_sweep

MONTHS_BACK = 13
SELIC_RATE = 0.1425


def _target_dates(months_back):
    today = date.today()
    dates = []
    y, m = today.year, today.month
    for i in range(1, months_back + 1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        dates.append(date(yy, mm, min(today.day, 28)))
    return sorted(dates)


def _realized_vol(yf_ticker, ref_date, window=21):
    start = ref_date - timedelta(days=window * 3)  # folga pra fins de semana/feriados
    end = ref_date + timedelta(days=1)
    hist = yf_ticker.history(start=start.isoformat(), end=end.isoformat())
    closes = hist["Close"].dropna()
    if len(closes) < 5:
        return None
    closes = closes.iloc[-window:] if len(closes) > window else closes
    log_ret = np.diff(np.log(closes.values))
    if len(log_ret) < 3:
        return None
    return float(np.std(log_ret, ddof=1) * np.sqrt(252))


def _spot_near(yf_ticker, ref_date, lookback_days=10):
    start = (ref_date - timedelta(days=lookback_days)).isoformat()
    end = (ref_date + timedelta(days=1)).isoformat()
    hist = yf_ticker.history(start=start, end=end)
    closes = hist["Close"].dropna()
    if closes.empty:
        return None
    return float(closes.iloc[-1])


def main():
    print("Buscando universo atual (top 60 por OI hoje)...")
    data_today, ref_today = b3_oi_client.fetch_latest_oi()
    index_today = b3_oi_client.build_root_index(data_today)
    universe = b3_oi_client.build_universe(index_today, top_n=60)
    print(f"  {len(universe)} ativos. Referencia hoje: {ref_today}")

    targets = _target_dates(MONTHS_BACK)
    print(f"Datas-alvo ({len(targets)}): {targets}")

    for target in targets:
        try:
            print(f"\n=== Mes alvo {target} ===")
            data, ref_date = b3_oi_client.fetch_oi_near(target)
            print(f"  Arquivo real usado: {ref_date}")
            index = b3_oi_client.build_root_index(data)

            done = 0
            for asset in universe:
                ticker, root = asset["ticker"], asset["root"]
                if history_store.has_snapshot(ticker, ref_date.isoformat()):
                    done += 1
                    continue
                try:
                    yf_ticker = yf.Ticker(f"{ticker}.SA")
                    spot = _spot_near(yf_ticker, ref_date)
                    iv = _realized_vol(yf_ticker, ref_date)
                    if spot is None or iv is None or iv <= 0:
                        continue
                    oi_legs_raw = b3_oi_client.extract_legs_from_index(index, root)
                    legs = flatten_legs_from_oi(oi_legs_raw, ref_date)
                    if not legs:
                        continue
                    profile = gex_profile_sweep(legs, spot, iv)
                    flip = profile["flip"]
                    # Invariante ja validada no cockpit ao vivo (ver memoria do
                    # projeto): flip abaixo do spot <=> regime positivo, sem
                    # excecao -- equivalente a olhar o sinal do gex_net_total,
                    # mais barato de calcular aqui (nao precisa do by_strike).
                    if flip is not None:
                        regime = "POSITIVO (vol estabiliza)" if flip <= spot else "NEGATIVO (vol amplifica)"
                    else:
                        regime = None
                    history_store.upsert_snapshot(
                        ticker=ticker, root=root, ref_date=ref_date.isoformat(),
                        gamma_flip=flip, spot=spot, regime=regime,
                        iv_source="realized_vol_proxy",
                        computed_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
                    )
                    done += 1
                except Exception:
                    traceback.print_exc()
            print(f"  {done}/{len(universe)} ativos gravados.")
        except Exception:
            print(f"  Falhou o mes {target}:")
            traceback.print_exc()

    print("\nBackfill concluido.")


if __name__ == "__main__":
    main()
