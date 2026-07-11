# Macro Desk — Contexto de Sessão

Leia este arquivo no início de TODA sessão. Contém o mapa completo dos projetos.

## Visão Geral

5 projetos de análise de mercado financeiro brasileiro. O usuário é o Guilherme (guizpenteado@gmail.com).

| Projeto | Pasta | Porta hub | Porta standalone |
|---|---|---|---|
| **Hub Unificado** | `Mktsentiment/` | — | 8000 (público) |
| **P1 — Intermarket** | `Mktsentiment/dashboard/` | /intermarket/ → :8010 | — |
| **P2 — Market Breadth Ultra** | `Market_BREADTH_ULTRA/` | /breadth/ → :8011 | 8001 |
| **P3 — Pine Script (TradingView)** | `Mktsentiment/docs/` | — | sem servidor |
| **P4 — Macro Dashboard** | `MacroDashboard/` | /macro/ → :8012 | 8002 |
| **P5 — SmartMoney** | `SmartMoneyBR/` | /smartmoney/ → backend :8100 + frontend :3100 | — |

**Para iniciar TUDO:** `c:\Users\Guilherme\Documents\Mktsentiment\start_hub.bat`  
**URL pública (ngrok):** `https://jawed-sermon-extras.ngrok-free.dev`  
**ngrok:** abre automaticamente no PC do Guilherme, tunel fixo na conta dele.

---

## Arquitetura do Hub

`unified_server.py` — FastAPI na porta 8000 que:
1. Sobe 3 sub-servidores como subprocessos (8010, 8011, 8012)
2. Serve shell HTML com 3 botões nav (cyan=Intermarket, purple=Breadth, gold=Macro)
3. Proxy reverso via httpx: `/intermarket/` → :8010, `/breadth/` → :8011, `/macro/` → :8012
4. Reescreve paths HTML no proxy para manter URLs relativas funcionando

**Armadilha crítica:** Sempre que reiniciar, garantir que as portas 8000, 8010, 8011, 8012 estejam livres. O `start_hub.bat` faz isso automaticamente.

---

## Docs detalhados (ler quando for trabalhar em cada projeto)

Estão em `C:\Users\Guilherme\.claude\projects\c--Users-Guilherme-Documents-Mktsentiment\memory\projetos\`

- [P1 — Intermarket](../../../.claude/projects/c--Users-Guilherme-Documents-Mktsentiment/memory/projetos/p1_intermarket/doc.md)
- [P2 — Market Breadth Ultra](../../../.claude/projects/c--Users-Guilherme-Documents-Mktsentiment/memory/projetos/p2_breadth_ultra/doc.md)
- [P3 — Pine Script](../../../.claude/projects/c--Users-Guilherme-Documents-Mktsentiment/memory/projetos/p3_pine_script/doc.md)
- [P4 — Macro Dashboard](../../../.claude/projects/c--Users-Guilherme-Documents-Mktsentiment/memory/projetos/p4_macro_dashboard/doc.md)
- [Hub Unificado](../../../.claude/projects/c--Users-Guilherme-Documents-Mktsentiment/memory/projetos/hub_unificado/doc.md)

---

## Armadilhas que já custaram tempo

1. **Plotly bar chart com meses:** SEMPRE usar `xaxis: { type: "category" }` — sem isso, "Jan","Fev" viram Unix epoch (Dec 31, 1969).
2. **onclick="" + event.currentTarget:** É null em atributos inline. Usar `onclick="fn(this)"` e receber `btn` no parâmetro.
3. **Pine Script array.from():** TODOS os elementos na mesma linha. Nunca quebrar linha dentro de array.from().
4. **Hub porta 8000 ocupada:** Processo antigo em 127.0.0.1:8000 intercepta antes do novo em 0.0.0.0:8000. Sempre matar antes de relançar.
5. **sys.modules stale no Breadth Ultra:** Após editar módulos, reiniciar o servidor — reload parcial não funciona.
6. **print() com caracteres Unicode no Windows:** CP1252 não aceita box-drawing (║╔═). Usar ASCII puro nos prints de terminal.
7. **NG=F e ZW=F têm distorção de roll:** Contratos futuros contínuos do Yahoo Finance geram outliers de +62% por mês. Gás Natural usa FRED MHHNGSP (Henry Hub spot), Trigo usa FRED PWHEAMTUSDM (IMF Global Wheat). Ver `MacroDashboard/app/settings.py` → `FRED_TICKERS`.
8. **FRED CSV com parse_dates:** `pd.read_csv(url, parse_dates=['DATE'])` falha com "Missing column". Ler a resposta como texto e parsear manualmente por linha.
9. **CFTC COT — nome da coluna de data:** É `As_of_Date_In_Form_YYMMDD` (capital "I" em "In"), NÃO `As_of_Date_in_Form_YYMMDD`. Também: não existe `Asset_Mgr_Positions_Long_All` no Disaggregated Futures Only — usar `Prod_Merc_Positions_Long_All` (produtores/hedgers comerciais) como contraparte do Managed Money. Usar também `Report_Date_as_YYYY-MM-DD` como fallback para parsing de data.
10. **CFTC COT — arquivo do ano atual:** `fut_disagg_txt.zip` (genérico) retorna 404 mid-year. Usar `fut_disagg_txt_{year}.zip` para todos os anos, inclusive o ano corrente enquanto não terminar — apenas logar o 404 e continuar.
11. **CFTC COT — contrato certo = maior OI:** Quando há vários contratos com nome parecido, o correto é invariavelmente o de maior Open Interest. Sempre rodar script listando OI por contrato antes de investigar fórmula ou fonte. WTI: NYMEX (~2M OI) não ICE Europe (~700K OI). Gas Natural: NYMEX 023651 (~1,6M OI) não Henry Hub Penultimate (~125K OI). Modus operandi: suspeitar do contrato primeiro → fórmula depois → fonte por último.
12. **CFTC COT — WTI usa NYMEX:** Contrato = "CRUDE OIL, LIGHT SWEET - NEW YORK MERCANTILE EXCHANGE" (pré-2022) + "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE" (pós-2022). NÃO usar "CRUDE OIL, LIGHT SWEET-WTI - ICE FUTURES EUROPE" (ICE, menor OI, dados diferentes).
13. **Plotly hovertemplate com preços grandes:** NÃO usar `~g` ou `g` — gera "4.72e+3" para S&P 500 (~4700). Usar `,.2f` para preços (funciona para todos os ativos: Gas $2.77, Gold $2045.30, SP500 $4720.15, BTC $67250.00).
