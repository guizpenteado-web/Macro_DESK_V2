# Fontes confiáveis — Calls de bancos por ação individual (módulo `/acoes`)

Criado em 26/jul/2026. Objetivo: toda vez que o usuário pedir pra "atualizar" o IBOV Calls / módulo de ações, buscar primeiro nessas fontes específicas, em vez de busca exploratória genérica — mais rápido, mais consistente, mais fácil de auditar.

Complementa (não substitui) `reference_sources_database.md`, que cobre a hierarquia TIER-1/2/3 pra dados macro e calls de Ibovespa/Brasil como mercado. Este documento é específico pra **preço-alvo/recomendação de ação individual**.

---

## TIER-0 — grupo de WhatsApp do usuário (26/jul/2026)

O usuário recebe calls diárias num grupo de WhatsApp (formato típico: `++ {Banco} tem recomendação de {compra/venda} para {Empresa}, com preço-alvo de R$ {X}` seguido de um parágrafo de contexto). Isso é potencialmente a fonte mais rica e mais fresca de todas — cobre calls que ainda não foram indexadas/republicadas por nenhum portal público.

**Workflow acordado**: o usuário exporta o chat periodicamente (WhatsApp → grupo → ⋮ → Mais → Exportar conversa → **Sem mídia**, gera um `.txt`) e manda o arquivo. Processo ao receber:
1. Extrair cada call do texto (banco, ativo, ação, alvo, alvo anterior se houver, data da mensagem)
2. Tentar confirmar cada uma contra uma fonte pública (TIER-1/2 abaixo) — mesma disciplina de sempre, nunca inserir sem verificar
3. As confirmadas entram no dataset normalmente, com a URL da fonte pública encontrada
4. As **não confirmadas** ficam numa lista separada pra o usuário decidir: inserir mesmo assim com tag "fonte: grupo, não confirmada externamente", ou aguardar alguns dias pra ver se algum portal republica

**Achado real (26/jul/2026)**: usuário mandou um exemplo — "JPMorgan compra Motiva, alvo R$19, após leilão Régis Bittencourt (23/jul)". Busca pública não confirmou JPMorgan com esse valor: achou **Bradesco BBI com R$19** (bate o valor, banco errado) e **JPMorgan com R$18** (bate o banco, mas de set/2025, desatualizado). Duas hipóteses: (a) o grupo tem uma nota do JPMorgan pós-leilão ainda não republicada publicamente — bem provável, já que o leilão foi só um dia antes; (b) troca de banco no repasse da mensagem. **Lição**: mesmo vindo de uma fonte "de dentro", sempre tentar cross-check — e se não confirmar, não travar a call no dataset como se fosse fato consolidado.

## TIER-1 — fontes diretas dos bancos (melhor sinal, mais raro de achar tudo)

| Banco | Onde buscar |
|---|---|
| **BTG Pactual** | `content.btgpactual.com/research/ativo/{TICKER}` — página por ativo, tem PDF de research quando disponível |
| **XP Investimentos** | `conteudos.xpi.com.br/acoes/{ticker minúsculo}/` |
| **BB Investimentos** | `investalk.bb.com.br/noticias/mercado/` — padrão de URL slug muito útil: `{ticker}-revisao-preco-{mes}{ano}` (ex: `abev-revisao-preco-marco-26`, `assai-asai3-revisao-preco-fev26`). Buscar `site:investalk.bb.com.br revisao preco {TICKER}` direto acha rápido. |

## TIER-2 — portais que republicam revisão de banco com detalhe de valor antigo/novo (a fonte mais produtiva na prática)

Esses sites são os que mais renderam resultado hoje — sempre citam banco, valor antigo→novo e recomendação, o que a busca genérica sozinha não filtra bem:

| Portal | Padrão de busca que funciona bem |
|---|---|
| **Seu Dinheiro** (`seudinheiro.com/2026/empresas/...` e `/bolsa-dolar/...`) | de longe a fonte mais rica hoje — cobre Citi, BofA, Safra, Bradesco BBI, JPMorgan, Goldman, Santander com todo o antigo→novo. Buscar `seudinheiro {banco} {TICKER} preço-alvo` |
| **Money Times** (`moneytimes.com.br`) | boa cobertura de cortes/altas de preço-alvo, títulos diretos tipo "Banco corta/eleva preço-alvo de TICKER" |
| **InfoMoney** (`infomoney.com.br/mercados/`) | forte pra JPMorgan/Goldman especificamente |
| **Guia do Investidor** (`guiadoinvestidor.com.br`) | tem páginas-resumo "Preço-alvo TICKER 2026" que agregam vários bancos numa única página — bom ponto de partida pra descobrir quais bancos cobrem um ativo antes de caçar a data exata de cada um |
| **EuQueroInvestir** (`euqueroinvestir.com/acoes/`) | boa pra Citi e BTG especificamente |
| **Suno Research** (`suno.com.br/noticias/`) | boa cobertura geral, útil como segunda fonte pra confirmar |

## TIER-3 — agregadores (bons pra achar QUE bancos cobrem um ativo, ruins pra data exata)

| Fonte | Uso |
|---|---|
| **Investing.com** (`investing.com/equities/{empresa}-consensus-estimates`) | preço-alvo médio/mín/máx consolidado — útil como sanity check, não pra atribuir a um banco específico |
| **Investidor10** / **Status Invest** | idem, bom pra pegar a lista de quem cobre o ativo |
| **Riconnect (Rico)** / **BTG Pactual Content** | espelham research de vários bancos, mas nem sempre com data clara |

---

## Como pesquisar um ticker novo (sequência validada)

1. `{banco} {TICKER} preço-alvo banco 2026` — pega o panorama geral de quem cobriu recentemente
2. Se o snippet não trouxer data exata, `WebFetch` direto na URL da Seu Dinheiro/InfoMoney/Money Times que aparecer — essas quase sempre têm a data de publicação no topo do artigo
3. **Sempre conferir se a data é realmente 2026** — vários resultados trazem artigos de final de 2025 (Nov/Dez/2025) discutindo "preço-alvo pra 2026", que não contam pro nosso recorte "desde início de 2026"
4. **Sempre checar o dia da semana da data antes de gravar** (`date(y,m,d).strftime('%A')` em Python) — se cair em fim de semana, o marcador some do gráfico (ver [[feedback-hub-proxy-fetch-rewrite]] pro tipo de bug relacionado, e a lição de fim de semana em [[project-ibov-calls]])
5. Adicionar em `IbovCalls/server.py` → `STOCK_CALLS` (dentro de `get_stock_calls()`) e `TICKER_NAMES`, sempre com `url` apontando pra fonte real

## Bancos rastreados (mesmos 11 do IBOV Calls macro)

BTG Pactual · Itaú BBA · Morgan Stanley · BofA · Goldman Sachs · JP Morgan · Citi · XP Investimentos · UBS · Santander · BB Investimentos

## Regra de categorização — o que entra aqui vs. no IBOV Calls principal

Ver [[project-ibov-calls]]: call sobre **uma ação específica** por dinâmica própria dela (resultado trimestral, setor) → só aqui (`/acoes`). Call sobre **Brasil/Ibovespa como mercado** ou **troca de carteira recomendada** → lista principal do IBOV Calls (pode citar ações, mas o tema é o mercado como um todo).

## Estado da cobertura (atualizar essa lista a cada expansão)

- **26/jul/2026** (primeira leva): 13 ativos, 18 calls
- **26/jul/2026** (segunda leva, mesmo dia): 21 ativos, 32 calls — PRIO3, SUZB3, RDOR3, LREN3, BBSE3, GGBR4, ABEV3, ASAI3 adicionados
- **26/jul/2026** (terceira leva, mesmo dia): 28 ativos, 39 calls — EMBJ3, RAIL3, TOTS3, VIVT3, USIM5, CSNA3, MULT3 adicionados

## Armadilha real: tickers que mudaram de código na B3

**Embraer trocou de EMBR3 para EMBJ3 em novembro/2025** (ADR: de ERJ para EMBJ na NYSE). Mesma empresa, mesmo papel — só o código mudou. A maioria dos resultados de busca de 2026 já usa o código novo (EMBJ3), mas fontes mais antigas ou não atualizadas ainda citam EMBR3. **Antes de cadastrar um ticker novo, sempre confirmar se o código ainda é o vigente na B3** — pesquisar `"{empresa}" ticker B3 mudou` se o ticker retornado nos resultados parecer estranho ou inconsistente entre fontes. Cadastrar sempre com o código atual (o `/api/stock-quote` via yfinance só funciona com o ticker vigente + `.SA`).

## Bancos fora dos 11 rastreados no IBOV Calls macro que aparecem em calls de ação individual

**Safra** e **Bradesco BBI** cobrem bastante ação individual mas não fazem parte da lista de 11 bancos macro do IBOV Calls principal. Ambos têm cor própria em `BANK_COLORS` no `acoes.html` (Safra `#00695c`, Bradesco BBI `#c40000`) — **sempre que adicionar um banco novo ao `STOCK_CALLS`, conferir se ele já tem cor em `BANK_COLORS`**, senão cai no fallback genérico `#58a6ff` e fica indistinguível de outro banco sem cor definida.
