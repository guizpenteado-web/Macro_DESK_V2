# Checklist — Migração do ngrok para domínio pago próprio

Criado em 06/07/2026. Use isso quando o domínio novo estiver contratado.

## 1. Arquivos que citam o domínio ngrok atual e precisam ser atualizados

| Arquivo | O que muda |
|---|---|
| `start_hub.bat` (linha `--domain=jawed-sermon-extras.ngrok-free.dev`) | Trocar para o novo domínio, ou remover o ngrok inteiramente se for expor via IP fixo/roteador + DNS direto |
| `CLAUDE.md` (seção "URL pública") | Atualizar o link documentado |
| **Artifact do claude.ai** (`analises_v3.html`, `const API_BASE = 'https://jawed-sermon-extras.ngrok-free.dev'`) | **Crítico** — sem isso, a versão hospedada no claude.ai para de falar com o backend. Redeploy via `Artifact` tool com a nova URL |
| `biblioteca/index.html` (comentário na linha ~571) | Cosmético — usa `API_BASE` vazio (relativo), não quebra, mas o comentário cita ngrok |

## 2. Decisões de infraestrutura antes de trocar

- **HTTPS**: o domínio pago precisa de certificado (Let's Encrypt via Certbot, ou Cloudflare proxy com SSL automático). O ngrok já dava HTTPS de graça — não perder isso na troca.
- **Onde aponta o DNS**: registro A/AAAA para o IP público de casa (exige IP fixo ou DDNS) OU continuar usando um túnel (ngrok pago com domínio custom, Cloudflare Tunnel, Tailscale Funnel) — mais simples que abrir porta no roteador.
- **Se abrir porta no roteador**: fica exposto ao mundo sem a camada extra que o ngrok oferece hoje. Vale revisar firewall do Windows e considerar um reverse proxy (Caddy/Nginx) na frente do `unified_server.py` em vez de expor a porta 8000 direto.

## 3. Segurança — pontos já verificados (06/07/2026)

- ✅ CORS `allow_origins=["*"]` no `unified_server.py` — decisão deliberada e documentada no próprio código (servidor pessoal, sem dado sensível de terceiros). `allow_credentials` não está ativado, então não há risco de CSRF via cookie.
- ✅ Escrita na Biblioteca exige `X-Api-Key` (401 sem a chave) — testado local e via ngrok público, funcionando nos dois.
- ✅ Nenhum `debug=True` / reload ligado em nenhum dos servidores (`unified_server.py`, `MacroDashboard/server.py`, `Market_BREADTH_ULTRA/server.py`, `IbovCalls/server.py`) — importante porque debug mode do Flask/FastAPI exposto publicamente permite RCE via console interativo.
- ✅ Repositório GitHub `Macro_DESK_V2` é **público** — nenhum segredo encontrado no histórico rastreado (chave da Biblioteca é gerada em runtime e fica fora do git via `.gitignore`).
- ⚠️ **Pendente (decisão do usuário, adiada em 06/07)**: dados reais da Biblioteca (SQLite + mídias, ~13MB) só existem neste PC, sem backup externo. Revisitar quando for mexer no domínio.
- ⚠️ Considerar: se o site vai ficar "de verdade" público num domínio memorável (em vez de uma URL ngrok obscura), reavaliar se a leitura sem senha da Biblioteca (decisão consciente anterior) ainda é aceitável — antes só quem tivesse o link aleatório do ngrok via ou o encontrasse.

## 4. Depois de trocar — reteste

Repetir os testes end-to-end feitos em 06/07/2026:
- `GET /` nas portas 8000/8010/8011/8012/8013 → HTTP 200
- Proxy do Hub: `/intermarket`, `/breadth`, `/macro`, `/ibov`, `/biblioteca` → HTTP 200
- `POST /api/biblioteca/posts` sem `X-Api-Key` → deve continuar dando 401
- Link público novo (substituindo o ngrok) → HTTP 200 na raiz e nas rotas acima
