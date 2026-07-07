# Hierarquia de Fontes — Macro Dashboard

> Criado em Jul/2026. Quando Claude buscar qualquer dado financeiro para este dashboard,
> deve seguir esta hierarquia obrigatoriamente. Gatilho: "procure informações".

---

## Regra geral

**NUNCA** usar memória de treinamento para dados financeiros (targets, preços, taxas, pesquisas).
**SEMPRE** buscar via WebSearch na ordem abaixo, verificar o dado contra o valor atual de mercado,
e registrar o mês/ano da fonte.

Se o target de um banco está **abaixo do preço spot e a visão é "BULL"**, o dado está errado ou desatualizado.

---

## TIER-1 — Sites oficiais dos bancos (consultar PRIMEIRO)

| Banco | URL pública de research |
|---|---|
| Goldman Sachs | goldmansachs.com/insights |
| JPMorgan | jpmorgan.com/insights/global-research/commodities |
| Morgan Stanley | morganstanley.com/insights |
| Bank of America | bankofamerica.com/invest/insights |
| Citi | citigroup.com/global/insights |
| XP Investimentos | conteudos.xpi.com.br |
| BTG Pactual | btgpactual.com/research |
| Itaú BBA | itau.com.br/itaubba-pt/analises-e-publicacoes |

---

## TIER-2 — Órgãos governamentais e bolsas (dados primários)

### Brasil
| Fonte | URL | Dado |
|---|---|---|
| BCB Focus | bcb.gov.br/publicacoes/focus | Selic, IPCA, câmbio — toda sexta |
| BCB COPOM | bcb.gov.br/publicacoes/atascopom | Decisão de juros |
| BCB Rel. Pol. Monetária | bcb.gov.br/publicacoes/politicamonetaria | Projeções BCB (trimestral) |
| IBGE | ibge.gov.br/explica/inflacao.php | IPCA mensal |

### EUA
| Fonte | URL | Dado |
|---|---|---|
| Fed FOMC | federalreserve.gov/monetarypolicy/fomccalendars.htm | Fed rate, dot plot |
| BLS CPI | bls.gov/cpi | CPI EUA mensal |
| BLS NFP | bls.gov/news.release/empsit.toc.htm | Non-Farm Payrolls |
| FRED | fred.stlouisfed.org | Séries históricas + API |

### Commodities — Bolsas oficiais
| Fonte | URL | Dado |
|---|---|---|
| CME Group | cmegroup.com | Gold GC, Silver SI, **Cobre HG USD/lb**, WTI CL |
| LME | lme.com | Cobre USD/ton — referência internacional dos bancos |
| EIA | eia.gov/outlooks/steo | WTI/Brent + Short-Term Energy Outlook mensal |
| Kitco | kitco.com | Metais preciosos spot + notícias de bancos sobre metais |

### Eleições Brasil
| Fonte | URL |
|---|---|
| Datafolha | datafolha.folha.uol.com.br |
| Quaest | quaest.com.br |
| Atlas Intel | atlasintel.com.br |
| TSE (repositório oficial) | divulgacandcontas.tse.jus.br |

---

## TIER-3 — Imprensa financeira de referência (usar se TIER-1 e TIER-2 não tiverem)

### Mercado americano/global
| Veículo | URL | Nota |
|---|---|---|
| **Bloomberg** | bloomberg.com/markets | Referência máxima do mercado. Paywall — manchetes/primeiros parágrafos públicos |
| **CNBC** | cnbc.com/investing | TV financeira líder EUA — primeiros a publicar revisões de bancos |
| **CNN Business** | cnn.com/business/markets | Cobertura de qualidade de eventos macro e revisões |
| **Reuters** | reuters.com/markets/commodities | Agência global — muito rápida e geralmente acessível |
| **Financial Times** | ft.com/markets | Referência britânica de alto nível. Paywall forte |
| **Wall Street Journal** | wsj.com/markets | Referência americana de alto nível. Paywall |
| **TheStreet** | thestreet.com/investing | Ótimo para artigos de revisão de target de bancos |
| **Investing.com** | investing.com/news/commodities-news | Ampla cobertura, preços em tempo real |
| **OilPrice.com** | oilprice.com | Especializado em petróleo e energia |
| **Mining.com** | mining.com | Especializado em mineração, cobre, ouro, prata |
| **Trading Economics** | tradingeconomics.com/commodity | Séries históricas + consensus de previsões |

### Mercado brasileiro
| Veículo | URL |
|---|---|
| Valor Econômico | valor.globo.com |
| InfoMoney | infomoney.com.br/mercados |
| Broadcast / Agência Estado | broadcast.com.br |
| Exame | exame.com/economia |
| Money Times | moneytimes.com.br |

---

## Notas técnicas — Cobre

- **COMEX HG** (EUA) = USD/lb — pode ter prêmio vs LME quando há tarifas de importação
- **LME** (internacional) = USD/ton — referência usada pelos bancos nos forecasts
- Conversão: `USD/lb × 2.204,62 = USD/ton` | `USD/ton ÷ 2.204,62 = USD/lb`
- Sempre especificar COMEX vs LME ao comparar spot com targets

## Notas técnicas — Forecasts desatualizados

- Se cobre subiu 27% em 7 meses, forecasts de dez/25 são inutilizáveis vs mercado atual
- Sempre verificar: "houve revisão deste banco nos últimos 2 meses?"
- Se sim → buscar revisão. Se não → sinalizar ao usuário que o dado pode estar desatualizado
