# Sistema de Rastreamento do Saldo Acumulado do Investidor Estrangeiro no IBOVESPA

## Visão Geral

Sistema end-to-end para coleta, armazenamento, exposição e visualização do fluxo acumulado do investidor estrangeiro no IBOVESPA, com indicador customizado no TradingView via Pine Script alimentado por dados em tempo real via webhook/API própria.

**Fonte primária de dados:** [DadosDeMercado — Fluxo](https://www.dadosdemercado.com.br/fluxo)

---

## Arquitetura Geral

```
┌──────────────────────────────────────────────────────────────────────┐
│                          SISTEMA FLUXO ESTRANGEIRO                   │
│                                                                      │
│  ┌─────────────┐    ┌─────────────┐    ┌──────────────────────────┐ │
│  │  Coletor    │───▶│  PostgreSQL │───▶│  API REST (FastAPI)      │ │
│  │  (Scraper/  │    │  TimescaleDB│    │  /api/v1/fluxo           │ │
│  │   Scheduler)│    │             │    │  /api/v1/fluxo/acumulado │ │
│  └─────────────┘    └─────────────┘    └──────────┬───────────────┘ │
│                                                    │                 │
│  ┌─────────────────────────────────────────────────▼──────────────┐ │
│  │           TradingView (Pine Script + Security())               │ │
│  │  Indicador: Fluxo Acumulado Investidor Estrangeiro IBOV        │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │           Frontend (Next.js) — Dashboard de Monitoramento       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

**Stack:**
- **Coletor:** Python + APScheduler
- **Banco de dados:** PostgreSQL 16 + TimescaleDB
- **Backend/API:** Python + FastAPI
- **Frontend:** Next.js 14 + TailwindCSS
- **Infra:** Docker + Docker Compose
- **Reverse Proxy:** Nginx
- **Cache:** Redis

---

## Roteiro Cronológico de Desenvolvimento

### FASE 1 — Infraestrutura Base e Banco de Dados
**Objetivo:** ambiente Docker funcional com banco de dados estruturado.

---

#### Etapa 1.1 — Estrutura de Pastas e Docker Compose Base

```
mktsentiment/
├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
├── .env
├── services/
│   ├── db/
│   │   └── init.sql
│   ├── collector/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py
│   ├── api/
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── main.py
│   ├── frontend/
│   │   ├── Dockerfile
│   │   └── ... (Next.js)
│   └── nginx/
│       └── nginx.conf
└── docs/
```

**`docker-compose.yml`**
```yaml
version: "3.9"

services:
  db:
    image: timescale/timescaledb:latest-pg16
    container_name: mkt_db
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pg_data:/var/lib/postgresql/data
      - ./services/db/init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"

  redis:
    image: redis:7-alpine
    container_name: mkt_redis
    restart: unless-stopped
    ports:
      - "6379:6379"

  collector:
    build: ./services/collector
    container_name: mkt_collector
    restart: unless-stopped
    depends_on:
      - db
      - redis
    env_file: .env
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
      - REDIS_URL=redis://redis:6379/0

  api:
    build: ./services/api
    container_name: mkt_api
    restart: unless-stopped
    depends_on:
      - db
      - redis
    env_file: .env
    environment:
      - DATABASE_URL=postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@db:5432/${POSTGRES_DB}
      - REDIS_URL=redis://redis:6379/0
    ports:
      - "8000:8000"

  frontend:
    build: ./services/frontend
    container_name: mkt_frontend
    restart: unless-stopped
    depends_on:
      - api
    ports:
      - "3000:3000"

  nginx:
    image: nginx:alpine
    container_name: mkt_nginx
    restart: unless-stopped
    depends_on:
      - api
      - frontend
    volumes:
      - ./services/nginx/nginx.conf:/etc/nginx/nginx.conf:ro
    ports:
      - "80:80"

volumes:
  pg_data:
```

**`.env.example`**
```env
POSTGRES_USER=mkt_user
POSTGRES_PASSWORD=changeme
POSTGRES_DB=mktsentiment

REDIS_URL=redis://redis:6379/0

# API externa — DadosDeMercado
DDM_BASE_URL=https://www.dadosdemercado.com.br
DDM_API_KEY=

# TradingView Webhook Secret (para validação futura)
TV_WEBHOOK_SECRET=changeme

# Coleta agendada (cron)
COLLECTOR_CRON=0 20 * * 1-5
```

**Teste da Etapa 1.1:**
```bash
docker compose up -d db redis
docker compose ps
# Verificar: db e redis em estado "running"
```

---

#### Etapa 1.2 — Schema do Banco de Dados

**`services/db/init.sql`**
```sql
-- Habilitar TimescaleDB
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Tabela principal: dados diários de fluxo de capitais
CREATE TABLE IF NOT EXISTS fluxo_estrangeiro (
    id              BIGSERIAL,
    data            DATE        NOT NULL,
    saldo_dia       NUMERIC(18, 2) NOT NULL,   -- fluxo líquido do dia (R$ milhões)
    compras         NUMERIC(18, 2),             -- volume comprado no dia
    vendas          NUMERIC(18, 2),             -- volume vendido no dia
    saldo_acumulado NUMERIC(18, 2),             -- saldo acumulado desde início da série
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now(),
    fonte           TEXT DEFAULT 'dadosdemercado',
    PRIMARY KEY (id, data)
);

-- Converter em hypertable para séries temporais eficientes
SELECT create_hypertable('fluxo_estrangeiro', 'data',
    if_not_exists => TRUE,
    chunk_time_interval => INTERVAL '3 months');

-- Índice único por data (evitar duplicatas na coleta)
CREATE UNIQUE INDEX IF NOT EXISTS idx_fluxo_data
    ON fluxo_estrangeiro (data);

-- Tabela de controle de coleta
CREATE TABLE IF NOT EXISTS coleta_log (
    id          BIGSERIAL PRIMARY KEY,
    iniciado_em TIMESTAMPTZ DEFAULT now(),
    finalizado_em TIMESTAMPTZ,
    status      TEXT CHECK (status IN ('running', 'success', 'error')),
    registros   INT DEFAULT 0,
    erro        TEXT,
    fonte       TEXT DEFAULT 'dadosdemercado'
);

-- View materializada: saldo acumulado YTD (recalculado diariamente)
CREATE MATERIALIZED VIEW IF NOT EXISTS fluxo_acumulado_ytd AS
SELECT
    data,
    saldo_dia,
    saldo_acumulado,
    SUM(saldo_dia) OVER (
        PARTITION BY EXTRACT(YEAR FROM data)
        ORDER BY data
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS acumulado_ano
FROM fluxo_estrangeiro
ORDER BY data;

CREATE UNIQUE INDEX IF NOT EXISTS idx_fluxo_acumulado_ytd_data
    ON fluxo_acumulado_ytd (data);
```

**Teste da Etapa 1.2:**
```bash
docker compose up -d db
docker exec -it mkt_db psql -U mkt_user -d mktsentiment -c "\dt"
# Verificar: tabelas fluxo_estrangeiro e coleta_log criadas
docker exec -it mkt_db psql -U mkt_user -d mktsentiment -c "\d fluxo_estrangeiro"
```

---

### FASE 2 — Serviço Coletor (Data Ingestion)
**Objetivo:** coletar dados da API DadosDeMercado e persistir no banco.

---

#### Etapa 2.1 — Análise e Mapeamento da API DadosDeMercado

A página `https://www.dadosdemercado.com.br/fluxo` expõe dados de fluxo de capitais. O coletor deve:

1. Fazer requisição HTTP à fonte
2. Parsear os dados de fluxo do investidor estrangeiro (tabela B3)
3. Calcular/verificar o saldo acumulado
4. Persistir novos registros sem duplicar

**Estratégia de coleta:**
- Coleta diária agendada via cron (após fechamento do mercado: 20h BRT)
- Coleta histórica (backfill) na primeira execução
- Idempotente: registros existentes são atualizados via `ON CONFLICT DO UPDATE`

---

#### Etapa 2.2 — Serviço Coletor Python

**`services/collector/requirements.txt`**
```
httpx==0.27.0
beautifulsoup4==4.12.3
lxml==5.2.2
psycopg2-binary==2.9.9
sqlalchemy==2.0.30
apscheduler==3.10.4
redis==5.0.4
python-dotenv==1.0.1
tenacity==8.3.0
```

**`services/collector/main.py`**
```python
import os
import logging
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, text
from apscheduler.schedulers.blocking import BlockingScheduler
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ["DATABASE_URL"]
DDM_URL = "https://www.dadosdemercado.com.br/fluxo"
engine = create_engine(DATABASE_URL, pool_pre_ping=True)


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=4, max=30))
def fetch_fluxo_page() -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    }
    with httpx.Client(timeout=30, follow_redirects=True) as client:
        response = client.get(DDM_URL, headers=headers)
        response.raise_for_status()
        return response.text


def parse_fluxo(html: str) -> list[dict]:
    """
    Extrai dados de fluxo do investidor estrangeiro da tabela HTML.
    Retorna lista de dicts: {data, saldo_dia, compras, vendas, saldo_acumulado}
    """
    soup = BeautifulSoup(html, "lxml")
    rows = []

    # Localizar tabela de estrangeiros — adaptar seletor conforme estrutura real da página
    tables = soup.find_all("table")
    target_table = None
    for table in tables:
        header_text = table.get_text().lower()
        if "estrangeiro" in header_text or "externo" in header_text:
            target_table = table
            break

    if not target_table:
        logger.warning("Tabela de fluxo estrangeiro não encontrada no HTML")
        return rows

    for tr in target_table.find_all("tr")[1:]:  # pular header
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cols) < 3:
            continue
        try:
            def parse_br_number(s: str) -> Optional[Decimal]:
                if not s or s in ("-", "—", ""):
                    return None
                cleaned = s.replace(".", "").replace(",", ".").replace("R$", "").replace(" ", "")
                return Decimal(cleaned)

            data_str = cols[0]
            data_parsed = datetime.strptime(data_str, "%d/%m/%Y").date()

            rows.append({
                "data": data_parsed,
                "saldo_dia": parse_br_number(cols[1]),
                "compras": parse_br_number(cols[2]) if len(cols) > 2 else None,
                "vendas": parse_br_number(cols[3]) if len(cols) > 3 else None,
                "saldo_acumulado": parse_br_number(cols[4]) if len(cols) > 4 else None,
            })
        except (ValueError, IndexError) as e:
            logger.debug(f"Linha ignorada: {cols} — {e}")

    return rows


def calcular_saldo_acumulado(rows: list[dict]) -> list[dict]:
    """Recalcula saldo acumulado caso não venha da fonte."""
    acumulado = Decimal(0)
    for row in sorted(rows, key=lambda r: r["data"]):
        if row["saldo_dia"] is not None:
            acumulado += row["saldo_dia"]
        if row.get("saldo_acumulado") is None:
            row["saldo_acumulado"] = acumulado
    return rows


def upsert_rows(rows: list[dict]) -> int:
    if not rows:
        return 0
    with engine.begin() as conn:
        count = 0
        for row in rows:
            conn.execute(text("""
                INSERT INTO fluxo_estrangeiro
                    (data, saldo_dia, compras, vendas, saldo_acumulado)
                VALUES
                    (:data, :saldo_dia, :compras, :vendas, :saldo_acumulado)
                ON CONFLICT (data) DO UPDATE SET
                    saldo_dia       = EXCLUDED.saldo_dia,
                    compras         = EXCLUDED.compras,
                    vendas          = EXCLUDED.vendas,
                    saldo_acumulado = EXCLUDED.saldo_acumulado,
                    updated_at      = now()
            """), row)
            count += 1

        # Atualizar view materializada
        conn.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY fluxo_acumulado_ytd"))
    return count


def log_coleta(status: str, registros: int = 0, erro: str = None):
    with engine.begin() as conn:
        conn.execute(text("""
            INSERT INTO coleta_log (status, registros, erro, finalizado_em)
            VALUES (:status, :registros, :erro, now())
        """), {"status": status, "registros": registros, "erro": erro})


def coletar():
    logger.info("Iniciando coleta de fluxo estrangeiro...")
    try:
        html = fetch_fluxo_page()
        rows = parse_fluxo(html)

        if not rows:
            logger.warning("Nenhum dado extraído da página")
            log_coleta("error", erro="Nenhum dado extraído")
            return

        rows = calcular_saldo_acumulado(rows)
        count = upsert_rows(rows)
        logger.info(f"Coleta concluída: {count} registros persistidos")
        log_coleta("success", registros=count)

    except Exception as e:
        logger.error(f"Erro na coleta: {e}", exc_info=True)
        log_coleta("error", erro=str(e))


if __name__ == "__main__":
    # Backfill na inicialização
    coletar()

    scheduler = BlockingScheduler(timezone="America/Sao_Paulo")
    # Coleta diária às 20h em dias úteis
    scheduler.add_job(coletar, "cron", day_of_week="mon-fri", hour=20, minute=0)
    logger.info("Scheduler iniciado — coleta diária 20h BRT (seg-sex)")
    scheduler.start()
```

**`services/collector/Dockerfile`**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]
```

**Teste da Etapa 2.2:**
```bash
docker compose up -d db redis
docker compose up --build collector
# Verificar logs: "Coleta concluída: N registros persistidos"

# Checar banco
docker exec -it mkt_db psql -U mkt_user -d mktsentiment \
  -c "SELECT data, saldo_dia, saldo_acumulado FROM fluxo_estrangeiro ORDER BY data DESC LIMIT 10;"
```

---

### FASE 3 — API REST (Backend)
**Objetivo:** expor os dados do banco via API RESTful consumível pelo TradingView e pelo frontend.

---

#### Etapa 3.1 — API FastAPI

**`services/api/requirements.txt`**
```
fastapi==0.111.0
uvicorn[standard]==0.30.1
psycopg2-binary==2.9.9
sqlalchemy==2.0.30
redis==5.0.4
python-dotenv==1.0.1
pydantic==2.7.1
```

**`services/api/main.py`**
```python
import os
import json
from datetime import date, timedelta
from typing import Optional
from decimal import Decimal

import redis
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, text
from pydantic import BaseModel

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
CACHE_TTL = 3600  # 1 hora

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
cache = redis.from_url(REDIS_URL, decode_responses=True)

app = FastAPI(
    title="MktSentiment — Fluxo Estrangeiro IBOV",
    version="1.0.0",
    description="API de fluxo acumulado do investidor estrangeiro no IBOVESPA",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class FluxoRow(BaseModel):
    time: str          # formato ISO date — obrigatório pelo TradingView
    value: float       # saldo acumulado em R$ milhões


class FluxoDiaRow(BaseModel):
    time: str
    saldo_dia: Optional[float]
    compras: Optional[float]
    vendas: Optional[float]
    saldo_acumulado: Optional[float]


def cache_key(endpoint: str, **kwargs) -> str:
    parts = "&".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
    return f"mkt:{endpoint}:{parts}"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/v1/fluxo/acumulado", response_model=list[FluxoRow])
def get_fluxo_acumulado(
    desde: Optional[date] = Query(None, description="Data inicial (YYYY-MM-DD)"),
    ate: Optional[date] = Query(None, description="Data final (YYYY-MM-DD)"),
    periodo: Optional[str] = Query("ytd", description="Atalho: 1m, 3m, 6m, 1a, 2a, ytd, max"),
):
    """
    Retorna o saldo acumulado do investidor estrangeiro.
    Formato compatível com o input de séries externas do TradingView (request()).
    """
    key = cache_key("acumulado", desde=desde, ate=ate, periodo=periodo)
    cached = cache.get(key)
    if cached:
        return json.loads(cached)

    hoje = date.today()
    if not desde:
        match periodo:
            case "1m":  desde = hoje - timedelta(days=30)
            case "3m":  desde = hoje - timedelta(days=90)
            case "6m":  desde = hoje - timedelta(days=180)
            case "1a":  desde = hoje - timedelta(days=365)
            case "2a":  desde = hoje - timedelta(days=730)
            case "ytd": desde = date(hoje.year, 1, 1)
            case _:     desde = date(2010, 1, 1)   # max

    if not ate:
        ate = hoje

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT data, saldo_acumulado
            FROM fluxo_estrangeiro
            WHERE data BETWEEN :desde AND :ate
              AND saldo_acumulado IS NOT NULL
            ORDER BY data ASC
        """), {"desde": desde, "ate": ate}).fetchall()

    result = [
        FluxoRow(time=str(r.data), value=float(r.saldo_acumulado))
        for r in rows
    ]

    cache.setex(key, CACHE_TTL, json.dumps([r.dict() for r in result]))
    return result


@app.get("/api/v1/fluxo/diario", response_model=list[FluxoDiaRow])
def get_fluxo_diario(
    desde: Optional[date] = Query(None),
    ate: Optional[date] = Query(None),
    periodo: Optional[str] = Query("ytd"),
):
    """Retorna fluxo diário bruto (compras, vendas, saldo do dia)."""
    hoje = date.today()
    if not desde:
        match periodo:
            case "1m":  desde = hoje - timedelta(days=30)
            case "3m":  desde = hoje - timedelta(days=90)
            case "ytd": desde = date(hoje.year, 1, 1)
            case _:     desde = date(2010, 1, 1)
    if not ate:
        ate = hoje

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT data, saldo_dia, compras, vendas, saldo_acumulado
            FROM fluxo_estrangeiro
            WHERE data BETWEEN :desde AND :ate
            ORDER BY data ASC
        """), {"desde": desde, "ate": ate}).fetchall()

    return [
        FluxoDiaRow(
            time=str(r.data),
            saldo_dia=float(r.saldo_dia) if r.saldo_dia else None,
            compras=float(r.compras) if r.compras else None,
            vendas=float(r.vendas) if r.vendas else None,
            saldo_acumulado=float(r.saldo_acumulado) if r.saldo_acumulado else None,
        )
        for r in rows
    ]


@app.get("/api/v1/fluxo/ultimo")
def get_ultimo():
    """Retorna o registro mais recente — útil para widgets de dashboard."""
    with engine.connect() as conn:
        row = conn.execute(text("""
            SELECT data, saldo_dia, saldo_acumulado
            FROM fluxo_estrangeiro
            ORDER BY data DESC
            LIMIT 1
        """)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Nenhum dado disponível")
    return {
        "data": str(row.data),
        "saldo_dia": float(row.saldo_dia) if row.saldo_dia else None,
        "saldo_acumulado": float(row.saldo_acumulado) if row.saldo_acumulado else None,
    }
```

**`services/api/Dockerfile`**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Teste da Etapa 3.1:**
```bash
docker compose up -d db redis collector api
# Aguardar collector fazer backfill (~30s)
curl http://localhost:8000/health
curl "http://localhost:8000/api/v1/fluxo/acumulado?periodo=ytd"
curl "http://localhost:8000/api/v1/fluxo/ultimo"
# Verificar: respostas JSON com dados de saldo acumulado
open http://localhost:8000/docs  # Swagger UI
```

---

### FASE 4 — Nginx (Reverse Proxy)
**Objetivo:** roteamento unificado na porta 80 para API e frontend.

**`services/nginx/nginx.conf`**
```nginx
events { worker_connections 1024; }

http {
    upstream api {
        server api:8000;
    }
    upstream frontend {
        server frontend:3000;
    }

    server {
        listen 80;

        location /api/ {
            proxy_pass http://api;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }

        location /health {
            proxy_pass http://api;
        }

        location / {
            proxy_pass http://frontend;
            proxy_set_header Host $host;
        }
    }
}
```

**Teste da Etapa 4:**
```bash
docker compose up -d nginx
curl http://localhost/api/v1/fluxo/ultimo
curl http://localhost/health
```

---

### FASE 5 — Indicador TradingView (Pine Script)
**Objetivo:** indicador de saldo acumulado do investidor estrangeiro no IBOVESPA, com visual idêntico ao painel de referência.

---

#### Etapa 5.1 — Publicar API com URL pública

Para o TradingView consumir a API, ela precisa ser acessível publicamente via HTTPS.

**Opções:**
- **Desenvolvimento/teste:** usar [ngrok](https://ngrok.com) para expor `localhost:80`
  ```bash
  ngrok http 80
  # Copiar URL gerada: https://xxxx.ngrok-free.app
  ```
- **Produção:** deploy em VPS (DigitalOcean, AWS EC2, etc.) com domínio próprio + certificado SSL (Let's Encrypt via Certbot ou Traefik)

---

#### Etapa 5.2 — Pine Script v5

Cole o script abaixo no Pine Script Editor do TradingView (Novo Indicador):

```pine
//@version=5
indicator(
    title        = "Fluxo Acumulado Estrangeiro — IBOV",
    shorttitle   = "FluxoExt",
    overlay      = false,
    scale        = scale.right,
    max_bars_back = 500
)

// ─────────────────────────────────────────────
// Inputs
// ─────────────────────────────────────────────
apiUrl    = input.string("https://SEU-DOMINIO/api/v1/fluxo/acumulado?periodo=max",
             title = "URL da API de Saldo Acumulado")

colorBull = input.color(color.new(#26a69a, 0),  title = "Cor Alta (saldo positivo)")
colorBear = input.color(color.new(#ef5350, 0),  title = "Cor Baixa (saldo negativo)")
colorLine = input.color(color.new(#ffffff, 0),  title = "Cor da Linha Principal")
showBars  = input.bool(true,  title = "Mostrar Histograma de Fluxo Diário")
showZero  = input.bool(true,  title = "Mostrar Linha Zero")
lineWidth = input.int(2,      title = "Espessura da Linha", minval=1, maxval=5)

// ─────────────────────────────────────────────
// Busca de dados externos via request.security_lower_tf() 
// ou, para URL externa, via request.security() com símbolo vazio.
// O TradingView não permite request() para URLs arbitrárias diretamente;
// a abordagem recomendada é usar um "UDF" (User-Defined Feed) configurado
// no TradingView via conta Premium/Enterprise, OU utilizar a integração
// via símbolo customizado importado como CSV.
//
// Abordagem prática (funciona em todas as contas):
// Exportar os dados da API como CSV e importar no TradingView como
// "Símbolo Customizado" (Custom Symbol / Spreadsheet), depois referenciar
// com request.security().
// ─────────────────────────────────────────────

// Símbolo importado manualmente como custom data no TradingView
// (ex: "SPREADSHEET:FLUXO_EST_IBOV")
customSymbol = input.symbol("SPREADSHEET:FLUXO_EST_IBOV",
                title = "Símbolo do Dado Importado")

// Busca do saldo acumulado (close do símbolo customizado = saldo acumulado)
[saldoAcum, saldoDia] = request.security(
    symbol   = customSymbol,
    timeframe= "D",
    expression = [close, open - close]  // close = acumulado, (open-close) = fluxo dia
)

// ─────────────────────────────────────────────
// Lógica do indicador
// ─────────────────────────────────────────────
varip float acumulado = na
acumulado := not na(saldoAcum) ? saldoAcum : acumulado

corHistograma = saldoDia >= 0 ? colorBull : colorBear

// ─────────────────────────────────────────────
// Plots
// ─────────────────────────────────────────────

// Histograma de fluxo diário (barras coloridas — similar ao indicador de referência)
plot(
    showBars ? saldoDia : na,
    style    = plot.style_histogram,
    color    = corHistograma,
    linewidth= 4,
    title    = "Fluxo Diário"
)

// Linha do saldo acumulado
plot(
    acumulado,
    style    = plot.style_line,
    color    = colorLine,
    linewidth= lineWidth,
    title    = "Saldo Acumulado"
)

// Linha zero de referência
hline(
    price     = 0,
    color     = showZero ? color.new(color.gray, 50) : color.new(color.gray, 100),
    linestyle = hline.style_dashed,
    linewidth = 1
)

// ─────────────────────────────────────────────
// Tabela informativa (canto superior direito — igual ao modelo de referência)
// ─────────────────────────────────────────────
var table tbl = table.new(
    position   = position.top_right,
    columns    = 2,
    rows       = 4,
    bgcolor    = color.new(color.black, 70),
    border_color = color.new(color.gray, 60),
    border_width = 1
)

if barstate.islast
    ultimoValor  = not na(acumulado) ? str.tostring(acumulado / 1000, "#,##0.0") + " bi" : "—"
    fluxoHoje    = not na(saldoDia)  ? str.tostring(saldoDia  / 1000, "#,##0.0") + " bi" : "—"
    corAcum      = acumulado >= 0    ? colorBull : colorBear
    corDia       = saldoDia  >= 0    ? colorBull : colorBear

    table.cell(tbl, 0, 0, "Fluxo Estrangeiro IBOV", text_color=color.white,   text_size=size.small, bgcolor=color.new(color.black, 60))
    table.cell(tbl, 1, 0, "",                        text_color=color.white,   text_size=size.small, bgcolor=color.new(color.black, 60))
    table.cell(tbl, 0, 1, "Acumulado",               text_color=color.gray,    text_size=size.tiny)
    table.cell(tbl, 1, 1, ultimoValor,               text_color=corAcum,       text_size=size.small)
    table.cell(tbl, 0, 2, "Hoje",                    text_color=color.gray,    text_size=size.tiny)
    table.cell(tbl, 1, 2, fluxoHoje,                 text_color=corDia,        text_size=size.small)
    table.cell(tbl, 0, 3, "Fonte: DadosDeMercado",   text_color=color.new(color.gray, 40), text_size=size.tiny)
    table.cell(tbl, 1, 3, str.tostring(timenow, "yyyy-MM-dd"), text_color=color.new(color.gray, 40), text_size=size.tiny)

// Background colorido por zona (positivo = verde translúcido, negativo = vermelho)
bgcolor(
    acumulado > 0 ? color.new(colorBull, 92) :
    acumulado < 0 ? color.new(colorBear, 92) : na,
    title = "Background de zona"
)
```

---

#### Etapa 5.3 — Fluxo de Integração dos Dados

Como o TradingView não aceita URLs arbitrárias via `request()` em contas padrão, o fluxo de dados funciona assim:

```
API REST (/api/v1/fluxo/acumulado)
        │
        ▼  exportar como CSV
┌───────────────────────────────┐
│  CSV gerado diariamente       │
│  date,open,high,low,close,vol │
│  (close = saldo_acumulado)    │
│  (open-close = saldo_dia)     │
└───────────────────────────────┘
        │
        ▼  importar no TradingView
┌───────────────────────────────────────────────────┐
│  TradingView → Novo Símbolo → Importar planilha   │
│  Símbolo criado: "SPREADSHEET:FLUXO_EST_IBOV"     │
└───────────────────────────────────────────────────┘
        │
        ▼  request.security() no Pine Script
┌─────────────────────┐
│  Indicador plotado  │
└─────────────────────┘
```

**Endpoint de exportação CSV — adicionar à API:**
```python
# Em services/api/main.py
from fastapi.responses import StreamingResponse
import csv, io

@app.get("/api/v1/fluxo/export.csv")
def export_csv(desde: Optional[date] = Query(None)):
    desde = desde or date(2010, 1, 1)
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT data, saldo_acumulado, saldo_dia
            FROM fluxo_estrangeiro
            WHERE data >= :desde AND saldo_acumulado IS NOT NULL
            ORDER BY data ASC
        """), {"desde": desde}).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["date", "open", "high", "low", "close", "volume"])
    for r in rows:
        acum = float(r.saldo_acumulado)
        dia  = float(r.saldo_dia) if r.saldo_dia else 0.0
        writer.writerow([str(r.data), acum + dia, acum, acum, acum, abs(dia)])
    output.seek(0)

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fluxo_estrangeiro.csv"},
    )
```

**Teste da Etapa 5:**
```bash
curl "http://localhost/api/v1/fluxo/export.csv" -o fluxo_estrangeiro.csv
# Abrir arquivo e verificar colunas: date, open, high, low, close, volume
# Importar no TradingView e validar indicador
```

---

### FASE 6 — Frontend (Dashboard de Monitoramento)
**Objetivo:** dashboard web para visualização do fluxo e status do sistema.

---

#### Etapa 6.1 — Setup Next.js

```bash
cd services/frontend
npx create-next-app@14 . --typescript --tailwind --app --no-src-dir
npm install recharts date-fns @radix-ui/react-tabs
```

**`services/frontend/Dockerfile`**
```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

---

#### Etapa 6.2 — Página Principal

**`app/page.tsx`** (estrutura simplificada):
```tsx
// Página com três painéis:
// 1. Card de saldo acumulado atual + variação do dia
// 2. Gráfico de linha histórico (recharts) — saldo acumulado
// 3. Gráfico de barras — fluxo diário (verde/vermelho)
// 4. Status da última coleta

export default async function Home() {
  const baseUrl = process.env.API_BASE_URL ?? "http://api:8000"

  const [ultimo, acumulado] = await Promise.all([
    fetch(`${baseUrl}/api/v1/fluxo/ultimo`).then(r => r.json()),
    fetch(`${baseUrl}/api/v1/fluxo/acumulado?periodo=ytd`).then(r => r.json()),
  ])

  return (
    <main className="min-h-screen bg-gray-950 text-white p-6">
      <h1 className="text-2xl font-bold mb-6">
        Fluxo Estrangeiro — IBOVESPA
      </h1>
      {/* Cards, gráficos e tabela aqui */}
    </main>
  )
}
```

**Teste da Etapa 6:**
```bash
docker compose up --build frontend
open http://localhost:3000
# Verificar: dashboard carrega com dados de fluxo acumulado
```

---

### FASE 7 — Produção e Deploy
**Objetivo:** ambiente de produção seguro e resiliente.

---

#### Etapa 7.1 — Docker Compose para Produção

**`docker-compose.prod.yml`**
```yaml
version: "3.9"

services:
  db:
    image: timescale/timescaledb:latest-pg16
    restart: always
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - pg_data:/var/lib/postgresql/data
    networks:
      - internal

  redis:
    image: redis:7-alpine
    restart: always
    networks:
      - internal

  collector:
    build: ./services/collector
    restart: always
    depends_on: [db, redis]
    env_file: .env.prod
    networks:
      - internal

  api:
    build: ./services/api
    restart: always
    depends_on: [db, redis]
    env_file: .env.prod
    networks:
      - internal
      - web

  frontend:
    build: ./services/frontend
    restart: always
    depends_on: [api]
    environment:
      - API_BASE_URL=http://api:8000
    networks:
      - internal
      - web

  nginx:
    image: nginx:alpine
    restart: always
    volumes:
      - ./services/nginx/nginx.prod.conf:/etc/nginx/nginx.conf:ro
      - certbot_www:/var/www/certbot
      - certbot_conf:/etc/letsencrypt
    ports:
      - "80:80"
      - "443:443"
    networks:
      - web

  certbot:
    image: certbot/certbot
    volumes:
      - certbot_www:/var/www/certbot
      - certbot_conf:/etc/letsencrypt

volumes:
  pg_data:
  certbot_www:
  certbot_conf:

networks:
  internal:
  web:
```

---

#### Etapa 7.2 — SSL com Let's Encrypt

```bash
# Primeiro: apontar DNS do domínio para o IP do servidor

# Obter certificado
docker compose -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot -w /var/www/certbot \
  -d seudominio.com --email seu@email.com --agree-tos

# Renovação automática (cron no host)
echo "0 3 * * * docker compose -f /caminho/docker-compose.prod.yml run --rm certbot renew" | crontab -
```

---

#### Etapa 7.3 — Monitoramento de Saúde

Adicionar ao `docker-compose.yml`:
```yaml
  healthcheck_db:
    image: postgres:16
    command: >
      sh -c "pg_isready -h db -U $$POSTGRES_USER -d $$POSTGRES_DB"
    depends_on: [db]
    interval: 30s
    timeout: 10s
    retries: 5
```

**Endpoint de status geral:**
```bash
curl http://localhost/health
curl "http://localhost/api/v1/fluxo/ultimo"
```

---

## Checklist de Validação por Fase

| Fase | Critério de Aceite |
|------|--------------------|
| 1.1  | `docker compose up -d db redis` — ambos `running` |
| 1.2  | Tabelas `fluxo_estrangeiro` e `coleta_log` criadas no banco |
| 2.2  | Coletor persiste dados históricos; `SELECT COUNT(*) FROM fluxo_estrangeiro` > 0 |
| 3.1  | `GET /api/v1/fluxo/acumulado?periodo=ytd` retorna array JSON com `time` e `value` |
| 4    | `curl http://localhost/api/v1/fluxo/ultimo` responde corretamente via Nginx |
| 5    | CSV exportado importado no TradingView; indicador plotado sem erros |
| 6    | Dashboard web exibe gráfico e valores atualizados |
| 7    | Deploy em produção com HTTPS funcional; coletor agenda coleta diária |

---

## Dependências e Versões Fixas

| Componente | Versão |
|------------|--------|
| Python | 3.12 |
| FastAPI | 0.111.0 |
| PostgreSQL | 16 |
| TimescaleDB | latest-pg16 |
| Redis | 7 |
| Node.js | 20 LTS |
| Next.js | 14 |
| Nginx | Alpine (latest) |
| Pine Script | v5 |

---

## Notas de Implementação

1. **Parser HTML:** O seletor CSS do coletor deve ser ajustado após inspeção real do HTML da página `dadosdemercado.com.br/fluxo`. Use `curl https://www.dadosdemercado.com.br/fluxo | grep -i "estrangeiro"` para verificar a estrutura antes da primeira execução.

2. **Rate limiting:** A fonte pública não requer autenticação, mas respeite o intervalo de coleta (1x/dia). Não faça scraping agressivo.

3. **Fallback de dados:** Caso a coleta falhe, o último dado persistido é retornado normalmente pela API — o indicador no TradingView não quebrará.

4. **TradingView UDF:** Para integração mais robusta (sem importação manual de CSV), é necessário conta TradingView Premium com acesso a UDF (User-Defined Data Feed). Com isso, o Pine Script pode consumir a API REST diretamente via `request.security("ACME:TICKER", ...)` configurado no broker UDF.

5. **Saldo acumulado:** A série do saldo acumulado é calculada somando `saldo_dia` progressivamente desde o início da série. Se a fonte já fornece o acumulado, ele é usado diretamente; caso contrário, é recalculado na função `calcular_saldo_acumulado()`.
