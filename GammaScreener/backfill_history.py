"""Backfill de ~12 meses de historico de Gamma Flip, um ponto por mes.

Roda uma vez (manual, `python backfill_history.py`) pra reconstruir o
passado usando dado 100% real: OI oficial da B3 de cada mes (arquivo
publico historico, confirmado disponivel voltando 12+ meses) + spot e
volatilidade implicita REAIS da propria OpLab, via
`/market/historical/options/{spot}/{from}/{to}` -- endpoint de dados
historicos de opcoes (IV/gregas/spot por opcao/dia) achado por engenharia
reversa do spec OpenAPI, confirmado funcionando voltando a pelo menos
jun/2025 (ver oplab_client.get_historical_options). Sem proxy nenhum: a IV
usada no calculo historico e a mesma grandeza (implicita) usada no cockpit
ao vivo, so que do dia certo.

Pra frente, o warmer em server.py adiciona o ponto do dia corrente usando
IV ao vivo da OpLab tambem -- o metodo passado/presente ficou consistente.
"""

import statistics
import sys
import time
import traceback
from datetime import date, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent / ".env")

import b3_oi_client
import oplab_client
import history_store
from gex_engine import flatten_legs_from_oi, gex_profile_sweep

MONTHS_BACK = 13
IV_SOURCE = "oplab_historical"


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


def _real_iv_and_spot(ticker, ref_date, window_days=4):
    """Busca IV mediana (real, da propria OpLab, entre todas as opcoes do
    ativo naquele pregao) e spot no dia de ref_date -- janela de alguns dias
    pra frente pra sempre cair num pregao com dado, mesmo se ref_date cair
    perto de fim de semana/feriado. Mediana em vez de media pra nao deixar
    uma opcao ilíquida/OTM extrema (IV as vezes degenerada) distorcer o
    numero representativo do dia.
    """
    frm = ref_date.isoformat()
    to = (ref_date + timedelta(days=window_days)).isoformat()
    records = oplab_client.get_historical_options(ticker, frm, to)
    if not records:
        return None, None

    by_date = {}
    for r in records:
        d = r.get("time", "")[:10]
        by_date.setdefault(d, []).append(r)

    target_date = min(by_date.keys(), key=lambda d: abs((date.fromisoformat(d) - ref_date).days), default=None)
    if target_date is None:
        return None, None

    day_records = by_date[target_date]
    vols = [r["volatility"] for r in day_records if r.get("volatility") and r["volatility"] > 0]
    spot = day_records[0].get("spot", {}).get("price")
    if not vols or spot is None:
        return None, None
    return statistics.median(vols) / 100.0, float(spot)


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
            print(f"  Arquivo real (OI) usado: {ref_date}")
            index = b3_oi_client.build_root_index(data)

            done = 0
            for asset in universe:
                ticker, root = asset["ticker"], asset["root"]
                existing = history_store.get_snapshot(ticker, ref_date.isoformat())
                if existing is not None and existing.get("iv_source") == IV_SOURCE:
                    done += 1
                    continue
                try:
                    iv, spot = _real_iv_and_spot(ticker, ref_date)
                    if iv is None or spot is None:
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
                        iv_source=IV_SOURCE,
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
