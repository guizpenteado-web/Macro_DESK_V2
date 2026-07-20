"""Calendário econômico BR+US.

Ambas as fontes vêm da página pública do TradingEconomics (não a API paga):
tradingeconomics.com/brazil/calendar e tradingeconomics.com/united-states/calendar
— HTML server-rendered, sem bloqueio Cloudflare (ao contrário do investing.com,
que bloqueou tanto o IP do VPS quanto o residencial local desde 17/jul/2026).

Essas páginas gratuitas não expõem nível de importância por evento (isso só
vem na API paga), por isso usamos whitelists curadas (_BR_WHITELIST,
_US_WHITELIST) com os eventos relevantes e impacto (High/Medium) manual —
o mesmo padrão pros dois países.

Migração de 20/jul/2026 — substitui o scraping do investing.com via
cloudscraper e elimina o mecanismo de push do PC local, que só existia pra
contornar o bloqueio por IP. Ajuste de 20/jul/2026 (mesmo dia): a primeira
versão usava o feed do ForexFactory pro US, mas esse feed só cobre "essa
semana" (sem next-week/month), deixando o calendário quase vazio em semanas
fracas — trocado pelo TradingEconomics também, que tem horizonte de várias
semanas à frente igual o BR.

Fonte validada em 20/jul/2026 como oficial e confiável: 6 valores conferidos
individualmente contra fonte primária/independente (Fed Funds Rate, Core PCE
YoY, PCE YoY, Desemprego BR, IPCA-15 MoM, Selic) bateram exato. Detalhes em
memória (reference_sources_database / feedback_calendar_cloudflare_block).
"""

import re
import time
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup


class EconomicCalendar:
    _HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    }
    _TE_TTL = 1800  # 30min

    _BR_URL = "https://tradingeconomics.com/brazil/calendar"
    _US_URL = "https://tradingeconomics.com/united-states/calendar"

    _br_cache: dict = {"ts": 0.0, "data": None}
    _us_cache: dict = {"ts": 0.0, "data": None}

    # Eventos relevantes (nome como aparece no TradingEconomics, lowercase)
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

    _US_WHITELIST: dict[str, tuple[str, str]] = {
        "non farm payrolls":                    ("High", "Payrolls Não-Agrícolas"),
        "nonfarm payrolls private":              ("High", "Empregos Privados"),
        "government payrolls":                   ("Medium", "Empregos Governo"),
        "manufacturing payrolls":                ("Medium", "Empregos Indústria"),
        "unemployment rate":                     ("High", "Taxa de Desemprego"),
        "adp employment change":                 ("High", "Emprego Privado ADP"),
        "inflation rate mom":                    ("High", "CPI (M/M)"),
        "inflation rate yoy":                    ("High", "CPI (A/A)"),
        "core inflation rate mom":               ("High", "CPI Núcleo (M/M)"),
        "core inflation rate yoy":               ("High", "CPI Núcleo (A/A)"),
        "pce price index mom":                   ("High", "PCE (M/M)"),
        "pce price index yoy":                   ("High", "PCE (A/A)"),
        "core pce price index mom":              ("High", "PCE Núcleo (M/M)"),
        "core pce price index yoy":               ("High", "PCE Núcleo (A/A)"),
        "gdp growth rate qoq adv":                ("High", "PIB (T/T, prévia)"),
        "fed interest rate decision":             ("High", "Decisão de Juros do Fed"),
        "fed press conference":                   ("High", "Coletiva do Fed"),
        "fomc meeting minutes":                   ("High", "Ata do FOMC"),
        "fomc statement":                         ("High", "Comunicado do FOMC"),
        "ism manufacturing pmi":                  ("High", "PMI Industrial ISM"),
        "ism services pmi":                       ("High", "PMI Serviços ISM"),
        "retail sales mom":                       ("High", "Vendas no Varejo (M/M)"),
        "ppi mom":                                ("Medium", "PPI (M/M)"),
        "ppi yoy":                                ("Medium", "PPI (A/A)"),
        "core ppi mom":                           ("Medium", "PPI Núcleo (M/M)"),
        "core ppi yoy":                           ("Medium", "PPI Núcleo (A/A)"),
        "initial jobless claims":                 ("Medium", "Pedidos Seguro-Desemprego"),
        "continuing jobless claims":              ("Medium", "Pedidos Contínuos Desemprego"),
        "jolts job openings":                     ("Medium", "Vagas JOLTS"),
        "durable goods orders mom":                ("Medium", "Pedidos Bens Duráveis (M/M)"),
        "building permits":                       ("Medium", "Licenças de Construção"),
        "housing starts":                         ("Medium", "Início de Construções"),
        "existing home sales":                    ("Medium", "Vendas Casas Usadas"),
        "new home sales":                         ("Medium", "Vendas Casas Novas"),
        "michigan consumer sentiment prel":       ("Medium", "Sentimento U. Michigan (Prévia)"),
        "michigan consumer sentiment final":      ("Medium", "Sentimento U. Michigan (Final)"),
        "balance of trade":                       ("Medium", "Balança Comercial"),
        "goods trade balance adv":                ("Medium", "Balança Comercial de Bens (Prévia)"),
        "personal income mom":                    ("Medium", "Renda Pessoal (M/M)"),
        "personal spending mom":                  ("Medium", "Gastos Pessoais (M/M)"),
        "factory orders mom":                     ("Medium", "Pedidos de Fábricas (M/M)"),
        "chicago pmi":                            ("Medium", "PMI Chicago"),
        "s&p global composite pmi flash":         ("Medium", "PMI Composto S&P Global (Prévia)"),
        "s&p global manufacturing pmi flash":      ("Medium", "PMI Industrial S&P Global (Prévia)"),
        "s&p global services pmi flash":          ("Medium", "PMI Serviços S&P Global (Prévia)"),
        "s&p global composite pmi final":         ("Medium", "PMI Composto S&P Global"),
        "s&p global manufacturing pmi final":     ("Medium", "PMI Industrial S&P Global"),
        "s&p global services pmi final":          ("Medium", "PMI Serviços S&P Global"),
        "employment cost index qoq":              ("Medium", "Índice Custo de Emprego (T/T)"),
        "eia crude oil stocks change":             ("Medium", "Estoques de Petróleo (EIA)"),
        "consumer confidence":                    ("Medium", "Confiança do Consumidor"),
        "monthly budget statement":               ("Medium", "Resultado Orçamentário Mensal"),
        "total vehicle sales":                    ("Medium", "Vendas de Veículos"),
        "s&p/case-shiller home price mom":        ("Medium", "Preços Case-Shiller (M/M)"),
        "s&p/case-shiller home price yoy":        ("Medium", "Preços Case-Shiller (A/A)"),
        "average hourly earnings mom":            ("Medium", "Remuneração Média/Hora (M/M)"),
        "average hourly earnings yoy":            ("Medium", "Remuneração Média/Hora (A/A)"),
    }

    # ── scraper genérico do calendário público do TradingEconomics ────────
    @classmethod
    def _scrape_te_calendar(cls, url: str, whitelist: dict, country: str, currency: str) -> list[dict]:
        r = requests.get(url, headers=cls._HEADERS, timeout=25)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        table = soup.find(id="calendar")
        events: list[dict] = []
        current_date = None
        if table:
            for row in table.find_all("tr"):
                date_td = row.find("td", class_=re.compile(r"^\d{4}-\d{2}-\d{2}$"))
                if date_td:
                    current_date = date_td["class"][0]
                ev_link = row.find("a", class_="calendar-event")
                if not ev_link or not current_date:
                    continue
                whitelisted = whitelist.get(ev_link.get_text(strip=True).lower())
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
                    "country": country,
                    "currency": currency,
                    "impact": impact,
                    "event": pt_name,
                    "actual": actual.get_text(strip=True) if actual else "",
                    "forecast": consensus.get_text(strip=True) if consensus else "",
                    "previous": previous.get_text(strip=True) if previous else "",
                })
        return events

    @classmethod
    def _fetch_tradingeconomics_br(cls) -> list[dict]:
        now = time.time()
        if cls._br_cache["data"] is not None and now - cls._br_cache["ts"] < cls._TE_TTL:
            return cls._br_cache["data"]
        try:
            events = cls._scrape_te_calendar(cls._BR_URL, cls._BR_WHITELIST, "Brazil", "BRL")
            cls._br_cache = {"ts": now, "data": events}
            return events
        except Exception:
            return cls._br_cache["data"] if cls._br_cache["data"] is not None else []

    @classmethod
    def _fetch_tradingeconomics_us(cls) -> list[dict]:
        now = time.time()
        if cls._us_cache["data"] is not None and now - cls._us_cache["ts"] < cls._TE_TTL:
            return cls._us_cache["data"]
        try:
            events = cls._scrape_te_calendar(cls._US_URL, cls._US_WHITELIST, "United States", "USD")
            cls._us_cache = {"ts": now, "data": events}
            return events
        except Exception:
            return cls._us_cache["data"] if cls._us_cache["data"] is not None else []

    @classmethod
    def fetch_filtered(cls, days: int = 7) -> list[dict]:
        """Brazil + US (High+Medium), sorted by datetime, dentro da janela."""
        floor = datetime.now() - timedelta(days=1)  # mantém eventos recém-liberados
        ceiling = datetime.now() + timedelta(days=days)
        combined = cls._fetch_tradingeconomics_br() + cls._fetch_tradingeconomics_us()
        combined = [e for e in combined if floor <= datetime.fromisoformat(e["datetime"]) <= ceiling]
        combined.sort(key=lambda e: e["datetime"])
        return combined
