import datetime
import json
import os
import secrets
import sqlite3
import uuid
from functools import wraps

from flask import Flask, g, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "portal.db")
SECRET_KEY_PATH = os.path.join(DATA_DIR, "secret_key.txt")

VALID_GROUPS = {"ATK-BR", "DEF-BR", "ATK-USA", "DEF-USA"}
VALID_SUBS = {"RF", "RV"}
DEFAULT_TARGETS = {"atk": 50, "br": 50, "rf": 50}
DEFAULT_REGIME = "Estagflação"


def get_secret_key():
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(SECRET_KEY_PATH):
        with open(SECRET_KEY_PATH, "w") as f:
            f.write(secrets.token_hex(32))
    with open(SECRET_KEY_PATH) as f:
        return f.read().strip()


app = Flask(__name__)
app.secret_key = get_secret_key()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            initials TEXT NOT NULL,
            created_at TEXT NOT NULL,
            hub_username TEXT UNIQUE
        );
        CREATE TABLE IF NOT EXISTS portfolios (
            client_id INTEGER PRIMARY KEY REFERENCES clients(id),
            state_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    # hub_username foi adicionado depois — em bancos ja existentes (criados
    # antes do 29/jul/2026) o CREATE TABLE IF NOT EXISTS acima nao adiciona a
    # coluna sozinho, precisa de ALTER TABLE. Guardado porque rodar duas
    # vezes quebra com "duplicate column".
    cols = {row[1] for row in db.execute("PRAGMA table_info(clients)").fetchall()}
    if "hub_username" not in cols:
        # SQLite nao permite UNIQUE direto em ADD COLUMN — indice unico
        # separado faz o mesmo papel (e ainda aceita varios NULL, que e o
        # caso normal pra cliente sem vinculo com usuario do Hub ainda).
        db.execute("ALTER TABLE clients ADD COLUMN hub_username TEXT")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_clients_hub_username ON clients(hub_username)")
    db.commit()
    db.close()


def make_asset(
    group, sub, name, tag, value,
    ticker=None, qtd=None, cotacao=None, preco_medio=None, tipo=None, desc=None,
    excluir_do_total=False, moeda=None,
):
    """ticker/qtd/cotacao/preco_medio sao opcionais — so ativos com posicao em
    bolsa (ticker+qtd) participam do refresh diario via Yahoo Finance (ver
    refresh_prices_from_yahoo). Ativos sem ticker (Tesouro Selic, caixa etc.)
    mantem "value" 100% manual, igual antes. excluir_do_total serve pra casos
    reais de inconsistencia de dados do cliente (ex.: posicao que a planilha
    original nao soma no patrimonio oficial) — aparece no card do ativo mas
    nao entra em compute_summary nem na matriz ALOC. moeda="USD" pra contas
    internacionais: cotacao/preco_medio ficam na moeda nativa (o JS calcula
    resultado/rentabilidade nessa moeda), mas "value" e sempre BRL convertido
    — e o unico jeito de somar corretamente no patrimonio/matriz ALOC."""
    return {
        "id": str(uuid.uuid4()), "group": group, "sub": sub, "name": name, "tag": tag, "value": float(value),
        "ticker": ticker, "qtd": qtd, "cotacao": cotacao, "preco_medio": preco_medio,
        "tipo": tipo, "desc": desc, "excluir_do_total": bool(excluir_do_total), "moeda": moeda,
    }


def make_special_position(ticker, nome, qtd, cotacao, desc, tipo="short"):
    """Posicoes fora do modelo normal de ativo (ex.: venda a descoberto sem
    preco medio de entrada conhecido) — aparecem na aba Ativos mas nunca
    entram na matriz ALOC nem no Patrimonio Total."""
    return {
        "id": str(uuid.uuid4()), "ticker": ticker, "nome": nome, "tipo": tipo,
        "qtd": qtd, "cotacao": cotacao, "desc": desc,
    }


def seed_client(
    username, password, display_name, initials, assets, hub_username=None,
    special_positions=None, pages=None,
):
    """Idempotent: does nothing if the username already exists. `pages` guarda
    conteudo redigido por assessor (nao editavel pela UI de add/remove ativo):
    diagnostico_executivo, macro_kpis, strengths, risks, diversif,
    recomendacoes, portfolio_compare, validation_points, strategy_html,
    tese_html — cada chave e opcional, aba correspondente vira placeholder
    se ausente."""
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    existing = db.execute("SELECT id FROM clients WHERE username=?", (username,)).fetchone()
    if existing is None:
        now = datetime.datetime.utcnow().isoformat()
        cur = db.execute(
            "INSERT INTO clients (username,password_hash,display_name,initials,created_at,hub_username) VALUES (?,?,?,?,?,?)",
            (username, generate_password_hash(password), display_name, initials, now, hub_username),
        )
        client_id = cur.lastrowid
        state = {
            "assets": assets,
            "targets": dict(DEFAULT_TARGETS),
            "regime": DEFAULT_REGIME,
            "special_positions": special_positions or [],
            "pages": pages or {},
        }
        db.execute(
            "INSERT INTO portfolios (client_id, state_json, updated_at) VALUES (?,?,?)",
            (client_id, json.dumps(state), now),
        )
        db.commit()
    db.close()


def fmt_brl(value):
    s = f"{value:,.2f}"
    s = s.replace(",", "X").replace(".", ",").replace("X", ".")
    return "R$ " + s


def fmt_pct(value):
    return f"{value:.1f}".replace(".", ",") + "%"


def compute_summary(assets):
    assets = [a for a in assets if not a.get("excluir_do_total")]
    total = sum(a["value"] for a in assets)

    def sum_where(pred):
        return sum(a["value"] for a in assets if pred(a))

    def pct(part):
        return (part / total * 100) if total else 0.0

    rf = sum_where(lambda a: a["sub"] == "RF")
    rv = sum_where(lambda a: a["sub"] == "RV")
    atk = sum_where(lambda a: a["group"].startswith("ATK"))
    dfn = sum_where(lambda a: a["group"].startswith("DEF"))
    groups = {gkey: sum_where(lambda a, gkey=gkey: a["group"] == gkey) for gkey in VALID_GROUPS}

    return {
        "total": total,
        "total_fmt": fmt_brl(total),
        "rf_fmt": fmt_brl(rf),
        "rf_pct_fmt": fmt_pct(pct(rf)),
        "rv_fmt": fmt_brl(rv),
        "rv_pct_fmt": fmt_pct(pct(rv)),
        "atk_pct_fmt": fmt_pct(pct(atk)),
        "def_pct_fmt": fmt_pct(pct(dfn)),
        "groups_fmt": {k: fmt_brl(v) for k, v in groups.items()},
    }


def get_csrf_token():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "client_id" not in session:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def _hub_username():
    # So chega preenchido quando a requisicao veio pelo proxy do Hub
    # (unified_server.py injeta esse header server-side, depois de remover
    # qualquer valor que o cliente tenha mandado — ver _IDENTITY_HEADERS la).
    # Acessando esse app direto (dev local, porta 8016) o header nunca existe,
    # entao cai no fluxo de login proprio abaixo.
    return request.headers.get("X-Hub-Username", "").strip()


def resolve_client(db):
    """Retorna (client_row_ou_None, veio_do_hub: bool)."""
    hub_username = _hub_username()
    if hub_username:
        row = db.execute("SELECT * FROM clients WHERE hub_username=?", (hub_username,)).fetchone()
        return row, True
    if "client_id" in session:
        row = db.execute("SELECT * FROM clients WHERE id=?", (session["client_id"],)).fetchone()
        return row, False
    return None, False


_NO_PORTFOLIO_HTML = """<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio — sem carteira vinculada</title>
<style>
  body{{background:#03060f;color:#e9edf7;font-family:system-ui,sans-serif;
    display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:20px;}}
  .box{{max-width:420px;text-align:center;}}
  h1{{font-size:18px;color:#f4d675;margin-bottom:10px;}}
  p{{font-size:14px;color:#aab3cf;line-height:1.6;}}
</style></head><body>
  <div class="box">
    <h1>Carteira ainda não vinculada</h1>
    <p>O usuário <b>{hub_username}</b> está logado no Hub, mas ainda não existe uma carteira associada a ele neste Portfolio.</p>
  </div>
</body></html>"""


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        if request.form.get("csrf_token") != session.get("csrf_token"):
            error = "Sessão expirada, tente novamente."
        else:
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            db = get_db()
            row = db.execute("SELECT * FROM clients WHERE username=?", (username,)).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                session.clear()
                session["client_id"] = row["id"]
                return redirect(url_for("dashboard"))
            error = "Usuário ou senha inválidos."
    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    db = get_db()
    client, via_hub = resolve_client(db)
    if client is None:
        if via_hub:
            return _NO_PORTFOLIO_HTML.format(hub_username=_hub_username()), 404
        return redirect(url_for("login", next=request.path))
    portfolio = db.execute("SELECT * FROM portfolios WHERE client_id=?", (client["id"],)).fetchone()
    state = json.loads(portfolio["state_json"])
    # Compat com carteiras criadas antes de special_positions/pages existirem.
    state.setdefault("special_positions", [])
    state.setdefault("pages", {})
    summary = compute_summary(state["assets"])
    return render_template(
        "dashboard.html",
        client=client,
        state=state,
        summary=summary,
        embedded=via_hub,
    )


@app.route("/api/portfolio", methods=["POST"])
def api_save_portfolio():
    db = get_db()
    client, via_hub = resolve_client(db)
    if client is None:
        return jsonify({"error": "not_found" if via_hub else "unauthorized"}), 404 if via_hub else 401

    payload = request.get_json(force=True, silent=True) or {}
    # CSRF token so faz sentido no fluxo de login proprio (cookie de sessao
    # deste app). Vindo pelo Hub, quem garante que a requisicao e legitima e
    # o cookie de sessao DO HUB (SameSite=Lax) — o _auth_gate do Hub ja
    # bloqueou antes de proxear se nao tivesse sessao valida la.
    if not via_hub and payload.get("csrf_token") != session.get("csrf_token"):
        return jsonify({"error": "csrf"}), 403

    raw_assets = payload.get("assets")
    if not isinstance(raw_assets, list) or len(raw_assets) > 500:
        return jsonify({"error": "assets inválido"}), 400

    def _opt_float(v):
        try:
            return None if v is None else float(v)
        except (TypeError, ValueError):
            return None

    def _opt_str(v, maxlen=120):
        return None if v is None else str(v)[:maxlen]

    clean_assets = []
    for a in raw_assets:
        if not isinstance(a, dict):
            return jsonify({"error": "ativo inválido"}), 400
        try:
            group = str(a["group"])
            sub = str(a["sub"])
            value = float(a["value"])
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "ativo inválido"}), 400
        if group not in VALID_GROUPS or sub not in VALID_SUBS or value < 0:
            return jsonify({"error": "ativo inválido"}), 400
        clean_assets.append(
            {
                "id": str(a.get("id") or uuid.uuid4()),
                "group": group,
                "sub": sub,
                "name": str(a.get("name", ""))[:80],
                "tag": str(a.get("tag") or "")[:80],
                "value": round(value, 2),
                # Campos de posicao em bolsa (opcionais) — preservados no
                # round-trip pra nao perder ticker/qtd ao editar valor manual
                # de outro ativo na mesma chamada (o front sempre manda o
                # array inteiro de volta, nao so o ativo alterado).
                "ticker": _opt_str(a.get("ticker"), 20),
                "qtd": _opt_float(a.get("qtd")),
                "cotacao": _opt_float(a.get("cotacao")),
                "preco_medio": _opt_float(a.get("preco_medio")),
                "tipo": _opt_str(a.get("tipo"), 40),
                "desc": _opt_str(a.get("desc"), 600),
                "excluir_do_total": bool(a.get("excluir_do_total")),
                "moeda": _opt_str(a.get("moeda"), 8),
            }
        )

    targets_in = payload.get("targets")
    targets = dict(DEFAULT_TARGETS)
    if isinstance(targets_in, dict):
        for k in ("atk", "br", "rf"):
            try:
                v = int(targets_in.get(k, targets[k]))
                targets[k] = min(100, max(0, v))
            except (TypeError, ValueError):
                pass

    regime = payload.get("regime")
    if not isinstance(regime, str) or not regime:
        regime = DEFAULT_REGIME

    # special_positions e pages sao conteudo redigido pelo assessor, nao
    # editavel pela UI de add/remove ativo — preserva o que ja esta salvo em
    # vez de aceitar do payload (o front nem manda essas chaves de volta).
    current = db.execute("SELECT state_json FROM portfolios WHERE client_id=?", (client["id"],)).fetchone()
    current_state = json.loads(current["state_json"]) if current else {}

    state = {
        "assets": clean_assets,
        "targets": targets,
        "regime": regime,
        "special_positions": current_state.get("special_positions", []),
        "pages": current_state.get("pages", {}),
    }
    db.execute(
        "UPDATE portfolios SET state_json=?, updated_at=? WHERE client_id=?",
        (json.dumps(state), datetime.datetime.utcnow().isoformat(), client["id"]),
    )
    db.commit()
    return jsonify({"ok": True, "summary": compute_summary(clean_assets)})


def refresh_prices_from_yahoo():
    """Roda apos o fechamento da B3: busca a cotacao de fechamento mais
    recente via Yahoo Finance pra todo ativo com ticker+qtd cadastrado, e
    recalcula "value" (qtd * cotacao). Resultado/rentabilidade sao sempre
    calculados no JS a partir de qtd/cotacao/preco_medio no momento da
    renderizacao (nao ficam persistidos, pra nao correrem o risco de ficar
    dessincronizados da cotacao). Ativos sem ticker (Tesouro Selic, caixa
    etc.) ficam intocados — "value" continua 100% manual pra esses."""
    import yfinance as yf

    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    clients = db.execute("SELECT id FROM clients").fetchall()

    states = {}
    tickers = set()
    for c in clients:
        row = db.execute("SELECT state_json FROM portfolios WHERE client_id=?", (c["id"],)).fetchone()
        if not row:
            continue
        state = json.loads(row["state_json"])
        states[c["id"]] = state
        for a in state.get("assets", []):
            if a.get("ticker") and a.get("qtd") is not None:
                tickers.add(a["ticker"])
        for sp in state.get("special_positions", []):
            if sp.get("ticker"):
                tickers.add(sp["ticker"])

    if not tickers:
        db.close()
        return {"updated_clients": 0, "quotes": 0}

    def yahoo_symbol(tk):
        # Convencao B3: ticker termina em digito (PETR4, INBR32, QBTC11...).
        # Tickers americanos (MSFT, AAPL) sao so letras — nao levam ".SA".
        return tk + ".SA" if tk[-1].isdigit() else tk

    quotes = {}
    for tk in tickers:
        try:
            hist = yf.Ticker(yahoo_symbol(tk)).history(period="5d")
            closes = hist["Close"].dropna()
            if len(closes):
                quotes[tk] = float(closes.iloc[-1])
        except Exception:
            continue

    # So busca USDBRL se algum ativo com moeda="USD" realmente precisar —
    # cotacao/preco_medio desses ficam na moeda nativa (USD), so "value"
    # (usado em todo total/matriz ALOC) precisa do cambio pra virar BRL.
    needs_usdbrl = any(
        a.get("moeda") == "USD" and a.get("ticker") and a.get("qtd") is not None
        for state in states.values() for a in state.get("assets", [])
    )
    usdbrl = None
    if needs_usdbrl:
        try:
            hist = yf.Ticker("BRL=X").history(period="5d")
            closes = hist["Close"].dropna()
            if len(closes):
                usdbrl = float(closes.iloc[-1])
        except Exception:
            usdbrl = None

    now = datetime.datetime.utcnow().isoformat()
    updated_clients = 0
    for client_id, state in states.items():
        changed = False
        for a in state.get("assets", []):
            tk = a.get("ticker")
            if tk and a.get("qtd") is not None and tk in quotes:
                a["cotacao"] = quotes[tk]
                if a.get("moeda") == "USD":
                    if usdbrl is not None:
                        a["value"] = round(a["qtd"] * quotes[tk] * usdbrl, 2)
                        changed = True
                    # sem taxa de cambio disponivel: mantem cotacao nova mas
                    # nao mexe em "value" (evita salvar total errado)
                else:
                    a["value"] = round(a["qtd"] * quotes[tk], 2)
                    changed = True
        for sp in state.get("special_positions", []):
            tk = sp.get("ticker")
            if tk and tk in quotes:
                sp["cotacao"] = quotes[tk]
                changed = True
        if changed:
            state["prices_updated_at"] = now
            db.execute(
                "UPDATE portfolios SET state_json=?, updated_at=? WHERE client_id=?",
                (json.dumps(state), now, client_id),
            )
            updated_clients += 1

    db.commit()
    db.close()
    return {"updated_clients": updated_clients, "quotes": len(quotes)}


@app.cli.command("refresh-prices")
def refresh_prices_cmd():
    """Dispara manualmente o refresh de cotacoes via Yahoo Finance.
    Uso: flask --app server refresh-prices"""
    result = refresh_prices_from_yahoo()
    print(f"OK: {result['updated_clients']} cliente(s) atualizado(s), {result['quotes']} cotação(ões) buscada(s).")


@app.cli.command("add-client")
def add_client_cmd():
    """Interactive helper: flask --app server add-client"""
    import getpass

    username = input("username: ").strip().lower()
    password = getpass.getpass("senha: ")
    display_name = input("nome do cliente: ").strip()
    initials = "".join(w[0] for w in display_name.split()[:2]).upper() or "XX"

    assets = []
    print("Cadastrar ativos (Enter em branco no nome para terminar).")
    print("Grupos válidos: ATK-BR, DEF-BR, ATK-USA, DEF-USA | Sub: RF, RV")
    while True:
        name = input("  nome do ativo: ").strip()
        if not name:
            break
        group = input("  grupo (ATK-BR/DEF-BR/ATK-USA/DEF-USA): ").strip().upper()
        sub = input("  sub (RF/RV): ").strip().upper()
        tag = input("  tag (opcional): ").strip()
        value = float(input("  valor (R$): ").strip().replace(",", "."))
        if group in VALID_GROUPS and sub in VALID_SUBS:
            assets.append(make_asset(group, sub, name, tag, value))
        else:
            print("  grupo/sub inválido, ativo ignorado.")

    seed_client(username, password, display_name, initials, assets)
    print(f"Cliente '{display_name}' ({username}) cadastrado.")


@app.cli.command("link-hub-user")
def link_hub_user_cmd():
    """Vincula um cliente ja cadastrado aqui a um usuario de login do Hub
    (macrodesk). Depois disso, esse usuario ve a carteira automaticamente
    ao clicar na aba Portfolio do Hub, sem precisar logar de novo aqui.
    Uso: flask --app server link-hub-user"""
    username = input("username deste app (carteira_portal): ").strip().lower()
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    client = db.execute("SELECT * FROM clients WHERE username=?", (username,)).fetchone()
    if client is None:
        print(f"Nenhum cliente com username '{username}' encontrado.")
        db.close()
        return
    hub_username = input("username de login no Hub (macrodesk): ").strip().lower()
    db.execute("UPDATE clients SET hub_username=? WHERE id=?", (hub_username, client["id"]))
    db.commit()
    db.close()
    print(f"OK: usuário do Hub '{hub_username}' agora vê a carteira de '{client['display_name']}'.")


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORTFOLIO_PORT", 8016))
    # debug=True liga o debugger interativo do Werkzeug (RCE se exposto) —
    # default seguro é desligado; ligar so localmente via PORTFOLIO_DEBUG=1.
    debug = os.environ.get("PORTFOLIO_DEBUG", "0") == "1"

    # Guard do reloader: em debug, Werkzeug reinicia o processo e roda este
    # bloco de novo — sem o guard o scheduler seria registrado 2x. B3 fecha
    # 18:00 BRT; 18:35 da folga pro fechamento assentar antes de buscar.
    if not debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        try:
            from apscheduler.schedulers.background import BackgroundScheduler

            sched = BackgroundScheduler(timezone="America/Sao_Paulo")
            sched.add_job(
                refresh_prices_from_yahoo, "cron",
                day_of_week="mon-fri", hour=18, minute=35, id="portfolio_eod_prices",
            )
            sched.start()
            print("  Scheduler configurado: cotações via Yahoo Finance seg-sex 18:35 BRT")
        except Exception as e:
            print(f"  APScheduler não disponível: {e}")

    app.run(host="127.0.0.1", port=port, debug=debug)
