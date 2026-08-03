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
from datetime import datetime, timedelta, timezone
from datetime import time as dtime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

# TradingEconomics serve o horario em UTC por padrao pra visitante sem
# cookie de preferencia de fuso (confirmado ao vivo em 26/jul/2026: "Durable
# Goods Orders", que sai 8:30 ET, aparece na pagina como "12:30 PM" = 8:30
# EDT (UTC-4) + 4h = 12:30 UTC). O scraper original nao convertia isso pra
# nenhum fuso — o horario cru (UTC) ia direto pro frontend como se fosse
# hora de Brasilia, deixando todo evento com hora certa 3h adiantado (Selic
# fixo em UTC-3, sem horario de verao desde 2019, entao a conversao e
# sempre "-3h", sem ambiguidade sazonal).
_BRT = ZoneInfo("America/Sao_Paulo")


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
    # do TE não expõe nível de importância por evento — lista revisada em
    # 21/jul/2026 contra o universo completo de eventos com página própria
    # (linkados) nos calendários BR/US, pra cobrir tudo que é Alto/Médio
    # impacto de fato. Ruído técnico (leilões de título, taxa de hipoteca,
    # sub-relatórios semanais de estoque de petróleo, rig count etc.) fica
    # de fora de propósito — não é omissão, é filtro de baixo impacto.
    _BR_WHITELIST: dict[str, tuple[str, str]] = {
        "interest rate decision":       ("High", "Decisão de Juros (Selic)"),
        "inflation rate mom":           ("High", "IPCA (M/M)"),
        "inflation rate yoy":           ("High", "IPCA (A/A)"),
        "net payrolls":                 ("High", "CAGED — Payroll Líquido"),
        "gdp growth rate qoq":          ("High", "PIB (T/T)"),
        "gdp growth rate yoy":          ("High", "PIB (A/A)"),
        "balance of trade":             ("High", "Balança Comercial"),
        "bcb copom meeting minutes":    ("High", "Ata do Copom"),
        "unemployment rate":            ("Medium", "Taxa de Desemprego"),
        "bcb focus market readout":     ("Medium", "BCB Focus"),
        "ipca mid-month cpi mom":       ("Medium", "IPCA-15 (M/M)"),
        "ipca mid-month cpi yoy":       ("Medium", "IPCA-15 (A/A)"),
        "ipc-fipe inflation mom":       ("Medium", "IPC-Fipe (M/M)"),
        "igp-m inflation mom":          ("Medium", "Inflação IGP-M"),
        "retail sales mom":             ("Medium", "Vendas no Varejo (M/M)"),
        "retail sales yoy":             ("Medium", "Vendas no Varejo (A/A)"),
        "industrial production mom":    ("Medium", "Produção Industrial (M/M)"),
        "industrial production yoy":    ("Medium", "Produção Industrial (A/A)"),
        "ppi mom":                      ("Medium", "IPP (M/M)"),
        "ppi yoy":                      ("Medium", "IPP (A/A)"),
        "current account":              ("Medium", "Conta Corrente"),
        "foreign direct investment":    ("Medium", "Investimento Direto no País"),
        "business confidence":          ("Medium", "Confiança Empresarial"),
        "fgv consumer confidence":      ("Medium", "Confiança do Consumidor (FGV)"),
        "s&p global composite pmi":     ("Medium", "PMI Composto S&P Global"),
        "s&p global manufacturing pmi": ("Medium", "PMI Industrial S&P Global"),
        "s&p global services pmi":      ("Medium", "PMI Serviços S&P Global"),
        "nominal budget balance":       ("Medium", "Resultado Nominal (Setor Público)"),
        "gross debt to gdp":            ("Medium", "Dívida Bruta / PIB"),
        "ibc-br economic activity":     ("Medium", "IBC-Br (Atividade Econômica)"),
    }

    _US_WHITELIST: dict[str, tuple[str, str]] = {
        # ── High ────────────────────────────────────────────────────────
        "non farm payrolls":                      ("High", "Payrolls Não-Agrícolas"),
        "nonfarm payrolls private":                ("High", "Empregos Privados"),
        "unemployment rate":                       ("High", "Taxa de Desemprego"),
        "adp employment change":                   ("High", "Emprego Privado ADP"),
        "inflation rate mom":                      ("High", "CPI (M/M)"),
        "inflation rate yoy":                      ("High", "CPI (A/A)"),
        "core inflation rate mom":                 ("High", "CPI Núcleo (M/M)"),
        "core inflation rate yoy":                 ("High", "CPI Núcleo (A/A)"),
        "adp employment change weekly":            ("High", "Emprego Privado ADP (Semanal)"),
        "initial jobless claims":                   ("High", "Pedidos Seguro-Desemprego"),
        "continuing jobless claims":                ("High", "Pedidos Contínuos Desemprego"),
        "jobless claims 4-week average":            ("High", "Pedidos Seguro-Desemprego (Média 4 Semanas)"),
        "durable goods orders mom":                  ("High", "Pedidos Bens Duráveis (M/M)"),
        "durable goods orders ex defense mom":       ("High", "Pedidos Bens Duráveis Ex-Defesa (M/M)"),
        "durable goods orders ex transp mom":        ("High", "Pedidos Bens Duráveis Ex-Transporte (M/M)"),
        "new home sales":                            ("High", "Vendas Casas Novas"),
        "new home sales mom":                        ("High", "Vendas Casas Novas (M/M)"),
        "personal income mom":                       ("High", "Renda Pessoal (M/M)"),
        "personal spending mom":                     ("High", "Gastos Pessoais (M/M)"),
        "michigan consumer sentiment final":         ("High", "Sentimento U. Michigan (Final)"),
        "goods trade balance":                       ("High", "Balança Comercial de Bens"),
        "goods trade balance adv":                   ("High", "Balança Comercial de Bens (Prévia)"),
        "core pce price index mom":                ("High", "PCE Núcleo (M/M)"),
        "core pce price index yoy":                ("High", "PCE Núcleo (A/A)"),
        "gdp growth rate qoq adv":                 ("High", "PIB (T/T, prévia)"),
        "fed interest rate decision":               ("High", "Decisão de Juros do Fed"),
        "fed press conference":                    ("High", "Coletiva do Fed"),
        "fomc meeting minutes":                    ("High", "Ata do FOMC"),
        "fomc statement":                          ("High", "Comunicado do FOMC"),
        "ism manufacturing pmi":                   ("High", "PMI Industrial ISM"),
        "ism services pmi":                        ("High", "PMI Serviços ISM"),
        "retail sales mom":                        ("High", "Vendas no Varejo (M/M)"),

        # ── Medium — emprego ────────────────────────────────────────────
        "government payrolls":                     ("Medium", "Empregos Governo"),
        "manufacturing payrolls":                  ("Medium", "Empregos Indústria"),
        "participation rate":                      ("Medium", "Taxa de Participação"),
        "u-6 unemployment rate":                    ("Medium", "Taxa de Desemprego U-6"),
        "average weekly hours":                    ("Medium", "Horas Semanais Médias"),
        "average hourly earnings mom":              ("Medium", "Remuneração Média/Hora (M/M)"),
        "average hourly earnings yoy":              ("Medium", "Remuneração Média/Hora (A/A)"),
        "challenger job cuts":                      ("Medium", "Cortes de Emprego (Challenger)"),
        "jolts job openings":                       ("Medium", "Vagas JOLTS"),
        "jolts job quits":                          ("Medium", "Demissões Voluntárias (JOLTS)"),
        "employment cost index qoq":                ("Medium", "Índice Custo de Emprego (T/T)"),
        "employment cost - wages qoq":               ("Medium", "Custo de Emprego — Salários (T/T)"),
        "employment cost - benefits qoq":            ("Medium", "Custo de Emprego — Benefícios (T/T)"),
        "nonfarm productivity qoq prel":             ("Medium", "Produtividade Não-Agrícola (T/T, prévia)"),
        "unit labour costs qoq prel":                ("Medium", "Custo Unitário do Trabalho (T/T, prévia)"),

        # ── Medium — preços/inflação ────────────────────────────────────
        "ppi mom":                                  ("Medium", "PPI (M/M)"),
        "ppi yoy":                                  ("Medium", "PPI (A/A)"),
        "core ppi mom":                              ("Medium", "PPI Núcleo (M/M)"),
        "core ppi yoy":                              ("Medium", "PPI Núcleo (A/A)"),
        "ppi ex food, energy and trade mom":         ("Medium", "PPI Núcleo Ex-Alim./Energia/Comércio (M/M)"),
        "ppi ex food, energy and trade yoy":         ("Medium", "PPI Núcleo Ex-Alim./Energia/Comércio (A/A)"),
        "core pce prices qoq adv":                   ("Medium", "PCE Núcleo (T/T, prévia)"),
        "pce prices qoq adv":                        ("Medium", "PCE (T/T, prévia)"),
        "consumer inflation expectations":           ("Medium", "Expectativa de Inflação do Consumidor"),
        "used car prices mom":                       ("Medium", "Preços Carros Usados (M/M, Manheim)"),
        "used car prices yoy":                       ("Medium", "Preços Carros Usados (A/A, Manheim)"),

        # ── Medium — atividade/PIB ──────────────────────────────────────
        "pce price index mom":                       ("Medium", "PCE (M/M)"),
        "pce price index yoy":                       ("Medium", "PCE (A/A)"),
        "gdp price index qoq adv":                   ("Medium", "Deflator do PIB (T/T, prévia)"),
        "gdp sales qoq adv":                         ("Medium", "Vendas Finais do PIB (T/T, prévia)"),
        "real consumer spending qoq adv":            ("Medium", "Gastos Reais do Consumidor (T/T, prévia)"),
        "chicago fed national activity index":       ("Medium", "Índice de Atividade Nacional (Chicago Fed)"),
        "chicago pmi":                                ("Medium", "PMI Chicago"),
        "dallas fed manufacturing index":            ("Medium", "Índice Manufatura Dallas Fed"),
        "dallas fed services index":                 ("Medium", "Índice Serviços Dallas Fed"),
        "kansas fed composite index":                ("Medium", "Índice Composto Kansas Fed"),
        "kansas fed manufacturing index":            ("Medium", "Índice Manufatura Kansas Fed"),
        "richmond fed manufacturing index":          ("Medium", "Índice Manufatura Richmond Fed"),
        "nfib business optimism index":              ("Medium", "Índice de Otimismo Empresarial (NFIB)"),
        "rcm/tipp economic optimism index":          ("Medium", "Índice de Otimismo Econômico (RCM/TIPP)"),
        "cb leading index mom":                       ("Medium", "Índice Antecedente (Conference Board, M/M)"),
        "construction spending mom":                  ("Medium", "Gastos com Construção (M/M)"),
        "business inventories mom":                   ("Medium", "Estoques das Empresas (M/M)"),
        "wholesale inventories mom":                  ("Medium", "Estoques no Atacado (M/M)"),
        "wholesale inventories mom adv":              ("Medium", "Estoques no Atacado (M/M, prévia)"),
        "retail inventories ex autos mom":            ("Medium", "Estoques no Varejo Ex-Autos (M/M)"),
        "retail inventories ex autos mom adv":        ("Medium", "Estoques no Varejo Ex-Autos (M/M, prévia)"),

        # ── Medium — consumo/vendas ─────────────────────────────────────
        "retail sales control group mom":            ("Medium", "Vendas no Varejo — Grupo de Controle (M/M)"),
        "retail sales ex autos mom":                  ("Medium", "Vendas no Varejo Ex-Autos (M/M)"),
        "retail sales ex gas/autos mom":              ("Medium", "Vendas no Varejo Ex-Gasolina/Autos (M/M)"),
        "retail sales yoy":                           ("Medium", "Vendas no Varejo (A/A)"),
        "real personal spending mom":                 ("Medium", "Gastos Pessoais Reais (M/M)"),
        "consumer credit change":                     ("Medium", "Crédito ao Consumidor"),
        "money supply":                               ("Medium", "Oferta Monetária (M2)"),
        "total vehicle sales":                        ("Medium", "Vendas de Veículos"),
        "total household debt":                       ("Medium", "Dívida Total das Famílias"),
        "consumer confidence":                        ("Medium", "Confiança do Consumidor"),
        "cb consumer confidence":                     ("Medium", "Confiança do Consumidor (Conference Board)"),
        "michigan consumer sentiment prel":           ("Medium", "Sentimento U. Michigan (Prévia)"),
        "michigan consumer expectations prel":        ("Medium", "Expectativas U. Michigan (Prévia)"),
        "michigan consumer expectations final":       ("Medium", "Expectativas U. Michigan (Final)"),
        "michigan current conditions prel":           ("Medium", "Condições Atuais U. Michigan (Prévia)"),
        "michigan current conditions final":          ("Medium", "Condições Atuais U. Michigan (Final)"),
        "michigan inflation expectations prel":       ("Medium", "Expectativa Inflação U. Michigan (Prévia)"),
        "michigan inflation expectations final":      ("Medium", "Expectativa Inflação U. Michigan (Final)"),
        "michigan 5 year inflation expectations prel": ("Medium", "Expectativa Inflação 5 Anos U. Michigan (Prévia)"),
        "michigan 5 year inflation expectations final": ("Medium", "Expectativa Inflação 5 Anos U. Michigan (Final)"),

        # ── Medium — indústria/pedidos ───────────────────────────────────
        "non defense goods orders ex air":             ("Medium", "Pedidos Bens Não-Defesa Ex-Aeronaves (M/M)"),
        "factory orders mom":                          ("Medium", "Pedidos de Fábricas (M/M)"),
        "factory orders ex transportation":            ("Medium", "Pedidos de Fábricas Ex-Transporte (M/M)"),
        "ism manufacturing employment":                ("Medium", "ISM Industrial — Emprego"),
        "ism manufacturing new orders":                ("Medium", "ISM Industrial — Novos Pedidos"),
        "ism manufacturing prices":                    ("Medium", "ISM Industrial — Preços"),
        "ism services business activity":              ("Medium", "ISM Serviços — Atividade"),
        "ism services employment":                     ("Medium", "ISM Serviços — Emprego"),
        "ism services new orders":                      ("Medium", "ISM Serviços — Novos Pedidos"),
        "ism services prices":                          ("Medium", "ISM Serviços — Preços"),
        "s&p global composite pmi flash":              ("Medium", "PMI Composto S&P Global (Prévia)"),
        "s&p global manufacturing pmi flash":           ("Medium", "PMI Industrial S&P Global (Prévia)"),
        "s&p global services pmi flash":               ("Medium", "PMI Serviços S&P Global (Prévia)"),
        "s&p global composite pmi final":              ("Medium", "PMI Composto S&P Global"),
        "s&p global manufacturing pmi final":          ("Medium", "PMI Industrial S&P Global"),
        "s&p global services pmi final":               ("Medium", "PMI Serviços S&P Global"),
        "lmi logistics managers index":                ("Medium", "Índice de Gerentes de Logística (LMI)"),

        # ── Medium — habitação ───────────────────────────────────────────
        "building permits":                            ("Medium", "Licenças de Construção"),
        "building permits final":                      ("Medium", "Licenças de Construção"),
        "building permits mom final":                  ("Medium", "Licenças de Construção (M/M)"),
        "housing starts":                              ("Medium", "Início de Construções"),
        "existing home sales":                         ("Medium", "Vendas Casas Usadas"),
        "existing home sales mom":                     ("Medium", "Vendas Casas Usadas (M/M)"),
        "house price index":                           ("Medium", "Índice de Preços de Imóveis (FHFA)"),
        "house price index mom":                       ("Medium", "Índice de Preços de Imóveis (M/M, FHFA)"),
        "house price index yoy":                       ("Medium", "Índice de Preços de Imóveis (A/A, FHFA)"),
        "s&p/case-shiller home price mom":              ("Medium", "Preços Case-Shiller (M/M)"),
        "s&p/case-shiller home price yoy":              ("Medium", "Preços Case-Shiller (A/A)"),

        # ── Medium — externo/fiscal/energia/Fed ──────────────────────────
        "balance of trade":                            ("Medium", "Balança Comercial"),
        "monthly budget statement":                    ("Medium", "Resultado Orçamentário Mensal"),
        "treasury refunding announcement":             ("Medium", "Anúncio de Refinanciamento do Tesouro"),
        "treasury refunding financing estimates":      ("Medium", "Estimativas de Financiamento do Tesouro"),
        "fed balance sheet":                           ("Medium", "Balanço do Fed (H.4.1)"),
        "eia crude oil stocks change":                 ("Medium", "Estoques de Petróleo (EIA)"),
        "eia gasoline stocks change":                  ("Medium", "Estoques de Gasolina (EIA)"),
        "api crude oil stock change":                  ("Medium", "Estoques de Petróleo (API)"),
        "mba 30-year mortgage rate":                   ("Medium", "Taxa de Hipoteca 30 Anos (MBA)"),
    }

    # Discursos de dirigentes do Fed vêm no TE como "Fed <Nome> Speech" (um
    # nome por dirigente - Cook, Musalem, Barkin, Waller, etc.), impraticável
    # de listar um por um na whitelist (e sempre ficaria incompleto quando
    # trocasse o titular). Casado via regex em vez de entrada fixa - achado
    # em 03/ago/2026 comparando contra investing.com: 3 speeches sumidos na
    # mesma semana (Cook, Musalem, Barkin) por não estarem na whitelist.
    _FED_SPEECH_RE = re.compile(r"^Fed (.+?) (Speech|Testimony|Remarks)$", re.IGNORECASE)

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
                raw_name = ev_link.get_text(strip=True)
                whitelisted = whitelist.get(raw_name.lower())
                if not whitelisted and country == "United States":
                    fed_m = cls._FED_SPEECH_RE.match(raw_name)
                    if fed_m:
                        kind = {"speech": "Discurso", "testimony": "Depoimento", "remarks": "Declarações"}[fed_m.group(2).lower()]
                        whitelisted = ("Medium", f"{kind} do Fed — {fed_m.group(1)}")
                if not whitelisted:
                    continue
                impact, pt_name = whitelisted
                time_span = row.find("span", class_=re.compile(r"^event-"))
                time_txt = time_span.get_text(strip=True) if time_span else ""
                has_time = False
                try:
                    dt = datetime.strptime(f"{current_date} {time_txt}", "%Y-%m-%d %I:%M %p")
                    has_time = True
                except ValueError:
                    dt = datetime.strptime(current_date, "%Y-%m-%d")
                if has_time:
                    # dt e o clock-time cru em UTC (ver comentario no topo do
                    # arquivo) - converte pra Brasilia antes de expor.
                    dt = dt.replace(tzinfo=timezone.utc).astimezone(_BRT)
                else:
                    # Evento sem horario intradiario (ex: BCB Focus) - nao ha
                    # hora real pra converter; so marca o fuso pra manter a
                    # data como veio, sem deslocar de dia por causa do UTC.
                    dt = dt.replace(tzinfo=_BRT)
                actual = row.find("span", id="actual")
                previous = row.find("span", id="previous")
                # id="consensus" (survey) e id="forecast" (modelo próprio do TE)
                # são dois valores DISTINTOS no HTML deles; a maioria dos eventos
                # só tem "forecast" preenchido (consensus vem vazio), mas alguns
                # (ex: New Home Sales) têm os dois com números diferentes — nesse
                # caso o "Consenso" exibido no site deles é o de "consensus", não
                # o "forecast". Confirmado inspecionando o HTML real em 24/jul/2026.
                consensus_el = row.find(id="consensus")
                forecast_el = row.find(id="forecast")
                consensus_txt = consensus_el.get_text(strip=True) if consensus_el else ""
                if not consensus_txt:
                    consensus_txt = forecast_el.get_text(strip=True) if forecast_el else ""
                events.append({
                    "datetime": dt.isoformat(),
                    "date": dt.strftime("%a, %d %b %Y"),
                    "time": dt.strftime("%H:%M") if has_time else "",
                    "country": country,
                    "currency": currency,
                    "impact": impact,
                    "event": pt_name,
                    "actual": actual.get_text(strip=True) if actual else "",
                    "forecast": consensus_txt,
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
        # datetime.now() sem tzinfo comparava "hora local da maquina que
        # roda o servidor" contra os horarios dos eventos (que agora vem
        # com tzinfo de Brasilia) - usar now(timezone.utc), que e sempre
        # comparavel corretamente contra qualquer datetime com tzinfo,
        # independente do fuso da maquina.
        now = datetime.now(timezone.utc)
        floor = now - timedelta(days=1)  # mantém eventos recém-liberados
        # Ceiling ate o FIM do N-esimo dia (23:59:59 em Brasilia), nao
        # N*24h corridas a partir de agora - achado real em 27/jul/2026:
        # eventos tarde no ultimo dia da janela (ex: ISM Manufacturing PMI,
        # 14:00 UTC = 11:00 BRT) sumiam quando "agora" era mais cedo no dia
        # do que o horario do evento, mesmo o evento estando dentro dos "N
        # dias" que o usuario pediu (achado comparando contra o calendario
        # do myfxbook.com, que o usuario usa como referencia externa).
        ceiling_date = now.astimezone(_BRT).date() + timedelta(days=days)
        ceiling = datetime.combine(ceiling_date, dtime(23, 59, 59), tzinfo=_BRT)
        combined = cls._fetch_tradingeconomics_br() + cls._fetch_tradingeconomics_us()
        combined = [e for e in combined if floor <= datetime.fromisoformat(e["datetime"]) <= ceiling]
        combined.sort(key=lambda e: e["datetime"])
        return combined
