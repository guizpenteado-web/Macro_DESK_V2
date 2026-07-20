"""Calendário econômico BR+US.

US: ForexFactory (nfs.faireconomy.media) — feed JSON público e gratuito,
impacto (Low/Medium/High) já vem pronto. Tem rate-limit agressivo (429 fácil
em requests repetidos), por isso cacheado com TTL generoso (_FF_TTL).

BR: página pública do TradingEconomics (tradingeconomics.com/brazil/calendar)
— não tem o bloqueio Cloudflare que o investing.com passou a ter (nem do IP
do VPS nem do residencial local). Essa página gratuita não expõe nível de
importância por evento (isso só vem na API paga), por isso usamos uma
whitelist curada (_BR_WHITELIST) com os eventos relevantes e impacto manual.

Migração de 20/jul/2026 — substitui o scraping do investing.com via
cloudscraper (bloqueado por desafio Cloudflare tanto no IP do VPS quanto no
IP residencial local desde 17/jul/2026) e elimina o mecanismo de push do PC
local, que só existia pra contornar esse bloqueio por IP — como as fontes
novas não bloqueiam nenhum dos dois IPs, o Hub busca direto.
"""

import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup


class EconomicCalendar:
    _FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    _ff_cache: dict = {"ts": 0.0, "data": None}
    _FF_TTL = 900  # 15min — o feed do ForexFactory tem rate-limit agressivo

    _TE_URL = "https://tradingeconomics.com/brazil/calendar"
    _te_cache: dict = {"ts": 0.0, "data": None}
    _TE_TTL = 1800  # 30min

    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }

    # Eventos BR relevantes (nome como aparece no TradingEconomics, lowercase)
    # -> (impacto, nome traduzido). Curada manualmente porque a página grátis
    # do TE não expõe nível de importância por evento.
    _BR_WHITELIST: dict[str, tuple[str, str]] = {
        "interest rate decision":       ("High", "Decisão de Juros (Selic)"),
        "inflation rate mom":           ("High", "IPCA (M/M)"),
        "inflation rate yoy":           ("High", "IPCA (A/A)"),
        "unemployment rate":            ("High", "Taxa de Desemprego"),
        "net payrolls":                 ("High", "CAGED — Payroll Líquido"),
        "gdp growth rate qoq":          ("High", "PIB (T/T)"),
        "gdp growth rate yoy":          ("High", "PIB (A/A)"),
        "balance of trade":             ("High", "Balança Comercial"),
        "bcb copom meeting minutes":    ("High", "Ata do Copom"),
        "bcb focus market readout":     ("Medium", "BCB Focus"),
        "ipca mid-month cpi mom":       ("Medium", "IPCA-15 (M/M)"),
        "ipca mid-month cpi yoy":       ("Medium", "IPCA-15 (A/A)"),
        "igp-m inflation mom":          ("Medium", "Inflação IGP-M"),
        "retail sales mom":             ("Medium", "Vendas no Varejo (M/M)"),
        "retail sales yoy":             ("Medium", "Vendas no Varejo (A/A)"),
        "industrial production mom":    ("Medium", "Produção Industrial (M/M)"),
        "industrial production yoy":    ("Medium", "Produção Industrial (A/A)"),
        "ppi mom":                      ("Medium", "IPP (M/M)"),
        "ppi yoy":                      ("Medium", "IPP (A/A)"),
        "current account":              ("Medium", "Conta Corrente"),
        "business confidence":          ("Medium", "Confiança Empresarial"),
        "fgv consumer confidence":      ("Medium", "Confiança do Consumidor (FGV)"),
        "s&p global composite pmi":     ("Medium", "PMI Composto S&P Global"),
        "s&p global manufacturing pmi": ("Medium", "PMI Industrial S&P Global"),
        "s&p global services pmi":      ("Medium", "PMI Serviços S&P Global"),
        "nominal budget balance":       ("Medium", "Resultado Nominal (Setor Público)"),
        "ibc-br economic activity":     ("Medium", "IBC-Br (Atividade Econômica)"),
    }

    # ── tradução EN→PT pros eventos US (ForexFactory) ────────────────────────
    _TRANSLATIONS: list[tuple[str, str]] = [
        (r"\bm/m\b", "(M/M)"), (r"\by/y\b", "(A/A)"), (r"\bq/q\b", "(T/T)"),
        ("Nonfarm Payrolls",           "Payrolls Não-Agrícolas"),
        ("Non-Farm Employment Change", "Variação Payrolls Não-Agrícolas"),
        ("Private Nonfarm Payrolls",   "Empregos Privados"),
        ("ADP Nonfarm Employment Change", "Emprego Privado ADP"),
        ("ADP Non-Farm Employment Change", "Emprego Privado ADP"),
        ("Unemployment Claims",        "Pedidos Seguro-Desemprego"),
        ("Unemployment Rate",          "Taxa de Desemprego"),
        ("Average Hourly Earnings",    "Remuneração Média/Hora"),
        ("CPI",                        "CPI"),
        ("Core CPI",                   "CPI Núcleo"),
        ("PPI",                        "PPI"),
        ("Core PPI",                   "PPI Núcleo"),
        ("Core PCE Price Index",       "PCE Núcleo"),
        ("PCE Price Index",            "PCE"),
        ("GDP",                        "PIB"),
        ("Industrial Production",      "Produção Industrial"),
        ("Retail Sales",               "Vendas no Varejo"),
        ("Core Retail Sales",          "Vendas no Varejo Núcleo"),
        ("Building Permits",           "Licenças de Construção"),
        ("Housing Starts",             "Início de Construções"),
        ("Existing Home Sales",        "Vendas Casas Usadas"),
        ("New Home Sales",             "Vendas Casas Novas"),
        ("ISM Manufacturing PMI",      "PMI Industrial ISM"),
        ("ISM Manufacturing Prices",   "Preços Indústria ISM"),
        ("ISM Services PMI",           "PMI Serviços ISM"),
        ("ISM Non-Manufacturing PMI",  "PMI Serviços ISM"),
        ("Final Manufacturing PMI",    "PMI Industrial Final"),
        ("Final Services PMI",         "PMI Serviços Final"),
        ("Prelim UoM Consumer Sentiment", "Sentimento U. Michigan (Prévia)"),
        ("Revised UoM Consumer Sentiment", "Sentimento U. Michigan (Revisado)"),
        ("CB Consumer Confidence",     "Confiança do Consumidor (CB)"),
        ("Federal Funds Rate",         "Taxa dos Fed Funds"),
        ("FOMC Statement",             "Comunicado do FOMC"),
        ("FOMC Meeting Minutes",       "Ata do FOMC"),
        ("FOMC Press Conference",      "Coletiva do Fed"),
        ("FOMC Member",                "Membro do FOMC"),
        ("Fed Chair",                  "Presidente do Fed"),
        ("Federal Funds Rate Decision", "Decisão de Juros do Fed"),
        ("Trade Balance",              "Balança Comercial"),
        ("Current Account",            "Conta Corrente"),
        ("Crude Oil Inventories",      "Estoques de Petróleo"),
        ("Natural Gas Storage",        "Armazenamento Gás Natural"),
        ("Consumer Confidence",        "Confiança do Consumidor"),
        ("Speaks",                     "Discursa"),
        ("Testifies",                  "Depoimento"),
    ]

    @classmethod
    def _translate(cls, name: str) -> str:
        for pattern, replacement in cls._TRANSLATIONS:
            if pattern.startswith(r"\b"):
                name = re.sub(pattern, replacement, name, flags=re.IGNORECASE)
            else:
                name = name.replace(pattern, replacement)
        return name

    # ── US — ForexFactory ─────────────────────────────────────────────────
    @classmethod
    def _fetch_forexfactory(cls) -> list[dict]:
        now = time.time()
        if cls._ff_cache["data"] is not None and now - cls._ff_cache["ts"] < cls._FF_TTL:
            return cls._ff_cache["data"]
        events: list[dict] = []
        try:
            r = requests.get(cls._FF_URL, headers=cls._HEADERS, timeout=20)
            r.raise_for_status()
            raw = r.json()
            for e in raw:
                if e.get("country") != "USD" or e.get("impact") not in ("High", "Medium"):
                    continue
                try:
                    dt = datetime.fromisoformat(e["date"]).replace(tzinfo=None)
                except (ValueError, KeyError):
                    continue
                events.append({
                    "datetime": dt.isoformat(),
                    "date": dt.strftime("%a, %d %b %Y"),
                    "time": dt.strftime("%H:%M"),
                    "country": "United States",
                    "currency": "USD",
                    "impact": e["impact"],
                    "event": cls._translate(e.get("title", "")),
                    "actual": e.get("actual") or "",
                    "forecast": e.get("forecast") or "",
                    "previous": e.get("previous") or "",
                })
            cls._ff_cache = {"ts": now, "data": events}
            return events
        except Exception:
            # mantém o que tiver em cache (mesmo vencido) em vez de zerar;
            # NÃO atualiza o cache com lista vazia, pra próxima chamada
            # tentar de novo em vez de ficar 15min travado sem dado nenhum
            return cls._ff_cache["data"] if cls._ff_cache["data"] is not None else []

    # ── BR — TradingEconomics (página pública) ────────────────────────────
    @classmethod
    def _fetch_tradingeconomics_br(cls) -> list[dict]:
        now = time.time()
        if cls._te_cache["data"] is not None and now - cls._te_cache["ts"] < cls._TE_TTL:
            return cls._te_cache["data"]
        events: list[dict] = []
        try:
            r = requests.get(cls._TE_URL, headers=cls._HEADERS, timeout=25)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "html.parser")
            table = soup.find(id="calendar")
            current_date = None
            if table:
                for row in table.find_all("tr"):
                    date_td = row.find("td", class_=re.compile(r"^\d{4}-\d{2}-\d{2}$"))
                    if date_td:
                        current_date = date_td["class"][0]
                    ev_link = row.find("a", class_="calendar-event")
                    if not ev_link or not current_date:
                        continue
                    whitelisted = cls._BR_WHITELIST.get(ev_link.get_text(strip=True).lower())
                    if not whitelisted:
                        continue
                    impact, pt_name = whitelisted
                    time_span = row.find("span", class_=re.compile(r"^event-"))
                    time_txt = time_span.get_text(strip=True) if time_span else ""
                    try:
                        dt = datetime.strptime(f"{current_date} {time_txt}", "%Y-%m-%d %I:%M %p")
                    except ValueError:
                        dt = datetime.strptime(current_date, "%Y-%m-%d")
                    actual = row.find("span", id="actual")
                    previous = row.find("span", id="previous")
                    consensus = row.find(id="consensus")
                    events.append({
                        "datetime": dt.isoformat(),
                        "date": dt.strftime("%a, %d %b %Y"),
                        "time": dt.strftime("%H:%M"),
                        "country": "Brazil",
                        "currency": "BRL",
                        "impact": impact,
                        "event": pt_name,
                        "actual": actual.get_text(strip=True) if actual else "",
                        "forecast": consensus.get_text(strip=True) if consensus else "",
                        "previous": previous.get_text(strip=True) if previous else "",
                    })
            cls._te_cache = {"ts": now, "data": events}
            return events
        except Exception:
            return cls._te_cache["data"] if cls._te_cache["data"] is not None else []

    @classmethod
    def fetch_filtered(cls, days: int = 7) -> list[dict]:
        """Brazil + US (High+Medium), sorted by datetime, dentro da janela."""
        floor = datetime.now() - timedelta(days=1)  # mantém eventos recém-liberados
        ceiling = datetime.now() + timedelta(days=days)
        combined = cls._fetch_forexfactory() + cls._fetch_tradingeconomics_br()
        combined = [e for e in combined if floor <= datetime.fromisoformat(e["datetime"]) <= ceiling]
        combined.sort(key=lambda e: e["datetime"])
        return combined
