# Sistema de Dashboard Intermarket — IBOVESPA · 6L COT · NTNB 2035 · Fluxo Estrangeiro

## Visão Geral

Sistema de compilação e visualização de quatro séries temporais correlacionadas para análise macroeconômica e intermarket do mercado brasileiro. O objetivo é sobrepor as curvas em um único dashboard interativo (HTML), permitindo ativar/desativar cada série individualmente.

### Séries monitoradas

| ID | Série | Fonte primária | Unidade |
|----|-------|----------------|---------|
| `ibov` | IBOVESPA (linha diária) | Yahoo Finance (`^BVSP`) / B3 | Pontos |
| `cot_6l` | 6L Brazilian Real — Asset Manager Net Positions (COT) | CFTC / Tradingster / Barchart | Contratos (net) |
| `ntnb35_pu` | Preço Unitário NTN-B 2035 | Tesouro Direto (séries históricas) / MaisRetorno | R$ |
| `foreign_flow` | Saldo acumulado do investidor estrangeiro (ano) | dadosdemercado.com.br/fluxo | R$ milhões |

---

## Referências Visuais

Os indicadores devem ser criados nos seguintes moldes:

- **6L COT (Asset Manager)** → `NetPositions.tradinsgeter.png` — linha azul step-chart, fundo verde-claro, eixo Y à esquerda, navegador de período na parte inferior.
- **NTN-B 2035 PU** → `mAISrETORNO.png` — linha vermelha sobreposta ao IBOVESPA verde, eixo % à esquerda, janela 3A.
- **IBOVESPA** → `ibovlinha.png` — linha dourada D1, sem fundo colorido, eixo de preço à direita.
- **Overlay final** → `model.example.png` — quatro séries normalizadas no mesmo canvas, legenda flutuante, toggle por série.

---

## Arquitetura do Sistema

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FRONTEND (HTML/JS)                           │
│   Dashboard SPA  ·  Highcharts / Chart.js  ·  Toggle de séries     │
└───────────────────────────┬─────────────────────────────────────────┘
                            │ REST / WebSocket
┌───────────────────────────▼─────────────────────────────────────────┐
│                        BACKEND (FastAPI)                             │
│  /api/ibov  ·  /api/cot  ·  /api/ntnb35  ·  /api/foreign-flow      │
└───────┬──────────────┬────────────────┬──────────────────┬──────────┘
        │              │                │                  │
   Yahoo /       CFTC / Barchart   Tesouro Direto    dadosdemercado
   B3 API          (scraper)        API pública       .com.br/fluxo
        │              │                │                  │
┌───────▼──────────────▼────────────────▼──────────────────▼──────────┐
│                    Scheduler (APScheduler / Celery)                  │
│       Coleta automática diária · fallback em múltiplas fontes       │
└───────────────────────────┬─────────────────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────────────────┐
│                     Banco de Dados (PostgreSQL)                      │
│  Tabelas: ibov_daily · cot_6l · ntnb35_pu · foreign_flow           │
└─────────────────────────────────────────────────────────────────────┘
```

Todo o stack roda em **Docker Compose** (um container por serviço).

---

## Fontes de Dados — Detalhe por Série

### 1. Saldo Acumulado do Investidor Estrangeiro

- **URL principal:** `https://www.dadosdemercado.com.br/fluxo`
- **Endpoint esperado:** verificar via DevTools se existe `/api/fluxo` ou similar exposto pelo site.
- **Período:** acumulado no ano calendário (reset a cada janeiro).
- **Frequência de atualização:** diária (D+1 útil).
- **Estratégia de fallback:** B3 publica o boletim de participação por investidor nos relatórios diários (arquivo CSV no portal de dados abertos da B3).
- **Unidade:** R$ milhões acumulados no ano.

### 2. COT 6L — Brazilian Real Futures (Asset Manager / Managed Money)

- **Fontes primárias:**
  - CFTC Disaggregated COT: `https://www.cftc.gov/dea/newcot/deafinwk.txt` (arquivo semanal, publicado toda terça-feira referente à posição de sexta passada)
  - Tradingster: `https://www.tradingster.com/cot/futures/fin/102741` (código CFTC do BRL = 102741)
  - Barchart: `https://www.barchart.com/futures/commitment-of-traders/interactive-charts/L6*0`
- **Campo desejado:** Asset Manager Net (longs − shorts) ou Managed Money Net, dependendo do relatório.
  - No relatório **Disaggregated** (CFTC): coluna `Asset Manager` net.
  - No relatório **Legacy**: coluna `Non-Commercial` net (proxy).
- **Período:** a partir de janeiro de 2026 (mas carregar histórico desde 2016 para contexto visual como no NetPositions.png).
- **Frequência:** semanal (relatório CFTC toda sexta/terça).
- **Download direto CFTC (histórico completo):**
  ```
  https://www.cftc.gov/files/dea/history/fin_fut_txt_{ANO}.zip
  ```
  Arquivo com todos os contratos; filtrar por `Market_and_Exchange_Names` contendo `BRAZILIAN REAL` ou código `102741`.
- **Validação cruzada:** comparar valor extraído do CFTC com o exibido no Tradingster para o mesmo período — devem coincidir.

### 3. Preço Unitário NTN-B 2035 (BRSTNCNTB3E2)

- **Fonte primária:** Tesouro Direto — séries históricas públicas.
  - URL de download: `https://www.tesourodireto.com.br/json/br/com/b3/tesourodireto/model/dto/PriceDateDTO.json`
  - Ou via planilha histórica: `https://www.tesourodireto.com.br/titulos/historico-de-precos-e-taxas.htm` (arquivo XLS disponível para download).
  - Código do papel: **NTN-B Principal 2035** (sem cupons = PU cheio, não amortizado).
- **Fonte secundária:** MaisRetorno comparador: `https://maisretorno.com/app/comparador-ativos?a=ntn-b-15-05-2035-brstncntb3e2:tp`
- **Campo:** `Preço Unitário` (R$) — série diária (dias úteis).
- **Validação:** cruzar dado do Tesouro Direto com o exibido no MaisRetorno para pelo menos os últimos 30 dias.

### 4. IBOVESPA

- **Fonte primária:** Yahoo Finance ticker `^BVSP`
  - Biblioteca Python: `yfinance` — `yf.download("^BVSP", start="2023-01-01")`
- **Fonte secundária:** B3 dados históricos: `https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-amplos/ibovespa.htm`
- **Campo:** fechamento diário (Close).
- **Frequência:** diária (dias úteis).

---

## Banco de Dados

### Engine: PostgreSQL 16

### Esquema

```sql
-- Tabela IBOVESPA
CREATE TABLE ibov_daily (
    date        DATE PRIMARY KEY,
    close       NUMERIC(12, 2) NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Tabela COT 6L
CREATE TABLE cot_6l (
    report_date        DATE PRIMARY KEY,
    asset_mgr_long     INTEGER NOT NULL,
    asset_mgr_short    INTEGER NOT NULL,
    asset_mgr_net      INTEGER GENERATED ALWAYS AS (asset_mgr_long - asset_mgr_short) STORED,
    source             TEXT DEFAULT 'CFTC',
    updated_at         TIMESTAMPTZ DEFAULT now()
);

-- Tabela NTN-B 2035 PU
CREATE TABLE ntnb35_pu (
    date        DATE PRIMARY KEY,
    pu          NUMERIC(14, 6) NOT NULL,
    yield_pct   NUMERIC(8, 4),            -- taxa indicativa (% a.a.)
    updated_at  TIMESTAMPTZ DEFAULT now()
);

-- Tabela Fluxo Estrangeiro
CREATE TABLE foreign_flow (
    date              DATE PRIMARY KEY,
    daily_flow_mm     NUMERIC(14, 2),     -- R$ milhões no dia
    ytd_flow_mm       NUMERIC(14, 2),     -- acumulado no ano
    updated_at        TIMESTAMPTZ DEFAULT now()
);

-- Índices auxiliares
CREATE INDEX ON ibov_daily (date DESC);
CREATE INDEX ON cot_6l (report_date DESC);
CREATE INDEX ON ntnb35_pu (date DESC);
CREATE INDEX ON foreign_flow (date DESC);
```

### Migrações

Gerenciadas via **Alembic** (integrado ao FastAPI backend).

---

## Backend — FastAPI

### Estrutura de pastas

```
backend/
├── app/
│   ├── main.py
│   ├── config.py               # env vars via pydantic-settings
│   ├── database.py             # SQLAlchemy engine + session
│   ├── models/
│   │   ├── ibov.py
│   │   ├── cot.py
│   │   ├── ntnb35.py
│   │   └── foreign_flow.py
│   ├── schemas/
│   │   └── timeseries.py       # Pydantic response schemas
│   ├── routers/
│   │   ├── ibov.py             # GET /api/ibov?from=&to=
│   │   ├── cot.py              # GET /api/cot?from=&to=
│   │   ├── ntnb35.py           # GET /api/ntnb35?from=&to=
│   │   └── foreign_flow.py     # GET /api/foreign-flow?from=&to=
│   └── collectors/
│       ├── ibov_collector.py
│       ├── cot_collector.py
│       ├── ntnb35_collector.py
│       └── foreign_flow_collector.py
├── alembic/
│   └── versions/
├── requirements.txt
└── Dockerfile
```

### Endpoints principais

```
GET  /api/ibov?from=YYYY-MM-DD&to=YYYY-MM-DD
GET  /api/cot?from=YYYY-MM-DD&to=YYYY-MM-DD
GET  /api/ntnb35?from=YYYY-MM-DD&to=YYYY-MM-DD
GET  /api/foreign-flow?from=YYYY-MM-DD&to=YYYY-MM-DD
GET  /api/all?from=YYYY-MM-DD&to=YYYY-MM-DD   ← endpoint combinado (join por date)
POST /api/collect/trigger                      ← disparo manual da coleta
GET  /health
```

### Resposta padrão (série temporal)

```json
{
  "series": "ibov",
  "from": "2026-01-02",
  "to": "2026-06-25",
  "data": [
    { "date": "2026-01-02", "value": 125430.5 },
    { "date": "2026-01-03", "value": 126010.0 }
  ]
}
```

---

## Scheduler — Coleta Automática

Implementado com **APScheduler** (embutido no backend) ou como worker **Celery + Redis** separado (recomendado para produção).

| Série | Horário de coleta | Observação |
|-------|-------------------|------------|
| IBOVESPA | 19:00 BRT dias úteis | Após fechamento B3 |
| Fluxo estrangeiro | 20:00 BRT dias úteis | Dado D+1 |
| NTN-B 2035 PU | 18:30 BRT dias úteis | Tesouro publica após fechamento |
| COT 6L | Toda terça-feira 16:00 BRT | CFTC publica ~15:30 ET |

---

## Frontend — Dashboard HTML

### Stack

- HTML5 + CSS3 (grid layout responsivo)
- **Vanilla JS** ou **Alpine.js** (sem framework pesado)
- **Highcharts** (licença gratuita para projetos não-comerciais) ou **Chart.js + chartjs-plugin-zoom**
- Comunicação com backend via `fetch()` (REST)

### Layout

```
┌──────────────────────────────────────────────────────────┐
│  INTERMARKET DASHBOARD  |  período: [6M][1A][2A][3A][5A] │
├──────────────────────────────────────────────────────────┤
│  Toggles:  [■ IBOVESPA] [■ 6L COT] [■ NTNB-35] [■ Fluxo]│
├──────────────────────────────────────────────────────────┤
│                                                          │
│          GRÁFICO OVERLAY (canvas principal)              │
│     Quatro séries normalizadas no mesmo eixo %           │
│     Eixo Y esquerdo: variação % desde início do período  │
│     Eixo Y direito: escala absoluta da série ativa       │
│                                                          │
│  ─────────────────────── timeline scrubber ─────────────│
└──────────────────────────────────────────────────────────┘
│  Tabela de correlações (rolling 60d): matriz 4x4         │
└──────────────────────────────────────────────────────────┘
```

### Comportamento dos toggles

- Cada série tem cor fixa:
  - IBOVESPA → **azul-ciano** (como `ibovlinha.png`)
  - 6L COT Asset Mgr → **preto** (como `model.example.png`)
  - NTN-B 2035 PU → **vermelho** (como `mAISrETORNO.png`)
  - Fluxo estrangeiro → **vermelho escuro / bordô**
- Normalização padrão: todas as séries indexadas a 100 no início do período selecionado.
- Opção de "escala absoluta" por série via duplo-clique na legenda.

---

## Docker Compose

### Arquivo `docker-compose.yml`

```yaml
version: "3.9"

services:

  db:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: intermarket
      POSTGRES_USER: intermarket
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  backend:
    build: ./backend
    restart: unless-stopped
    depends_on:
      - db
    environment:
      DATABASE_URL: postgresql+asyncpg://intermarket:${DB_PASSWORD}@db:5432/intermarket
      CFTC_DOWNLOAD_URL: https://www.cftc.gov/files/dea/history/fin_fut_txt_2026.zip
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app

  scheduler:
    build: ./backend
    command: python -m app.scheduler
    restart: unless-stopped
    depends_on:
      - db
      - backend
    environment:
      DATABASE_URL: postgresql+asyncpg://intermarket:${DB_PASSWORD}@db:5432/intermarket

  frontend:
    image: nginx:alpine
    restart: unless-stopped
    depends_on:
      - backend
    volumes:
      - ./frontend:/usr/share/nginx/html:ro
      - ./nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
    ports:
      - "80:80"

volumes:
  pgdata:
```

### Arquivo `nginx/default.conf`

```nginx
server {
    listen 80;

    location / {
        root /usr/share/nginx/html;
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://backend:8000/api/;
        proxy_set_header Host $host;
    }
}
```

---

## Etapas Cronológicas de Desenvolvimento

### FASE 1 — Infraestrutura Base (Dias 1–3)

**Objetivo:** ambiente Docker funcionando com banco de dados e backend respondendo.

- [ ] 1.1 Criar estrutura de pastas do projeto (`backend/`, `frontend/`, `nginx/`, `docs/`)
- [ ] 1.2 Criar `docker-compose.yml` com serviços `db` e `backend`
- [ ] 1.3 Configurar `backend/Dockerfile` com Python 3.12, FastAPI, SQLAlchemy async, Alembic
- [ ] 1.4 Criar `database.py` com connection pool async (asyncpg)
- [ ] 1.5 Escrever e rodar migration inicial (Alembic) criando as 4 tabelas
- [ ] 1.6 Testar: `docker compose up db backend` → `GET /health` retorna 200

**Entregável:** containers `db` + `backend` rodando; tabelas criadas no PostgreSQL.

---

### FASE 2 — Collector IBOVESPA (Dias 3–4)

**Objetivo:** popular `ibov_daily` com dados históricos e testar endpoint.

- [ ] 2.1 Instalar `yfinance` no backend
- [ ] 2.2 Criar `collectors/ibov_collector.py`:
  - Função `fetch_ibov(start, end)` → usa `yf.download("^BVSP")`
  - Upsert no PostgreSQL (INSERT ... ON CONFLICT DO UPDATE)
- [ ] 2.3 Criar script de carga histórica: `python -m app.collectors.ibov_collector --from 2016-01-01`
- [ ] 2.4 Criar `routers/ibov.py` com `GET /api/ibov`
- [ ] 2.5 Testar: query retorna JSON com fechamentos diários

**Entregável:** `/api/ibov?from=2026-01-01` retorna dados corretos.

---

### FASE 3 — Collector COT 6L (Dias 4–7)

**Objetivo:** popular `cot_6l` com posições do Asset Manager desde 2016.

- [ ] 3.1 Criar `collectors/cot_collector.py`:
  - Download do arquivo ZIP anual CFTC: `fin_fut_txt_{ANO}.zip`
  - Parser do arquivo `.txt` (formato fixed-width / CSV), filtrar código `102741`
  - Extrair colunas: `Report_Date_as_YYYY-MM-DD`, `Asset_Mgr_Positions_Long_All`, `Asset_Mgr_Positions_Short_All`
  - Upsert em `cot_6l`
- [ ] 3.2 Carga histórica anos 2016–2025 (loop nos ZIPs anuais)
- [ ] 3.3 Carga incremental: download do arquivo semanal `deafinwk.txt` para dados correntes
- [ ] 3.4 Criar `routers/cot.py` com `GET /api/cot`
- [ ] 3.5 Validação cruzada: comparar 5 datas aleatórias com valores exibidos no Tradingster `102741`
- [ ] 3.6 Testar endpoint

**Entregável:** `/api/cot` retorna net positions Asset Manager com dados validados.

---

### FASE 4 — Collector NTN-B 2035 PU (Dias 7–9)

**Objetivo:** popular `ntnb35_pu` com preço unitário histórico.

- [ ] 4.1 Criar `collectors/ntnb35_collector.py`:
  - Download da planilha histórica do Tesouro Direto (XLS/CSV)
  - URL: `https://www.tesourodireto.com.br/titulos/historico-de-precos-e-taxas.htm`
  - Filtrar papel `NTN-B Principal 2035` (vencimento 15/05/2035)
  - Extrair: data, PU de venda, taxa indicativa
  - Upsert em `ntnb35_pu`
- [ ] 4.2 Carga histórica completa disponível
- [ ] 4.3 Criar `routers/ntnb35.py` com `GET /api/ntnb35`
- [ ] 4.4 Validação cruzada: comparar últimos 30 dias com MaisRetorno
- [ ] 4.5 Testar endpoint

**Entregável:** `/api/ntnb35` retorna PU com série completa validada.

---

### FASE 5 — Collector Fluxo Estrangeiro (Dias 9–11)

**Objetivo:** popular `foreign_flow` com saldo acumulado no ano.

- [ ] 5.1 Investigar API pública do `dadosdemercado.com.br/fluxo` via DevTools:
  - Identificar endpoint XHR/fetch
  - Verificar se há parâmetros de data e retorno JSON
- [ ] 5.2 Criar `collectors/foreign_flow_collector.py`:
  - Chamar endpoint identificado com headers adequados (User-Agent, etc.)
  - Calcular `ytd_flow_mm` (soma acumulada desde 01/01 do ano corrente)
  - Upsert em `foreign_flow`
- [ ] 5.3 Fallback B3: caso o site bloqueie scraping, usar os relatórios de participação por investidor da B3 (arquivo CSV diário no portal de dados abertos)
- [ ] 5.4 Criar `routers/foreign_flow.py` com `GET /api/foreign-flow`
- [ ] 5.5 Testar endpoint

**Entregável:** `/api/foreign-flow` retorna saldo acumulado diário.

---

### FASE 6 — Scheduler Automático (Dias 11–12)

**Objetivo:** coleta automática diária sem intervenção manual.

- [ ] 6.1 Criar `app/scheduler.py` usando APScheduler (AsyncIOScheduler)
- [ ] 6.2 Configurar jobs conforme tabela de horários (seção Scheduler)
- [ ] 6.3 Adicionar retry automático (máx. 3 tentativas com backoff exponencial)
- [ ] 6.4 Logging estruturado (JSON) para cada execução de coleta
- [ ] 6.5 Adicionar serviço `scheduler` ao `docker-compose.yml`
- [ ] 6.6 Testar disparo manual via `POST /api/collect/trigger`

**Entregável:** coleta automática rodando; logs visíveis no Docker.

---

### FASE 7 — Endpoint Combinado + Normalização (Dia 12–13)

**Objetivo:** endpoint único que entrega todas as séries alinhadas por data.

- [ ] 7.1 Criar `GET /api/all?from=&to=&normalize=true`
  - Inner join das 4 tabelas por data (dias com todas as séries disponíveis)
  - Normalização opcional: indexar tudo a 100 na data inicial do período
- [ ] 7.2 Calcular correlações rolling (janela 60 dias)
- [ ] 7.3 Testar resposta JSON completa

**Entregável:** `/api/all` retorna objeto com 4 séries + matriz de correlação.

---

### FASE 8 — Frontend Dashboard (Dias 13–18)

**Objetivo:** dashboard HTML interativo com overlay das séries.

- [ ] 8.1 Criar `frontend/index.html` com layout base (grid CSS)
- [ ] 8.2 Integrar Highcharts (via CDN) com configuração de múltiplos eixos Y
- [ ] 8.3 Implementar fetch de `/api/all` e renderização das 4 séries sobrepostas
- [ ] 8.4 Implementar toggles (checkboxes) por série com cores fixas
- [ ] 8.5 Implementar seletor de período: 6M / 1A / 2A / 3A / 5A / custom
- [ ] 8.6 Normalização visual: botão "% desde início" vs "valores absolutos"
- [ ] 8.7 Timeline scrubber (range selector nativo do Highcharts)
- [ ] 8.8 Tabela de correlações rolling (HTML + CSS)
- [ ] 8.9 Responsividade mobile
- [ ] 8.10 Adicionar serviço `frontend` + `nginx` ao `docker-compose.yml`

**Entregável:** dashboard acessível em `http://localhost:80` com overlay funcional.

---

### FASE 9 — Testes e Validação (Dias 18–20)

**Objetivo:** garantir integridade dos dados e robustez do sistema.

- [ ] 9.1 Teste de integridade: comparar todos os valores finais com fontes primárias
- [ ] 9.2 Teste de carga: simular 30 dias de coletas consecutivas
- [ ] 9.3 Teste de falha: simular indisponibilidade de cada fonte e verificar fallback
- [ ] 9.4 Adicionar endpoint `GET /api/data-quality` com checklist de gaps por série
- [ ] 9.5 Documentar quaisquer discrepâncias encontradas na validação cruzada

---

### FASE 10 — Deploy e Documentação Final (Dias 20–22)

**Objetivo:** sistema pronto para uso contínuo.

- [ ] 10.1 Criar `.env.example` com todas as variáveis de ambiente necessárias
- [ ] 10.2 Criar `Makefile` com comandos: `make up`, `make down`, `make seed`, `make collect`
- [ ] 10.3 Escrever `README.md` com instruções de instalação e uso
- [ ] 10.4 Configurar volume de backup do PostgreSQL
- [ ] 10.5 Testar fluxo completo do zero: `git clone` → `make up` → dashboard funcionando

---

## Dependências Python (backend/requirements.txt)

```
fastapi==0.111.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
pydantic-settings==2.3.0
yfinance==0.2.40
httpx==0.27.0
pandas==2.2.2
openpyxl==3.1.2          # leitura XLS Tesouro Direto
apscheduler==3.10.4
python-dotenv==1.0.1
```

---

## Variáveis de Ambiente (.env)

```env
DB_PASSWORD=changeme
DATABASE_URL=postgresql+asyncpg://intermarket:changeme@db:5432/intermarket
CFTC_BASE_URL=https://www.cftc.gov/files/dea/history
TESOURO_DIRETO_XLS_URL=https://www.tesourodireto.com.br/json/br/com/b3/tesourodireto/model/dto/PriceDateDTO.json
DADOSDEMERCADO_FLUXO_URL=https://www.dadosdemercado.com.br/fluxo
TZ=America/Sao_Paulo
```

---

## Notas de Validação Cruzada

Antes de considerar qualquer coletor como "finalizado", executar as seguintes verificações:

### COT 6L
1. Acessar `https://www.tradingster.com/cot/futures/fin/102741`
2. Anotar o valor de "Asset Manager Net" para 3 datas recentes
3. Comparar com os valores armazenados em `cot_6l.asset_mgr_net`
4. Tolerância aceitável: 0 contratos de diferença (dado é exato, não estimado)

### NTN-B 2035 PU
1. Acessar planilha histórica no Tesouro Direto
2. Anotar PU para 5 datas nos últimos 30 dias
3. Comparar com `ntnb35_pu.pu`
4. Tolerância aceitável: ≤ R$ 0,01 (diferença de arredondamento)

### IBOVESPA
1. Acessar Yahoo Finance `^BVSP`
2. Comparar fechamento de 5 datas recentes
3. Comparar com `ibov_daily.close`
4. Tolerância: 0 pontos (dado exato)

### Fluxo Estrangeiro
1. Acessar `dadosdemercado.com.br/fluxo` e anotar saldo de 3 datas
2. Comparar com `foreign_flow.ytd_flow_mm`
3. Tolerância: ≤ R$ 10 milhões (possível diferença de hora de captura)

---

## Estrutura Final de Pastas do Projeto

```
intermarket-dashboard/
├── docker-compose.yml
├── .env.example
├── Makefile
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── config.py
│       ├── database.py
│       ├── scheduler.py
│       ├── models/
│       ├── schemas/
│       ├── routers/
│       └── collectors/
├── frontend/
│   ├── index.html
│   ├── css/
│   │   └── dashboard.css
│   └── js/
│       ├── api.js
│       ├── chart.js
│       └── controls.js
├── nginx/
│   └── default.conf
├── alembic/
│   ├── env.py
│   └── versions/
└── docs/
    └── SISTEMA_INTERMARKET.md  ← este arquivo
```