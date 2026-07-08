"""
Macro Desk — servidor unificado.

Sobe os três projetos em portas internas e serve um shell de navegacao na porta 8000.
Proxy reverso integrado: tudo passa pela porta 8000 (compativel com ngrok/Tailscale/URL publica).

  http://<host>:8000              -> shell com botoes de navegacao
  http://<host>:8000/intermarket/ -> Intermarket Dashboard (proxy -> :8010)
  http://<host>:8000/breadth/     -> Market_BREADTH_ULTRA  (proxy -> :8011)
  http://<host>:8000/macro/       -> Macro Dashboard        (proxy -> :8012)
"""
from __future__ import annotations
import asyncio
import atexit
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

import re
import json
import concurrent.futures
import httpx
import uvicorn
import yfinance as yf
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from bs4 import BeautifulSoup

BASE          = Path(__file__).resolve().parent
DASHBOARD_DIR = BASE / "dashboard"
BIBLIOTECA_DIR = BASE / "biblioteca"
# Módulos do Macro Desk Principal — desde 07/07/2026 vivem dentro deste mesmo
# repositório (git subtree), não mais em pastas irmãs separadas em Documents.
BREADTH_DIR   = BASE / "Market_BREADTH_ULTRA"
MACRO_DIR     = BASE / "MacroDashboard"
IBOV_DIR      = BASE / "IbovCalls"


PYTHON_1 = str(DASHBOARD_DIR / ".venv" / "Scripts" / "python.exe")
PYTHON_2 = str(BREADTH_DIR   / ".venv" / "Scripts" / "python.exe")
PYTHON_3 = str(MACRO_DIR     / ".venv" / "Scripts" / "python.exe")
PYTHON_4 = str(IBOV_DIR      / ".venv" / "Scripts" / "python.exe")

PORT_SHELL       = 8000
PORT_INTERMARKET = 8010
PORT_BREADTH     = 8011
PORT_MACRO       = 8012
PORT_IBOV        = 8013

_procs: list[subprocess.Popen] = []

# Descrição de cada sub-servidor para o watchdog poder reiniciá-los
_SUBSERVER_SPECS: list[dict] = []


def _make_popen(spec: dict) -> subprocess.Popen:
    kwargs: dict = {"cwd": spec["cwd"]}
    if spec.get("env"):
        kwargs["env"] = spec["env"]
    return subprocess.Popen(spec["cmd"], **kwargs)


def _start_subservers() -> None:
    global _SUBSERVER_SPECS
    _SUBSERVER_SPECS = [
        {
            "name": "Intermarket",
            "port": PORT_INTERMARKET,
            "cmd":  [PYTHON_1, "-m", "uvicorn", "main:app",
                     "--host", "127.0.0.1", "--port", str(PORT_INTERMARKET), "--log-level", "warning"],
            "cwd":  str(DASHBOARD_DIR),
        },
        {
            "name": "Breadth",
            "port": PORT_BREADTH,
            "cmd":  [PYTHON_2, "-m", "uvicorn", "server:app",
                     "--host", "127.0.0.1", "--port", str(PORT_BREADTH), "--log-level", "warning"],
            "cwd":  str(BREADTH_DIR),
        },
        {
            "name": "Macro",
            "port": PORT_MACRO,
            "cmd":  [PYTHON_3, "-m", "uvicorn", "server:app",
                     "--host", "127.0.0.1", "--port", str(PORT_MACRO), "--log-level", "warning"],
            "cwd":  str(MACRO_DIR),
        },
        {
            "name": "IbovCalls",
            "port": PORT_IBOV,
            "cmd":  [PYTHON_4, "server.py"],
            "cwd":  str(IBOV_DIR),
            "env":  {**__import__("os").environ, "PORT": str(PORT_IBOV)},
        },
    ]

    for spec in _SUBSERVER_SPECS:
        p = _make_popen(spec)
        spec["proc"] = p
        _procs.append(p)

    atexit.register(lambda: [p.terminate() for p in _procs if p.poll() is None])
    print("  Aguardando sub-servidores iniciarem...", flush=True)
    time.sleep(4)


def _watchdog_loop() -> None:
    """Reinicia sub-servidores que morreram inesperadamente."""
    while True:
        time.sleep(30)
        for spec in _SUBSERVER_SPECS:
            proc: subprocess.Popen = spec.get("proc")
            if proc is None:
                continue
            if proc.poll() is not None:  # processo morreu
                print(f"  [watchdog] {spec['name']} (porta {spec['port']}) caiu — reiniciando...", flush=True)
                try:
                    new_proc = _make_popen(spec)
                    spec["proc"] = new_proc
                    print(f"  [watchdog] {spec['name']} reiniciado (PID {new_proc.pid})", flush=True)
                except Exception as exc:
                    print(f"  [watchdog] Falha ao reiniciar {spec['name']}: {exc}", flush=True)


# ── News RSS ─────────────────────────────────────────────────────────────────

RSS_SOURCES: dict[str, list[tuple[str, str]]] = {
    "calls": [
        ("InfMoney Análises", "https://www.infomoney.com.br/analises/feed/"),
        ("Suno Análises",     "https://www.suno.com.br/artigos/feed/"),
        ("Exame Invest",      "https://exame.com/invest/feed/"),
    ],
    "brasil": [
        ("Infomoney",     "https://www.infomoney.com.br/feed/"),
        ("Valor Econ.",   "https://valor.globo.com/rss/valor-economico/index.xml"),
        ("Exame",         "https://exame.com/invest/feed/"),
        ("MoneyTimes",    "https://moneytimes.com.br/feed/"),
        ("Suno Research", "https://www.suno.com.br/noticias/feed/"),
        ("Estadão Econ.", "https://economia.estadao.com.br/rss.xml"),
        ("Investing BR",  "https://br.investing.com/rss/news.rss"),
    ],
    "global": [
        ("Reuters",       "https://feeds.reuters.com/reuters/businessNews"),
        ("Bloomberg",     "https://feeds.bloomberg.com/markets/news.rss"),
        ("CNBC",          "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("MarketWatch",   "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines"),
        ("Yahoo Finance", "https://finance.yahoo.com/rss/topstories"),
        ("Reuters World", "https://feeds.reuters.com/reuters/worldNews"),
        ("CNBC Stocks",   "https://www.cnbc.com/id/15839135/device/rss/rss.html"),
        ("TheStreet",     "https://www.thestreet.com/rss/main.xml"),
        ("Investopedia",  "https://www.investopedia.com/feedbuilder/feed/getfeed/?feedName=rss_articles"),
        ("InfMoney Ações","https://www.infomoney.com.br/mercados/acoes/feed/"),
    ],
}
_news_cache: dict[str, dict] = {}
_NEWS_TTL = 900  # 15 min


def _fix_enc(s: str) -> str:
    """Corrige mojibake UTF-8 interpretado como Latin-1 (comum em RSS brasileiros)."""
    try:
        return s.encode("latin-1").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return s


async def _fetch_rss(source: str, url: str) -> list[dict]:
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True,
                                     headers={"User-Agent": "Mozilla/5.0"}) as cl:
            r = await cl.get(url)
            r.raise_for_status()
        root = ET.fromstring(r.content)
        out = []
        for item in root.findall(".//item")[:12]:
            title = _fix_enc((item.findtext("title") or "").strip())
            link  = (item.findtext("link")  or "").strip()
            pub   = (item.findtext("pubDate") or "")
            if title and link:
                out.append({"source": source, "title": title, "link": link, "pub": pub})
        return out
    except Exception:
        return []


def _sort_key(x: dict) -> float:
    try:
        return parsedate_to_datetime(x["pub"]).timestamp()
    except Exception:
        return 0.0


# ── Shell HTML ────────────────────────────────────────────────────────────────

_SHELL = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Macro Desk</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:       #0d1117;
    --nav-h:    52px;
    --ticker-w: 200px;
    --c1:       #00BFFF;
    --c2:       #c9a227;
    --c3:       #a78bfa;
    --c4:       #34d399;
    --c5:       #f472b6;
    --text:     #e6edf3;
    --muted:    #8b949e;
    --border:   #21262d;
    --btn-bg:   #161b22;
    --btn-hover:#1f2937;
  }

  html, body {
    height: 100%;
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    overflow: hidden;
  }

  /* ── Nav bar ── */
  nav {
    position: fixed; top: 0; left: 0; right: 0;
    height: var(--nav-h);
    background: #161b22;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    padding: 0 20px;
    gap: 10px;
    z-index: 100;
  }

  .hub-logo {
    font-size: 21px;
    font-weight: 700;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--muted);
    margin-right: 16px;
    white-space: nowrap;
  }
  .hub-logo span { color: var(--text); }

  .divider {
    width: 1px; height: 24px;
    background: var(--border);
    margin: 0 6px;
  }

  .nav-btn {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 7px 16px;
    border-radius: 8px;
    border: 1px solid transparent;
    background: transparent;
    color: var(--muted);
    font-size: 13px;
    font-weight: 500;
    cursor: pointer;
    transition: all .15s;
    white-space: nowrap;
    letter-spacing: .2px;
  }
  .nav-btn .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: currentColor;
    opacity: .4;
    transition: opacity .15s;
  }
  .nav-btn:hover {
    background: var(--btn-hover);
    color: var(--text);
  }
  .nav-btn.active-1 {
    border-color: var(--c1);
    color: var(--c1);
    background: rgba(0,191,255,.08);
  }
  .nav-btn.active-1 .dot { opacity: 1; }
  .nav-btn.active-2 {
    border-color: var(--c2);
    color: var(--c2);
    background: rgba(167,139,250,.08);
  }
  .nav-btn.active-2 .dot { opacity: 1; }
  .nav-btn.active-3 {
    border-color: var(--c3);
    color: var(--c3);
    background: rgba(201,162,39,.08);
  }
  .nav-btn.active-3 .dot { opacity: 1; }
  .nav-btn.active-4 {
    border-color: var(--c4);
    color: var(--c4);
    background: rgba(52,211,153,.08);
  }
  .nav-btn.active-4 .dot { opacity: 1; }
  .nav-btn.active-8 {
    border-color: var(--c5);
    color: var(--c5);
    background: rgba(244,114,182,.08);
  }
  .nav-btn.active-8 .dot { opacity: 1; }
  .nav-btn.active-5 { border-color: #6e7681; color: #d1d4dc; background: rgba(110,118,129,.12); }
  .nav-btn.active-6 { border-color: #6e7681; color: #d1d4dc; background: rgba(110,118,129,.12); }
  .nav-btn.active-7 { border-color: #6e7681; color: #d1d4dc; background: rgba(110,118,129,.12); }

  /* ── Ticker Panel — oculto por padrão, toggled via botão Overview ── */
  .ticker-hidden .ticker-panel,
  .ticker-hidden #tq-sep { display: none; }
  .ticker-hidden .frame-wrap { right: 0; }
  /* posicionamento controlado via JS _syncPanels() */

  /* call badge */
  .call-badge {
    position: absolute; top: 4px; right: 4px;
    background: #ef4444; color: #fff;
    font-size: 9px; font-weight: 700; line-height: 1;
    min-width: 14px; height: 14px;
    border-radius: 7px; padding: 0 3px;
    display: flex; align-items: center; justify-content: center;
  }
  .nav-btn { position: relative; }

  /* ── iframes ── */
  .frame-wrap {
    position: fixed;
    top: var(--nav-h); left: 0; right: var(--ticker-w); bottom: 0;
  }

  iframe {
    width: 100%; height: 100%;
    border: none;
    display: none;
    background: var(--bg);
  }
  iframe.visible { display: block; }

  /* loading overlay */
  .loader {
    position: absolute; inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 14px;
    background: var(--bg);
    color: var(--muted);
    font-size: 13px;
  }
  .spinner {
    width: 32px; height: 32px;
    border: 3px solid var(--border);
    border-top-color: var(--c1);
    border-radius: 50%;
    animation: spin .7s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .loader.hidden { display: none; }

  /* ── News Panel ── */
  #news-panel {
    position: fixed;
    top: var(--nav-h); right: -370px; bottom: 0;
    width: 365px;
    background: #0d1117;
    border-left: 1px solid var(--border);
    z-index: 201;
    transition: right .25s ease;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  /* posicionamento controlado via JS _syncPanels() */

  .news-hdr {
    display: flex; align-items: center; justify-content: space-between;
    padding: 11px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 13px; font-weight: 600; color: var(--text);
    flex-shrink: 0;
  }
  .news-close {
    background: none; border: none; color: var(--muted);
    cursor: pointer; font-size: 15px; padding: 2px 6px; border-radius: 4px;
  }
  .news-close:hover { background: var(--btn-hover); color: var(--text); }

  .news-tabs {
    display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .ntab {
    flex: 1; padding: 8px 2px;
    background: none; border: none; color: var(--muted);
    font-size: 11px; cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all .12s;
  }
  .ntab:hover { color: var(--text); background: var(--btn-hover); }
  .ntab.active { color: #58a6ff; border-bottom-color: #58a6ff; }

  #news-list {
    flex: 1; overflow-y: auto; padding: 4px 0;
  }
  #news-list::-webkit-scrollbar { width: 3px; }
  #news-list::-webkit-scrollbar-track { background: transparent; }
  #news-list::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }

  .news-item { padding: 9px 14px; border-bottom: 1px solid #161b22; }
  .news-item:hover { background: #161b22; }
  .news-item a { text-decoration: none; color: inherit; display: block; }
  .news-meta { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
  .news-src { font-size: 10px; font-weight: 700; color: #58a6ff; text-transform: uppercase; letter-spacing: .04em; }
  .news-time { font-size: 10px; color: #484f58; }
  .news-title { font-size: 12px; color: #c9d1d9; line-height: 1.45;
    display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .news-empty { padding: 24px; color: #484f58; font-size: 12px; text-align: center; }
  .call-bank { color: #f59e0b !important; }
  .call-summary { font-size: 10px; color: #484f58; margin-top: 3px; line-height: 1.4; }
  .call-new-badge { font-size: 8px; background: #ef4444; color: #fff; border-radius: 3px; padding: 1px 4px; font-weight: 700; }
  .news-item.call-new { border-left: 2px solid #ef4444 !important; }

  .news-refresh {
    flex-shrink: 0; padding: 6px 14px;
    border-top: 1px solid var(--border);
    font-size: 10px; color: #484f58; text-align: right;
  }
  .news-refresh span { cursor: pointer; color: #58a6ff; }
  .news-refresh span:hover { text-decoration: underline; }

  /* ── Calendar Panel ── */
  #cal-panel {
    position: fixed;
    top: var(--nav-h); right: -420px; bottom: 0;
    width: 415px;
    background: #0d1117;
    border-left: 1px solid var(--border);
    z-index: 200;
    transition: right .25s ease;
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  /* posicionamento controlado via JS _syncPanels() */

  .cal-hdr {
    display: flex; align-items: center; justify-content: space-between;
    padding: 11px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 13px; font-weight: 600; color: var(--text);
    flex-shrink: 0;
    background: linear-gradient(90deg, rgba(88,166,255,.06) 0%, transparent 100%);
  }
  .cal-close {
    background: none; border: none; color: var(--muted);
    cursor: pointer; font-size: 15px; padding: 2px 6px; border-radius: 4px;
  }
  .cal-close:hover { background: var(--btn-hover); color: var(--text); }

  .cal-days {
    display: flex; border-bottom: 1px solid var(--border); flex-shrink: 0;
  }
  .cdtab {
    flex: 1; padding: 8px 2px;
    background: none; border: none; color: var(--muted);
    font-size: 11px; cursor: pointer;
    border-bottom: 2px solid transparent;
    transition: all .12s;
  }
  .cdtab:hover { color: var(--text); background: var(--btn-hover); }
  .cdtab.active { color: #58a6ff; border-bottom-color: #58a6ff; }

  #cal-list {
    flex: 1; overflow-y: auto; padding: 0;
  }
  #cal-list::-webkit-scrollbar { width: 3px; }
  #cal-list::-webkit-scrollbar-track { background: transparent; }
  #cal-list::-webkit-scrollbar-thumb { background: #30363d; border-radius: 2px; }

  .cal-date-hdr {
    padding: 6px 14px 4px;
    font-size: 11px; font-weight: 700; letter-spacing: .06em;
    color: #484f58; text-transform: uppercase;
    background: #0d1117;
    position: sticky; top: 0; z-index: 5;
    border-bottom: 1px solid #161b22;
  }
  .cal-event {
    display: grid;
    grid-template-columns: 44px 36px 22px 1fr 62px 62px 62px;
    gap: 0 6px;
    align-items: center;
    padding: 7px 10px;
    border-bottom: 1px solid #161b22;
    font-size: 13px;
    transition: background .1s;
  }
  .cal-event:hover { background: #161b22; }
  .cal-time { color: #8b949e; font-size: 12px; font-variant-numeric: tabular-nums; }
  .cal-curr { font-size: 16px; line-height: 1; }
  .cal-imp {
    display: flex; gap: 1px; align-items: center;
  }
  .cal-dot { width: 5px; height: 5px; border-radius: 50%; }
  .cal-dot.H { background: #ef5350; }
  .cal-dot.M { background: #f59e0b; }
  .cal-dot.L { background: #30363d; }
  .cal-name { color: #c9d1d9; line-height: 1.35;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
  }
  .cal-val { text-align: right; color: #8b949e; font-size: 12px; font-variant-numeric: tabular-nums; }
  .cal-val.actual { color: #26a69a; font-weight: 700; }
  .cal-val.actual.miss { color: #ef5350; }
  .cal-val-hdr {
    display: grid;
    grid-template-columns: 44px 36px 22px 1fr 62px 62px 62px;
    gap: 0 6px;
    padding: 4px 10px;
    border-bottom: 1px solid #21262d;
    font-size: 9px; font-weight: 600; letter-spacing: .04em;
    color: #484f58; text-transform: uppercase;
    flex-shrink: 0;
  }
  .cal-val-hdr span:nth-child(n+5) { text-align: right; }
  .cal-empty { padding: 32px; color: #484f58; font-size: 12px; text-align: center; }
  .cal-loading { padding: 32px; text-align: center; color: #484f58; font-size: 12px; }

  /* ── Ticker Panel — TradingView style ── */
  .ticker-panel {
    position: fixed;
    top: var(--nav-h); right: 0; bottom: 0;
    width: var(--ticker-w);
    background: #131722;
    z-index: 150;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Trebuchet MS", "Segoe UI", sans-serif;
    border-left: none;
  }
  .tq-hdr {
    padding: 8px 10px 6px;
    display: flex; align-items: center; justify-content: space-between;
    border-bottom: 1px solid #2a2e39;
    flex-shrink: 0;
    background: #1a1d2e;
  }
  .tq-title {
    font-size: 9px; font-weight: 700; letter-spacing: 1.4px;
    text-transform: uppercase; color: #434651;
  }
  .tq-live {
    width: 5px; height: 5px; border-radius: 50%;
    background: #26a69a; box-shadow: 0 0 5px #26a69a;
  }
  .tq-body { flex: 1; overflow-y: auto; overflow-x: hidden; scrollbar-width: thin; scrollbar-color: #2a2e39 transparent; }
  .tq-body::-webkit-scrollbar { width: 2px; }
  .tq-body::-webkit-scrollbar-track { background: transparent; }
  .tq-body::-webkit-scrollbar-thumb { background: #2a2e39; border-radius: 10px; }
  .tq-body::-webkit-scrollbar-thumb:hover { background: #434651; }
  .tq-gh {
    padding: 7px 10px 5px;
    font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.8px;
    color: #434651;
    background: #1a1d2e;
    border-bottom: 1px solid #2a2e39;
  }
  .tq-gh:not(:first-child) { border-top: 1px solid #2a2e39; }
  .tq-row {
    display: flex; align-items: center;
    padding: 5px 10px 5px 8px;
    border-bottom: 1px solid #1e222d;
    gap: 7px; cursor: default;
    transition: background .1s;
  }
  .tq-row:hover { background: #1e222d; }
  .tq-dot {
    width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
  }
  .tq-sym {
    flex: 1; font-size: 13px; font-weight: 700; color: #d1d4dc;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    letter-spacing: .1px;
  }
  .tq-vals {
    display: flex; flex-direction: column; align-items: flex-end; flex-shrink: 0;
  }
  .tq-price { font-size: 13px; color: #d1d4dc; font-weight: 400; white-space: nowrap; }
  .tq-pct   { font-size: 11px; font-weight: 700; white-space: nowrap; }
  .tq-pct.up   { color: #26a69a; }
  .tq-pct.dn   { color: #ef5350; }
  .tq-pct.flat { color: #434651; }
  .tq-ft {
    padding: 5px 10px;
    border-top: 1px solid #2a2e39;
    font-size: 9.5px; color: #434651;
    display: flex; align-items: center; justify-content: space-between;
    flex-shrink: 0; background: #1a1d2e;
  }
  .tq-rb { cursor: pointer; color: #2962ff; background: none; border: none;
    font-size: 11px; padding: 0; line-height: 1; }
  .tq-rb:hover { color: #5c85ff; }
  /* Overlay que cobre o scrollbar cinza do iframe e cria o separador azul */
  #tq-sep {
    position: fixed;
    top: var(--nav-h); bottom: 0;
    right: var(--ticker-w);
    width: 18px;
    background: var(--bg);
    border-right: 2px solid #1e3d6e;
    z-index: 149;
    pointer-events: none;
  }
</style>
</head>
<body>

<nav>
  <div class="hub-logo">&#9670; <span>Macro Desk</span></div>
  <div class="divider"></div>

  <button class="nav-btn active-1" id="btn1" onclick="show(1)">
    <span class="dot"></span>
    IBOV Calls
    <span class="call-badge" id="call-badge" style="display:none"></span>
  </button>

  <button class="nav-btn" id="btn2" onclick="show(2)">
    <span class="dot"></span>
    Intermarket
  </button>

  <button class="nav-btn" id="btn3" onclick="show(3)">
    <span class="dot"></span>
    Macro Dashboard
  </button>

  <button class="nav-btn" id="btn4" onclick="show(4)">
    <span class="dot"></span>
    Market Breadth
  </button>

  <button class="nav-btn" id="btn5" onclick="show(5)">
    <span class="dot"></span>
    Biblioteca
    <span class="call-badge" id="biblio-badge" style="display:none"></span>
  </button>

  <button class="nav-btn" id="btn-news" onclick="toggleNews()" style="margin-left:auto">
    <span style="font-size:14px">📰</span>
    Notícias
  </button>
  <button class="nav-btn" id="btn-cal" onclick="toggleCal()">
    <span style="font-size:13px">📅</span>
    Calendário
  </button>
  <button class="nav-btn" id="btn-overview" onclick="toggleOverview()">
    <span style="font-size:13px">◫</span>
    Overview
  </button>
</nav>

<!-- ── News Panel ── -->
<div id="news-panel">
  <div class="news-hdr">
    <span>📰 Notícias &amp; Calls</span>
    <button class="news-close" onclick="toggleNews()">✕</button>
  </div>
  <div class="news-tabs">
    <button class="ntab active" id="ntab-calls"  onclick="loadNews('calls',this)">🏦 Calls</button>
    <button class="ntab"        id="ntab-brasil" onclick="loadNews('brasil',this)">🇧🇷 Brasil</button>
    <button class="ntab"        id="ntab-global" onclick="loadNews('global',this)">🌐 Global</button>
  </div>
  <div id="news-list"><div class="news-empty">Clique em uma aba para carregar.</div></div>
  <div class="news-refresh" id="news-refresh-bar" style="display:none">
    Atualizado há <span id="news-age">0</span>s &nbsp;|&nbsp; <span onclick="forceReloadNews()">↻ Atualizar</span>
  </div>
</div>

<!-- ── Calendar Panel ── -->
<div id="cal-panel">
  <div class="cal-hdr">
    <span>📅 Calendário Econômico</span>
    <button class="cal-close" onclick="toggleCal()">✕</button>
  </div>
  <div class="cal-days">
    <button class="cdtab active" onclick="calLoad(3,this)">3 dias</button>
    <button class="cdtab" onclick="calLoad(7,this)">7 dias</button>
    <button class="cdtab" onclick="calLoad(14,this)">14 dias</button>
  </div>
  <div id="cal-list"><div class="cal-empty">Carregando...</div></div>
</div>

<!-- Overlay cobre o scrollbar cinza do iframe → substitua visualmente por separador azul-escuro -->
<div id="tq-sep"></div>

<!-- ── Ticker Panel ── -->
<div class="ticker-panel" id="tickerPanel">
  <div class="tq-hdr" style="justify-content:flex-end">
    <span class="tq-live" id="tqLive"></span>
  </div>
  <div class="tq-body" id="tqBody">
    <div style="padding:20px 10px;font-size:10px;color:#434651">Carregando...</div>
  </div>
  <div class="tq-ft">
    <span id="tqAge">—</span>
    <button class="tq-rb" onclick="tqFetch()" title="Atualizar">↻</button>
  </div>
</div>

<div class="frame-wrap">
  <div class="loader" id="loader1">
    <div class="spinner"></div>
    Carregando IBOV Calls...
  </div>
  <div class="loader hidden" id="loader2">
    <div class="spinner" style="border-top-color:var(--c2)"></div>
    Carregando Intermarket Dashboard...
  </div>
  <div class="loader hidden" id="loader3">
    <div class="spinner" style="border-top-color:var(--c3)"></div>
    Carregando Macro Dashboard...
  </div>
  <div class="loader hidden" id="loader4">
    <div class="spinner" style="border-top-color:var(--c4)"></div>
    Carregando Market Breadth...
  </div>
  <div class="loader hidden" id="loader5">
    <div class="spinner" style="border-top-color:var(--c5)"></div>
    Carregando Biblioteca...
  </div>

  <iframe id="f1" src="" class="visible"
          onload="loaded(1)"></iframe>
  <iframe id="f2" src="about:blank"
          onload="loaded(2)"></iframe>
  <iframe id="f3" src="about:blank"
          onload="loaded(3)"></iframe>
  <iframe id="f4" src="about:blank"
          onload="loaded(4)"></iframe>
  <iframe id="f5" src="about:blank"
          onload="loaded(5)"></iframe>

</div>

<script>
  var _loaded    = {1: false, 2: false, 3: false, 4: false, 5: false};
  var _srcSet    = {1: false, 2: false, 3: false, 4: false, 5: false};
  var _current   = 1;

  var _cv = Date.now();
  var URLS = {
    1: "/ibov/?v=" + _cv,
    2: "/intermarket/?v=" + _cv,
    3: "/macro/?v=" + _cv,
    4: "/breadth/?v=" + _cv,
    5: "/biblioteca/?v=" + _cv,
  };

  function loaded(n) {
    if (!_srcSet[n]) return;
    _loaded[n] = true;
    document.getElementById("loader" + n).classList.add("hidden");
  }

  function applyTab(n) {
    _current = n;
    localStorage.setItem("hub_active_tab", n);

    if (!_srcSet[n]) {
      _srcSet[n] = true;
      document.getElementById("f" + n).src = URLS[n];
    }

    [1, 2, 3, 4, 5].forEach(function(i) {
      document.getElementById("f" + i).classList.toggle("visible", i === n);
      document.getElementById("loader" + i).classList.toggle("hidden",
        i !== n || _loaded[i]);
    });

    document.getElementById("btn1").className =
      "nav-btn" + (n === 1 ? " active-1" : "");
    document.getElementById("btn2").className =
      "nav-btn" + (n === 2 ? " active-2" : "");
    document.getElementById("btn3").className =
      "nav-btn" + (n === 3 ? " active-3" : "");
    document.getElementById("btn4").className =
      "nav-btn" + (n === 4 ? " active-4" : "");
    document.getElementById("btn5").className =
      "nav-btn" + (n === 5 ? " active-8" : "");
    if (n === 1) {
      var today = new Date().toISOString().slice(0,10);
      localStorage.setItem("calls_last_seen", today);
      document.getElementById("call-badge").style.display = "none";
    }
    if (n === 5) {
      localStorage.setItem("biblioteca_last_seen", Date.now().toString());
      document.getElementById("biblio-badge").style.display = "none";
    }
  }

  function show(n) {
    if (n === _current) return;
    applyTab(n);
  }

  // Restaura a última aba visitada ao atualizar a página, em vez de sempre abrir em IBOV Calls
  (function() {
    var saved = parseInt(localStorage.getItem("hub_active_tab"), 10);
    var initial = (saved >= 1 && saved <= 5) ? saved : 1;
    applyTab(initial);
  })();

  // ── News Panel ──
  var _newsOpen = false;
  var _newsTab  = "brasil";
  var _newsData = {};
  var _newsTs   = {};

  // ── Posicionamento dos painéis laterais (sem sobreposição) ──
  // Ordem da direita para esquerda: ticker (200px) → calendário (415px) → notícias (365px)
  function _syncPanels() {
    var tickerW = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--ticker-w'), 10) || 200;
    var base    = document.body.classList.contains('ticker-hidden') ? 0 : tickerW;
    var calEl   = document.getElementById('cal-panel');
    var newsEl  = document.getElementById('news-panel');
    var calW    = _calOpen ? calEl.offsetWidth : 0;
    calEl.style.right  = _calOpen  ? base + 'px' : '-420px';
    newsEl.style.right = _newsOpen ? (base + calW) + 'px' : '-370px';
  }

  function toggleNews() {
    _newsOpen = !_newsOpen;
    var newsEl = document.getElementById("news-panel");
    newsEl.classList.toggle("open", _newsOpen);
    document.getElementById("btn-news").classList.toggle("active-5", _newsOpen);
    if (_newsOpen && !_newsData[_newsTab]) loadNews(_newsTab, document.getElementById("ntab-" + _newsTab));
    if (_newsOpen && _calOpen) {
      // Cal já aberto: posiciona notícias à esquerda do target sem transição para
      // evitar que o painel anime cruzando por dentro do calendário
      var calEl = document.getElementById('cal-panel');
      var base  = document.body.classList.contains('ticker-hidden') ? 0
                    : (parseInt(getComputedStyle(document.documentElement).getPropertyValue('--ticker-w'), 10) || 200);
      newsEl.style.transition = 'none';
      newsEl.style.right = (base + calEl.offsetWidth + newsEl.offsetWidth) + 'px';
      newsEl.getBoundingClientRect(); // força reflow
      newsEl.style.transition = '';  // reativa transição CSS
    }
    _syncPanels();
  }

  var _overviewOpen = false;
  function toggleOverview() {
    _overviewOpen = !_overviewOpen;
    document.body.classList.toggle("ticker-hidden", !_overviewOpen);
    document.getElementById("btn-overview").classList.toggle("active-6", _overviewOpen);
    if (_overviewOpen && !window._tqFetched) { window._tqFetched = true; tqFetch(); }
    _syncPanels();
  }
  document.body.classList.add("ticker-hidden"); // oculto por padrão

  // ── Calendar Panel ──
  var _calOpen = false;
  var _calDays = 3;
  var _calData = {};

  function toggleCal() {
    _calOpen = !_calOpen;
    document.getElementById("cal-panel").classList.toggle("open", _calOpen);
    document.getElementById("btn-cal").classList.toggle("active-7", _calOpen);
    if (_calOpen && !_calData[_calDays]) calLoad(_calDays, document.querySelector(".cdtab.active"));
    _syncPanels();
  }

  function calLoad(days, btn) {
    _calDays = days;
    document.querySelectorAll(".cdtab").forEach(function(b) { b.classList.remove("active"); });
    if (btn) btn.classList.add("active");
    if (_calData[days]) { renderCal(_calData[days]); return; }
    document.getElementById("cal-list").innerHTML = "<div class='cal-loading'>⏳ Buscando eventos...</div>";
    fetch("/api/calendar?days=" + days)
      .then(function(r) { return r.json(); })
      .then(function(items) {
        _calData[days] = items;
        renderCal(items);
        setTimeout(function() { delete _calData[days]; }, 600000);
      })
      .catch(function() {
        document.getElementById("cal-list").innerHTML = "<div class='cal-empty'>Erro ao carregar calendário.</div>";
      });
  }

  function renderCal(events) {
    if (!events || events.length === 0) {
      document.getElementById("cal-list").innerHTML = "<div class='cal-empty'>Nenhum evento encontrado para o período.</div>";
      return;
    }
    var html = "<div class='cal-val-hdr'><span></span><span></span><span></span><span>Evento</span><span>Real</span><span>Prev.</span><span>Ant.</span></div>";
    var lastDate = "";
    var impMap = {High:"H",Medium:"M",Low:"L"};
    var _c2f = {
      USD:"us", BRL:"br", EUR:"eu", GBP:"gb", JPY:"jp",
      CNY:"cn", AUD:"au", CAD:"ca", CHF:"ch", MXN:"mx",
      NZD:"nz", KRW:"kr", US:"us", BR:"br"
    };
    function _flagImg(cur) {
      var code = _c2f[cur];
      if (!code) return cur || "";
      return "<img src='https://flagcdn.com/w20/" + code + ".png' title='" + cur + "' style='vertical-align:middle;border-radius:1px;max-width:22px;'>";
    }
    events.forEach(function(e) {
      if (e.date !== lastDate) {
        html += "<div class='cal-date-hdr'>" + e.date + "</div>";
        lastDate = e.date;
      }
      var imp = impMap[e.impact] || "L";
      var dots = "";
      for (var i=0;i<3;i++) {
        var filled = (imp==="H" && i<3) || (imp==="M" && i<2) || (imp==="L" && i<1);
        dots += "<span class='cal-dot " + (filled ? imp : "L") + "'></span>";
      }
      var actualCls = "cal-val actual";
      var flag = _flagImg(e.currency);
      html += "<div class='cal-event'>" +
        "<span class='cal-time'>" + e.time + "</span>" +
        "<span class='cal-curr'>" + flag + "</span>" +
        "<span class='cal-imp'>" + dots + "</span>" +
        "<span class='cal-name'>" + e.event + "</span>" +
        "<span class='" + actualCls + "'>" + (e.actual || "—") + "</span>" +
        "<span class='cal-val'>" + (e.forecast || "—") + "</span>" +
        "<span class='cal-val'>" + (e.previous || "—") + "</span>" +
        "</div>";
    });
    document.getElementById("cal-list").innerHTML = html;
  }


  function loadNews(tab, btn) {
    _newsTab = tab;
    document.querySelectorAll(".ntab").forEach(function(b) { b.classList.remove("active"); });
    if (btn) btn.classList.add("active");
    if (_newsData[tab]) {
      tab === "calls" ? renderCalls(_newsData[tab]) : renderNews(_newsData[tab]);
      return;
    }
    document.getElementById("news-list").innerHTML = "<div class='news-empty'>Carregando...</div>";
    document.getElementById("news-refresh-bar").style.display = "none";
    if (tab === "calls") {
      fetch("/ibov/api/calls")
        .then(function(r) { return r.json(); })
        .then(function(items) {
          items.sort(function(a,b){ return b.date.localeCompare(a.date); });
          _newsData["calls"] = items;
          _newsTs["calls"]   = Date.now();
          renderCalls(items);
          setTimeout(function() { delete _newsData["calls"]; }, 900000);
        })
        .catch(function() {
          document.getElementById("news-list").innerHTML = "<div class='news-empty'>IbovCalls offline.</div>";
        });
    } else {
      fetch("/api/news?tab=" + tab)
        .then(function(r) { return r.json(); })
        .then(function(items) {
          _newsData[tab] = items;
          _newsTs[tab]   = Date.now();
          renderNews(items);
          setTimeout(function() { delete _newsData[tab]; }, 900000);
        })
        .catch(function() {
          document.getElementById("news-list").innerHTML = "<div class='news-empty'>Erro ao carregar.</div>";
        });
    }
  }

  function forceReloadNews() {
    delete _newsData[_newsTab];
    loadNews(_newsTab, document.getElementById("ntab-" + _newsTab));
  }

  function _ago(pub) {
    try {
      var d = new Date(pub), diff = Math.floor((Date.now() - d) / 1000);
      if (diff < 60) return "agora";
      if (diff < 3600) return Math.floor(diff/60) + "min";
      if (diff < 86400) return Math.floor(diff/3600) + "h";
      return Math.floor(diff/86400) + "d";
    } catch(e) { return ""; }
  }

  function renderNews(items) {
    var list = document.getElementById("news-list");
    if (!items || !items.length) { list.innerHTML = "<div class='news-empty'>Nenhuma notícia encontrada.</div>"; return; }
    list.innerHTML = items.map(function(n) {
      var ago = _ago(n.pub);
      return "<div class='news-item'><a href='" + n.link + "' target='_blank' rel='noopener'>" +
        "<div class='news-meta'><span class='news-src'>" + (n.source||"") + "</span>" +
        (ago ? "<span class='news-time'>• " + ago + "</span>" : "") + "</div>" +
        "<div class='news-title'>" + n.title.replace(/</g,"&lt;") + "</div>" +
        "</a></div>";
    }).join("");
    _showRefreshBar();
  }

  function renderCalls(items) {
    var list = document.getElementById("news-list");
    if (!items || !items.length) { list.innerHTML = "<div class='news-empty'>Nenhum call encontrado.</div>"; return; }
    var lastSeen = localStorage.getItem("calls_last_seen") || "1970-01-01";
    list.innerHTML = items.map(function(c) {
      var isnew = c.date > lastSeen;
      var esc = function(s){ return (s||"").replace(/</g,"&lt;"); };
      return "<div class='news-item" + (isnew ? " call-new" : "") + "'>" +
        "<a href='" + c.url + "' target='_blank' rel='noopener'>" +
        "<div class='news-meta'>" +
        "<span class='news-src call-bank'>" + esc(c.bank) + "</span>" +
        "<span class='news-time'>• " + c.date + "</span>" +
        (isnew ? "<span class='call-new-badge'>NOVO</span>" : "") +
        "</div>" +
        "<div class='news-title'>" + esc(c.title) + "</div>" +
        (c.summary ? "<div class='call-summary'>" + esc(c.summary.substring(0,120)) + "…</div>" : "") +
        "</a></div>";
    }).join("");
    _showRefreshBar();
  }

  function _showRefreshBar() {
    var bar = document.getElementById("news-refresh-bar");
    bar.style.display = "block";
    var age = document.getElementById("news-age");
    clearInterval(bar._iv);
    bar._iv = setInterval(function() {
      age.textContent = Math.floor((Date.now() - (_newsTs[_newsTab]||Date.now())) / 1000);
    }, 5000);
  }

  // Badge de notificação para calls novos
  function _refreshCallBadge() {
    fetch("/ibov/api/calls")
      .then(function(r) { return r.json(); })
      .then(function(items) {
        var lastSeen = localStorage.getItem("calls_last_seen") || "1970-01-01";
        var newCount = items.filter(function(c) { return c.date > lastSeen; }).length;
        var badge = document.getElementById("call-badge");
        if (newCount > 0) {
          badge.textContent = newCount;
          badge.style.display = "flex";
        } else {
          badge.style.display = "none";
        }
      })
      .catch(function() {});
  }
  _refreshCallBadge();
  setInterval(_refreshCallBadge, 1800000);

  // Badge de notificação para posts novos na Biblioteca
  function _refreshBiblioBadge() {
    fetch("/api/biblioteca/posts")
      .then(function(r) { return r.json(); })
      .then(function(items) {
        var lastSeen = parseInt(localStorage.getItem("biblioteca_last_seen"), 10) || 0;
        var newCount = items.filter(function(p) { return p.ts > lastSeen; }).length;
        var badge = document.getElementById("biblio-badge");
        if (_current !== 5 && newCount > 0) {
          badge.textContent = newCount;
          badge.style.display = "flex";
        } else {
          badge.style.display = "none";
        }
      })
      .catch(function() {});
  }
  _refreshBiblioBadge();
  // Ancora às 05h e repete a cada 2h a partir daí (05h, 07h, 09h, ...), em vez de a cada 30min
  (function _scheduleBiblioBadge() {
    var now = new Date();
    var next = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 5, 0, 0, 0);
    if (next <= now) next.setDate(next.getDate() + 1);
    setTimeout(function() {
      _refreshBiblioBadge();
      setInterval(_refreshBiblioBadge, 7200000);
    }, next - now);
  })();

  setInterval(function() {
    if (_newsOpen) { delete _newsData[_newsTab]; loadNews(_newsTab, document.getElementById("ntab-"+_newsTab)); }
  }, 900000);

  // ── Ticker Panel — TradingView style ──
  var _tqTs = 0;

  var TQ_GROUPS = [
    { label: "USA FUTURES",   keys: ["ES","NQ","YM"] },
    { label: "SENTIMENT",     keys: ["US10Y","VIX","DXY"] },
    { label: "CRYPTO",        keys: ["BTC","ETH","BNB"] },
    { label: "COMMODITIES",   keys: ["PETROLEO","OURO","PRATA","COBRE","MINERIO_FERRO","GAS_NATURAL"] },
    { label: "BRASIL",        keys: ["IBOV","EWZ","USDBRL","DIFUT"] },
  ];

  var TQ_META = {
    ES:       { label:"ES!",       dot:"#f23645", fmt:function(v){ return v.toLocaleString("en-US",{maximumFractionDigits:2}); }},
    NQ:       { label:"NQ!",       dot:"#2196f3", fmt:function(v){ return v.toLocaleString("en-US",{maximumFractionDigits:2}); }},
    YM:       { label:"YM!",       dot:"#26a69a", fmt:function(v){ return v.toLocaleString("en-US",{maximumFractionDigits:0}); }},
    US10Y:    { label:"US10Y",     dot:"#2962ff", fmt:function(v){ return v.toFixed(3)+"%"; }},
    VIX:      { label:"VIX",       dot:"#9c27b0", fmt:function(v){ return v.toFixed(2); }},
    DXY:      { label:"DXY",       dot:"#26a69a", fmt:function(v){ return v.toFixed(2); }},
    BTC:           { label:"BTC",        dot:"#f7931a", fmt:function(v){ return "$"+Math.round(v).toLocaleString("en-US"); }},
    ETH:           { label:"ETH",        dot:"#627eea", fmt:function(v){ return "$"+v.toFixed(2); }},
    BNB:           { label:"BNB",        dot:"#f3ba2f", fmt:function(v){ return "$"+v.toFixed(2); }},
    PETROLEO:      { label:"CRUDE OIL",  dot:"#607d8b", fmt:function(v){ return "$"+v.toFixed(2); }},
    OURO:          { label:"GOLD",       dot:"#ffd700", fmt:function(v){ return "$"+v.toLocaleString("en-US",{maximumFractionDigits:2}); }},
    PRATA:         { label:"SILVER",     dot:"#9e9e9e", fmt:function(v){ return "$"+v.toFixed(3); }},
    COBRE:         { label:"COPPER",     dot:"#ff7043", fmt:function(v){ return "$"+v.toFixed(4); }},
    MINERIO_FERRO: { label:"FEF2 (SGX)", dot:"#8d6e63", fmt:function(v){ return "$"+v.toFixed(2); }},
    GAS_NATURAL:   { label:"NAT GAS",    dot:"#80cbc4", fmt:function(v){ return "$"+v.toFixed(3); }},
    IBOV:    { label:"IBOVESPA",  dot:"#00c4a0", fmt:function(v){ return v.toLocaleString("pt-BR",{maximumFractionDigits:0}); }},
    EWZ:     { label:"EWZ",       dot:"#009c3b", fmt:function(v){ return "$"+v.toFixed(2); }},
    USDBRL:  { label:"USD/BRL",   dot:"#ffcc00", fmt:function(v){ return v.toFixed(4); }},
    DIFUT:   { label:"DI1F2033",  dot:"#ff9800", fmt:function(v){
        if (v > 4 && v < 35) return v.toFixed(3)+"% a.a.";
        return v.toLocaleString("en-US",{maximumFractionDigits:0});
    }},
  };

  function tqRender(data) {
    var body = document.getElementById("tqBody");
    var html = "";
    TQ_GROUPS.forEach(function(g) {
      html += "<div class='tq-gh'>" + g.label + "</div>";
      g.keys.forEach(function(k) {
        var m = TQ_META[k];
        var d = data ? data[k] : null;
        if (!d) {
          html += "<div class='tq-row'>" +
            "<span class='tq-dot' style='background:" + m.dot + "'></span>" +
            "<span class='tq-sym'>" + m.label + "</span>" +
            "<div class='tq-vals'><span class='tq-price' style='color:#434651'>—</span><span class='tq-pct flat'>—</span></div>" +
            "</div>";
          return;
        }
        var pct = d.change_pct;
        var cls  = pct > 0 ? "up" : pct < 0 ? "dn" : "flat";
        var sign = pct >= 0 ? "+" : "";
        html += "<div class='tq-row'>" +
          "<span class='tq-dot' style='background:" + m.dot + "'></span>" +
          "<span class='tq-sym'>" + m.label + "</span>" +
          "<div class='tq-vals'>" +
            "<span class='tq-price'>" + m.fmt(d.price) + "</span>" +
            "<span class='tq-pct " + cls + "'>" + sign + pct.toFixed(2) + "%</span>" +
          "</div>" +
          "</div>";
      });
    });
    body.innerHTML = html;
    _tqTs = Date.now();
    _tqUpdateAge();
  }

  function _tqUpdateAge() {
    var el = document.getElementById("tqAge");
    if (!el || !_tqTs) return;
    var s = Math.floor((Date.now() - _tqTs) / 1000);
    el.textContent = s < 60 ? s + "s atrás" : Math.floor(s/60) + "min atrás";
  }

  function tqFetch() {
    var live = document.getElementById("tqLive");
    if (live) { live.style.background = "#e3b341"; live.style.boxShadow = "0 0 5px #e3b341"; }
    fetch("/api/quotes")
      .then(function(r){ return r.json(); })
      .then(function(d){
        tqRender(d);
        if (live) { live.style.background = "#26a69a"; live.style.boxShadow = "0 0 5px #26a69a"; }
      })
      .catch(function(){
        if (live) { live.style.background = "#ef5350"; live.style.boxShadow = "none"; }
      });
  }

  tqFetch();
  setInterval(tqFetch, 30000);
  setInterval(_tqUpdateAge, 5000);
</script>

</body>
</html>"""


# ── FastAPI shell ─────────────────────────────────────────────────────────────

app = FastAPI(title="Macro Desk")

# CORS liberado: o artifact "Análises Macro Desk" roda em claude.ai (origem diferente
# desta) e precisa poder chamar a API da Biblioteca aqui hospedada. Não há autenticação
# nem dados sensíveis de terceiros neste servidor pessoal, então liberar geral é aceitável.
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Log de acessos (IP, rota, hora) ─────────────────────────────────────────
# Registra toda requisição ao Hub (todas as abas) num SQLite local, pra dar
# visibilidade de quem acessou o quê — em especial via o túnel ngrok público.
# Consultado sob demanda (sem página dedicada); ver ACCESS_LOG_DB.
import sqlite3 as _sqlite3

ACCESS_LOG_DB = BASE / "access_log.db"


def _init_access_log() -> None:
    conn = _sqlite3.connect(ACCESS_LOG_DB)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS access_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            ip TEXT,
            method TEXT,
            path TEXT,
            status INTEGER,
            user_agent TEXT
        )"""
    )
    conn.commit()
    conn.close()


_init_access_log()


@app.middleware("http")
async def _log_access(request: Request, call_next):
    response = await call_next(request)
    try:
        conn = _sqlite3.connect(ACCESS_LOG_DB)
        conn.execute(
            "INSERT INTO access_log (ts, ip, method, path, status, user_agent) VALUES (?,?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(),
                request.client.host if request.client else None,
                request.method,
                request.url.path,
                response.status_code,
                request.headers.get("user-agent", ""),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return response


sys.path.insert(0, str(BIBLIOTECA_DIR))
from biblioteca_api import router as biblioteca_api_router  # noqa: E402

app.include_router(biblioteca_api_router)


@app.get("/", response_class=HTMLResponse)
def shell() -> str:
    return _SHELL


# ── Proxy reverso ─────────────────────────────────────────────────────────────

_SKIP_HEADERS = {"host", "content-length", "transfer-encoding", "content-encoding"}


async def _proxy(request: Request, target_base: str, strip_prefix: str) -> Response:
    path = request.url.path[len(strip_prefix):]
    if not path or not path.startswith("/"):
        path = "/" + (path or "")
    url = f"{target_base}{path}"
    if request.url.query:
        url += f"?{request.url.query}"

    req_headers = {k: v for k, v in request.headers.items() if k.lower() not in _SKIP_HEADERS}

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.request(
            method=request.method,
            url=url,
            headers=req_headers,
            content=await request.body(),
            follow_redirects=False,
        )

    content = resp.content
    content_type = resp.headers.get("content-type", "")

    if "text/html" in content_type:
        html = content.decode("utf-8", errors="replace")
        # Reescreve caminhos absolutos internos para o prefixo do proxy
        for attr, q in [("src=", '"'), ("src=", "'"), ("href=", '"'), ("href=", "'"), ("action=", '"'), ("action=", "'")]:
            old = f'{attr}{q}/'
            new = f'{attr}{q}{strip_prefix}/'
            html = html.replace(old, new)
        # Reescreve fetch/axios/XHR com caminhos absolutos
        html = html.replace("fetch('/", f"fetch('{strip_prefix}/")
        html = html.replace('fetch("/', f'fetch("{strip_prefix}/')
        # Reescreve variavel de base de API (padrao: const API = "" ou const BASE = "")
        html = re.sub(r'(const\s+(?:API|BASE)\s*=\s*)["\']["\']', rf'\1"{strip_prefix}"', html)
        content = html.encode("utf-8")

    resp_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _SKIP_HEADERS}
    return Response(content=content, status_code=resp.status_code, headers=resp_headers)


@app.api_route("/intermarket", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.api_route("/intermarket/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_intermarket(request: Request, path: str = "") -> Response:
    return await _proxy(request, f"http://127.0.0.1:{PORT_INTERMARKET}", "/intermarket")


@app.api_route("/breadth", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.api_route("/breadth/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_breadth(request: Request, path: str = "") -> Response:
    return await _proxy(request, f"http://127.0.0.1:{PORT_BREADTH}", "/breadth")


@app.api_route("/macro", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.api_route("/macro/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_macro(request: Request, path: str = "") -> Response:
    return await _proxy(request, f"http://127.0.0.1:{PORT_MACRO}", "/macro")


@app.api_route("/ibov", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
@app.api_route("/ibov/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy_ibov(request: Request, path: str = "") -> Response:
    return await _proxy(request, f"http://127.0.0.1:{PORT_IBOV}", "/ibov")


@app.get("/biblioteca")
@app.get("/biblioteca/{path:path}")
async def biblioteca(path: str = "") -> Response:
    # Página estática (localStorage-only, sem backend) — servida direto do disco,
    # sempre fresca. Cópia local do artifact "Análises Macro Desk" (claude.ai
    # bloqueia iframe de outra origem via X-Frame-Options: SAMEORIGIN, por isso
    # não dá pra embutir o artifact remoto direto).
    return HTMLResponse((BIBLIOTECA_DIR / "index.html").read_text(encoding="utf-8"))


@app.get("/api/news")
async def api_news(tab: str = "brasil") -> JSONResponse:
    now = time.time()
    cached = _news_cache.get(tab)
    if cached and now - cached["ts"] < _NEWS_TTL:
        return JSONResponse(cached["data"])
    sources = RSS_SOURCES.get(tab, [])
    results = await asyncio.gather(*[_fetch_rss(s, u) for s, u in sources])
    items: list[dict] = []
    for lst in results:
        items.extend(lst)
    items.sort(key=_sort_key, reverse=True)
    data = items[:40]
    _news_cache[tab] = {"ts": now, "data": data}
    return JSONResponse(data)


# ──────────────────────────────────────────────────────────────────────────
#  Economic Calendar — Investing.com via cloudscraper
# ──────────────────────────────────────────────────────────────────────────

_CAL_CACHE: dict = {"ts": 0, "data": None, "days": 0}
_CAL_TTL = 600  # 10 min

class EconomicCalendar:
    _scraper = None
    _token: str | None = None
    _token_ts: float = 0

    # country IDs on investing.com
    _COUNTRY_IDS = {"US": "5", "BR": "32"}

    @classmethod
    def _get_scraper(cls):
        if cls._scraper is None:
            import cloudscraper
            cls._scraper = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False}
            )
        return cls._scraper

    @classmethod
    def _get_token(cls) -> str | None:
        now = time.time()
        if cls._token and now - cls._token_ts < 3600:
            return cls._token
        try:
            s = cls._get_scraper()
            r = s.get("https://www.investing.com/economic-calendar/", timeout=20,
                       headers={"Accept-Language": "en-US,en;q=0.9"})
            m = re.search(
                r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
                r.text, re.DOTALL
            )
            if not m:
                return None
            nd = json.loads(m.group(1))
            token = cls._find_key(nd, "accessToken")
            cls._token = token
            cls._token_ts = now
            return token
        except Exception:
            return None

    @staticmethod
    def _find_key(d, key, depth=0):
        if depth > 10:
            return None
        if isinstance(d, dict):
            if key in d:
                return d[key]
            for v in d.values():
                res = EconomicCalendar._find_key(v, key, depth + 1)
                if res:
                    return res
        elif isinstance(d, list):
            for v in d:
                res = EconomicCalendar._find_key(v, key, depth + 1)
                if res:
                    return res
        return None

    # ── Dicionário de tradução EN→PT ──────────────────────────────────────────
    _TRANSLATIONS: list[tuple[str, str]] = [
        # Períodos
        (r"\(MoM\)",  "(M/M)"),
        (r"\(YoY\)",  "(A/A)"),
        (r"\(QoQ\)",  "(T/T)"),
        (r"\(WoW\)",  "(S/S)"),
        # Payrolls / Emprego
        ("Nonfarm Payrolls",           "Payrolls Não-Agrícolas"),
        ("Private Nonfarm Payrolls",   "Empregos Privados"),
        ("Government Payrolls",        "Empregos Governo"),
        ("Manufacturing Payrolls",     "Empregos Indústria"),
        ("ADP Nonfarm Employment",     "Emprego Privado ADP"),
        ("ADP Employment Change",      "Variação Emprego ADP"),
        ("Initial Jobless Claims",     "Pedidos Seguro-Desemprego"),
        ("Continuing Jobless Claims",  "Pedidos Contínuos Desemprego"),
        ("Jobless Claims 4-Week Avg",  "Média 4S - Seguro-Desemprego"),
        ("JOLTS Job Openings",         "Vagas JOLTS"),
        ("Challenger Job Cuts",        "Demissões Challenger"),
        ("Unemployment Rate",          "Taxa de Desemprego"),
        ("Average Hourly Earnings",    "Remuneração Média/Hora"),
        ("Average Weekly Hours",       "Média Horas Semanais"),
        # Inflação EUA
        ("Consumer Price Index",       "CPI"),
        ("Core CPI",                   "CPI Núcleo"),
        ("Producer Price Index",       "PPI"),
        ("Core PPI",                   "PPI Núcleo"),
        ("Core PCE Price Index",       "PCE Núcleo"),
        ("PCE Price Index",            "PCE"),
        ("Import Price Index",         "Preços de Importação"),
        ("Export Price Index",         "Preços de Exportação"),
        # PIB / Atividade
        ("Gross Domestic Product",     "PIB"),
        ("GDP",                        "PIB"),
        ("Industrial Production",      "Produção Industrial"),
        ("Capacity Utilization Rate",  "Utilização da Capacidade"),
        ("Factory Orders",             "Pedidos de Fábricas"),
        ("Durable Goods Orders",       "Pedidos Bens Duráveis"),
        ("Business Inventories",       "Estoques Empresariais"),
        ("Wholesale Inventories",      "Estoques Atacado"),
        ("Retail Sales",               "Vendas no Varejo"),
        # Habitação EUA
        ("Housing Starts",             "Início de Construções"),
        ("Building Permits",           "Licenças de Construção"),
        ("Existing Home Sales",        "Vendas Casas Usadas"),
        ("New Home Sales",             "Vendas Casas Novas"),
        ("Case-Shiller Home Price",    "Preços Case-Shiller"),
        ("Pending Home Sales",         "Vendas Pendentes Imóveis"),
        # PMI
        ("ISM Manufacturing PMI",      "PMI Industrial ISM"),
        ("ISM Non-Manufacturing PMI",  "PMI Serviços ISM"),
        ("ISM Services PMI",           "PMI Serviços ISM"),
        ("S&P Global Composite PMI",   "PMI Composto S&P Global"),
        ("S&P Global Manufacturing PMI", "PMI Industrial S&P Global"),
        ("S&P Global Services PMI",    "PMI Serviços S&P Global"),
        ("Chicago PMI",                "PMI Chicago"),
        # Confiança EUA
        ("Michigan Consumer Sentiment",    "Sentimento U. Michigan"),
        ("Michigan Consumer Expectations", "Expectativas U. Michigan"),
        ("Consumer Confidence",            "Confiança do Consumidor"),
        ("NFIB Business Optimism",         "Otimismo Empresarial NFIB"),
        # Índices Fed
        ("Empire State Manufacturing Index", "Índice Empire State"),
        ("Philadelphia Fed Manufacturing Index", "Índice Philly Fed"),
        ("Dallas Fed Manufacturing Index",   "Índice Dallas Fed"),
        ("Richmond Fed Manufacturing Index", "Índice Richmond Fed"),
        # Fed / FOMC
        ("Fed Interest Rate Decision",  "Decisão de Juros do Fed"),
        ("Federal Funds Rate",          "Taxa dos Fed Funds"),
        ("FOMC Meeting Minutes",        "Ata do FOMC"),
        ("FOMC Statement",              "Comunicado do FOMC"),
        ("FOMC Press Conference",       "Coletiva do Fed"),
        ("FOMC Member",                 "Membro do FOMC"),
        ("Fed Chair",                   "Presidente do Fed"),
        # Comércio / Conta
        ("Trade Balance",               "Balança Comercial"),
        ("Current Account",             "Conta Corrente"),
        # Veículos
        ("Total Vehicle Sales",         "Vendas de Veículos"),
        ("Auto Production",             "Produção de Veículos"),
        ("Auto Sales",                  "Vendas de Veículos"),
        # Energia
        ("Crude Oil Inventories",       "Estoques de Petróleo"),
        ("Crude Oil Imports",           "Importação de Petróleo"),
        ("Cushing Crude Oil Inventories", "Estoques Petróleo Cushing"),
        ("Natural Gas Storage",         "Armazenamento Gás Natural"),
        ("EIA Natural Gas Storage",     "Estoques Gás Natural EIA"),
        # Brasil
        ("IPC-Fipe Inflation Index",    "Inflação IPC-Fipe"),
        ("Brazilian IPCA Inflation Index SA", "IPCA Dessazonalizado"),
        ("IPCA",                        "IPCA"),
        ("IGP-DI Inflation Index",      "Inflação IGP-DI"),
        ("IGP-M Inflation Index",       "Inflação IGP-M"),
        ("BCB Focus Market Readout",    "BCB Focus"),
        ("CFTC BRL speculative net positions", "Posições BRL (CFTC)"),
        ("Brazilian Service Sector Growth", "Setor de Serviços"),
        ("Brazil Thomson Reuters IPSOS PCSI", "Confiança Consumidor (Thomson Reuters)"),
        # Genérico
        ("Consumer Prices",             "Preços ao Consumidor"),
        ("Producer Prices",             "Preços ao Produtor"),
        ("Interest Rate Decision",      "Decisão de Juros"),
        ("Foreign Exchange Reserves",   "Reservas Cambiais"),
        ("Foreign Reserves",            "Reservas Externas"),
        ("Net FX Reserves",             "Reservas Líquidas (FX)"),
        ("speculative net positions",   "posições especulativas"),
        ("Inflation Index",             "Índice de Inflação"),
        ("Inflation Rate",              "Taxa de Inflação"),
        # Leilões Tesouraria EUA
        ("2-Year Note Auction",         "Leilão T-Note 2 Anos"),
        ("3-Year Note Auction",         "Leilão T-Note 3 Anos"),
        ("5-Year Note Auction",         "Leilão T-Note 5 Anos"),
        ("7-Year Note Auction",         "Leilão T-Note 7 Anos"),
        ("10-Year Note Auction",        "Leilão T-Note 10 Anos"),
        ("20-Year Bond Auction",        "Leilão T-Bond 20 Anos"),
        ("30-Year Bond Auction",        "Leilão T-Bond 30 Anos"),
        ("Note Auction",                "Leilão de T-Note"),
        ("Bond Auction",                "Leilão de T-Bond"),
        ("Bill Auction",                "Leilão de T-Bill"),
        # ISM preços
        ("ISM Non-Manufacturing Prices","Preços Serviços ISM"),
        ("ISM Manufacturing Prices",    "Preços Indústria ISM"),
        ("ISM Non-Manufacturing Employment", "Emprego Serviços ISM"),
        ("ISM Manufacturing Employment","Emprego Indústria ISM"),
        ("ISM Non-Manufacturing New Orders", "Novos Pedidos Serviços ISM"),
        # Genérico
        ("Speaks",                      "Discursa"),
        ("Statement",                   "Comunicado"),
        ("Minutes",                     "Ata"),
        ("Decision",                    "Decisão"),
        ("Prices",                      "Preços"),
        ("Employment",                  "Emprego"),
        ("New Orders",                  "Novos Pedidos"),
        ("Production",                  "Produção"),
        ("Inventories",                 "Estoques"),
        ("Exports",                     "Exportações"),
        ("Imports",                     "Importações"),
        ("Services",                    "Serviços"),
        ("Manufacturing",               "Indústria"),
        ("Composite",                   "Composto"),
    ]

    @classmethod
    def _translate(cls, name: str) -> str:
        for pattern, replacement in cls._TRANSLATIONS:
            if pattern.startswith("(") and pattern.endswith(")") and "\\" in pattern:
                name = re.sub(pattern, replacement, name)
            else:
                name = name.replace(pattern, replacement)
        return name

    @classmethod
    def _parse_html(cls, html: str) -> list[dict]:
        soup = BeautifulSoup(html, "html.parser")
        events = []
        for row in soup.find_all("tr"):
            if "js-event-item" not in row.get("class", []):
                continue
            dt_str = row.get("data-event-datetime", "")
            try:
                dt = datetime.strptime(dt_str, "%Y/%m/%d %H:%M:%S")
                date_fmt = dt.strftime("%a, %d %b %Y")
                time_fmt = dt.strftime("%H:%M")
                dt_iso = dt.isoformat()
            except ValueError:
                date_fmt, time_fmt, dt_iso = "", "", ""

            # Currency / country
            flag_td = row.find("td", class_="flagCur")
            currency = ""
            country = ""
            if flag_td:
                span = flag_td.find("span", class_=re.compile(r"ceFlags"))
                if span:
                    cls_list = [c for c in span.get("class", []) if c != "ceFlags"]
                    country = cls_list[0].replace("_", " ") if cls_list else ""
                # text node after span
                text_nodes = [t for t in flag_td.strings if t.strip()]
                currency = text_nodes[-1].strip() if text_nodes else ""

            # Impact: count grayFullBullishIcon
            sent_td = row.find("td", class_="sentiment")
            bulls = sent_td.find_all("i", class_="grayFullBullishIcon") if sent_td else []
            impact_map = {1: "Low", 2: "Medium", 3: "High"}
            impact = impact_map.get(len(bulls), "Low")

            # Event name (translated to PT)
            event_td = row.find("td", class_="event")
            event_name = cls._translate(event_td.get_text(strip=True)) if event_td else ""

            # Actual / forecast / previous
            def _cell(cls_name):
                el = row.find("td", class_=cls_name)
                return el.get_text(strip=True) if el else ""

            actual   = _cell("act")
            forecast = _cell("fore")
            previous = row.find("td", class_="prev")
            previous = previous.get_text(strip=True) if previous else ""

            events.append({
                "datetime": dt_iso,
                "date": date_fmt,
                "time": time_fmt,
                "country": country,
                "currency": currency,
                "impact": impact,
                "event": event_name,
                "actual": actual,
                "forecast": forecast,
                "previous": previous,
            })
        return events

    @classmethod
    def fetch(cls, countries: list[str], importances: list[str], days: int = 7) -> list[dict]:
        s = cls._get_scraper()
        token = cls._get_token()
        today = datetime.now()
        payload: dict = {
            "country[]":    [cls._COUNTRY_IDS.get(c, c) for c in countries],
            "importance[]": importances,
            "dateFrom":     today.strftime("%Y-%m-%d"),
            "dateTo":       (today + timedelta(days=days)).strftime("%Y-%m-%d"),
            "timeZone":     "8",
            "timeFilter":   "timeRemain",
            "currentTab":   "custom",
            "submitFilters":"1",
            "limit_from":   "0",
        }
        hdrs = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "*/*",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://www.investing.com/economic-calendar/",
        }
        if token:
            hdrs["Authorization"] = f"Bearer {token}"
        r = s.post(
            "https://www.investing.com/economic-calendar/Service/getCalendarFilteredData",
            data=payload, headers=hdrs, timeout=25
        )
        html = r.json().get("data", "")
        return cls._parse_html(html)

    @classmethod
    def fetch_us_high_medium(cls, days: int = 7) -> list[dict]:
        # importance: 1=Low, 2=Medium, 3=High on investing.com
        return cls.fetch(["US"], ["3", "2"], days)

    @classmethod
    def fetch_brazil_high_medium(cls, days: int = 7) -> list[dict]:
        # Brasil quase não tem eventos marcados "High" nessa fonte (mesmo CPI e
        # Vendas no Varejo ficam em "Medium") — High-only deixaria a seção
        # praticamente sempre vazia, por isso mantém High+Medium.
        return cls.fetch(["BR"], ["3", "2"], days)

    @classmethod
    def fetch_filtered(cls, days: int = 7) -> list[dict]:
        """Brazil High+Medium + US High+Medium, sorted by datetime."""
        br   = cls.fetch(["BR"], ["3", "2"], days)
        us   = cls.fetch(["US"], ["3", "2"], days)
        combined = br + us
        combined.sort(key=lambda e: e.get("datetime", ""))
        return combined


@app.get("/api/calendar")
async def api_calendar(days: int = 7) -> JSONResponse:
    now = time.time()
    if _CAL_CACHE["data"] and _CAL_CACHE["days"] == days and now - _CAL_CACHE["ts"] < _CAL_TTL:
        return JSONResponse(_CAL_CACHE["data"])
    try:
        data = await asyncio.to_thread(EconomicCalendar.fetch_filtered, days)
        _CAL_CACHE["data"] = data
        _CAL_CACHE["ts"]   = now
        _CAL_CACHE["days"] = days
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


_QUOTES_CACHE: dict = {"ts": 0, "data": None}
_QUOTES_TTL = 25  # seconds — under the 30s JS poll interval

# ── MT5 DI1F33 — cache com lock para acesso thread-safe ──
_MT5_DI_CACHE: dict = {"price": None, "change_pct": None, "ts": 0}
import threading as _threading
_MT5_LOCK = _threading.Lock()

# ── Iron Ore 62% — cache com background thread (cloudscraper não é thread-safe) ──
_IRON_ORE_CACHE: dict = {"price": None, "change_pct": None, "ts": 0}
_IRON_ORE_LOCK = _threading.Lock()

def _iron_ore_refresh_loop():
    import time as _t, json as _json
    _ttl = 300  # 5 min
    while True:
        # Aguarda se cache ainda fresco
        if _IRON_ORE_CACHE["price"] is not None and _t.time() - _IRON_ORE_CACHE["ts"] < _ttl:
            _t.sleep(30)
            continue
        try:
            import cloudscraper as _cs
            _s = _cs.create_scraper(browser={"browser":"chrome","platform":"windows","mobile":False})
            # Chart API: retorna OHLCV diário dos últimos ~10 dias para Iron Ore 62% (CME, id=961729)
            # Formato: [[timestamp, open, high, low, close, volume, ?], ...]
            # Usado para calcular variação correta entre os dois últimos fechamentos.
            _r = _s.get(
                "https://api.investing.com/api/financialdata/961729/historical/chart/?period=P1W&pointscount=60",
                timeout=25, headers={"Accept-Language":"en-US,en;q=0.9", "Accept":"application/json"}
            )
            _d = _json.loads(_r.text).get("data", [])
            if _d and len(_d) >= 2:
                _price = float(_d[-1][4])  # último close/settlement
                _prev  = float(_d[-2][4])  # penúltimo close
                _chg   = round((_price - _prev) / _prev * 100, 2) if _prev else 0.0
                _IRON_ORE_CACHE["price"]      = _price
                _IRON_ORE_CACHE["change_pct"] = _chg
                _IRON_ORE_CACHE["ts"]         = _t.time()
        except Exception:
            pass
        _t.sleep(30)

_iron_ore_thread = _threading.Thread(target=_iron_ore_refresh_loop, daemon=True)
_iron_ore_thread.start()


@app.get("/api/quotes")
async def api_quotes() -> JSONResponse:
    now = time.time()
    if _QUOTES_CACHE["data"] and now - _QUOTES_CACHE["ts"] < _QUOTES_TTL:
        return JSONResponse(_QUOTES_CACHE["data"])

    _tickers = {
        "ES":            "ES=F",
        "NQ":            "NQ=F",
        "YM":            "YM=F",
        "US10Y":         "^TNX",
        "VIX":           "^VIX",
        "DXY":           "DX-Y.NYB",
        "BTC":           "BTC-USD",
        "ETH":           "ETH-USD",
        "BNB":           "BNB-USD",
        "PETROLEO":      "CL=F",
        "OURO":          "GC=F",
        "PRATA":         "SI=F",
        "COBRE":         "HG=F",
        "MINERIO_FERRO": "__investing_iron_ore__",
        "GAS_NATURAL":   "NG=F",
        "IBOV":    "^BVSP",
        "EWZ":     "EWZ",
        "USDBRL":  "BRL=X",
        "DIFUT":   "__b3__",
    }

    _BINANCE_CRYPTO = {"BTC": "BTCUSDT", "ETH": "ETHUSDT", "BNB": "BNBUSDT"}

    def _fetch_one(name: str, ticker: str):
        # ── Crypto: Binance klines diários → variação do fechamento anterior (= TradingView) ──
        # Binance ticker/24hr usa janela rolante de 24h; klines usa fechamento UTC midnight, igual TV.
        if name in _BINANCE_CRYPTO:
            try:
                sym = _BINANCE_CRYPTO[name]
                r = httpx.get(
                    f"https://api.binance.com/api/v3/klines?symbol={sym}&interval=1d&limit=2",
                    timeout=8
                )
                d = r.json()
                prev_close = float(d[-2][4])   # fechamento de ontem (candle completo)
                current    = float(d[-1][4])   # preço atual (candle de hoje em aberto)
                chg_pct    = (current - prev_close) / prev_close * 100
                return name, {"price": round(current, 2), "change_pct": round(chg_pct, 2)}
            except Exception:
                pass  # fallback abaixo

        # ── MINERIO_FERRO: FEF2 Iron Ore 62% — lê do cache da background thread ──
        if ticker == "__investing_iron_ore__":
            if _IRON_ORE_CACHE["price"] is not None:
                return name, {"price": _IRON_ORE_CACHE["price"], "change_pct": _IRON_ORE_CACHE["change_pct"]}
            return name, None

        # ── DIFUT: DI1F2033 via MetaTrader5 com lock thread-safe ──
        if name == "DIFUT":
            now_ts = time.time()
            # Usa cache se fresco (< 55s)
            if _MT5_DI_CACHE["price"] is not None and now_ts - _MT5_DI_CACHE["ts"] < 55:
                return name, {"price": _MT5_DI_CACHE["price"], "change_pct": _MT5_DI_CACHE["change_pct"]}
            # Tenta atualizar via MT5 (com lock para evitar chamadas paralelas)
            if _MT5_LOCK.acquire(blocking=False):
                try:
                    import MetaTrader5 as mt5
                    if mt5.initialize():
                        sym = "DI1F33"
                        mt5.symbol_select(sym, True)
                        tick = mt5.symbol_info_tick(sym)
                        if tick and tick.last > 0.1:
                            current = round(float(tick.last), 3)
                            bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_D1, 0, 2)
                            change_pct = 0.0
                            if bars is not None and len(bars) >= 2:
                                prev_close = float(bars[-2]["close"])
                                if prev_close > 0.1:
                                    change_pct = round((current - prev_close) / prev_close * 100, 2)
                            _MT5_DI_CACHE["price"] = current
                            _MT5_DI_CACHE["change_pct"] = change_pct
                            _MT5_DI_CACHE["ts"] = time.time()
                        mt5.shutdown()
                except Exception:
                    pass
                finally:
                    _MT5_LOCK.release()
            if _MT5_DI_CACHE["price"] is not None:
                return name, {"price": _MT5_DI_CACHE["price"], "change_pct": _MT5_DI_CACHE["change_pct"]}
            return name, None

        # ── USDBRL: BCB PTAX Oficial (cotacaoVenda) → fallback yfinance BRL=X ──
        if name == "USDBRL":
            try:
                import datetime as _dt2
                _end   = _dt2.date.today().strftime("%m-%d-%Y")
                _start = (_dt2.date.today() - _dt2.timedelta(days=7)).strftime("%m-%d-%Y")
                _ptax_url = (
                    "https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/"
                    f"CotacaoDolarPeriodo(dataInicial=@di,dataFinalCotacao=@df)"
                    f"?@di='{_start}'&@df='{_end}'"
                    f"&$top=50&$format=json"
                    f"&$select=cotacaoVenda,dataHoraCotacao"
                    f"&$orderby=dataHoraCotacao desc"
                )
                _pr = httpx.get(_ptax_url, timeout=8)
                _vals = _pr.json().get("value", [])
                if _vals:
                    _today_day = _vals[0]["dataHoraCotacao"][:10]
                    _price_ptax = float(_vals[0]["cotacaoVenda"])
                    _prev_ptax  = next(
                        (float(v["cotacaoVenda"]) for v in _vals if v["dataHoraCotacao"][:10] < _today_day),
                        None
                    )
                    _chg_ptax = round((_price_ptax - _prev_ptax) / _prev_ptax * 100, 2) if _prev_ptax else 0.0
                    return name, {"price": round(_price_ptax, 4), "change_pct": _chg_ptax}
            except Exception:
                pass  # fallback yfinance abaixo

        # ── Futuros (=F) ──────────────────────────────────────────────────────────────
        # Duas sub-categorias com comportamentos diferentes no Yahoo Finance:
        #
        # INDEX FUTURES (ES, NQ, YM): fast_info.previous_close tem "rollover artifact"
        #   após troca de contrato (Jun→Set em 19/jun) → usa history()[-2] que dá o
        #   settlement real do dia anterior do contrato vigente.
        #
        # COMMODITY FUTURES (GC, CL, SI, HG, NG): fast_info.previous_close reflete o
        #   settlement oficial do CME/NYMEX (~13:30 CT). history()[-2] dá o fechamento
        #   eletrônico GLOBEX (17h ET) que pode diferir. O TradingView usa o settlement
        #   oficial → usar fast_info.previous_close.
        # ──────────────────────────────────────────────────────────────────────────────
        _INDEX_FUTURES = {"ES=F", "NQ=F", "YM=F"}

        if ticker.endswith("=F"):
            try:
                _yftkr = yf.Ticker(ticker)
                _fi    = _yftkr.fast_info
                _price = float(_fi.last_price or 0)

                if ticker in _INDEX_FUTURES:
                    # Index futures: history()[-2] = settlement correto do contrato vigente
                    hist  = _yftkr.history(period="5d", interval="1d")
                    _prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else 0
                else:
                    # Commodity futures: fast_info.previous_close = settlement oficial
                    _prev = float(_fi.previous_close or 0)
                    if _prev <= 0:
                        hist  = _yftkr.history(period="5d", interval="1d")
                        _prev = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else 0

                if _price > 0 and _prev > 0:
                    return name, {"price": round(_price, 6), "change_pct": round((_price - _prev) / _prev * 100, 2)}
            except Exception:
                pass

        # ── Não-futuros (VIX, US10Y, DXY, IBOV, EWZ): fast_info ──
        try:
            _fi = yf.Ticker(ticker).fast_info
            _fp = float(_fi.last_price or 0)
            _fc = float(_fi.previous_close or 0)
            if _fp > 0 and _fc > 0:
                return name, {"price": round(_fp, 6), "change_pct": round((_fp - _fc) / _fc * 100, 2)}
        except Exception:
            pass

        return name, None

    def _run_all():
        result: dict = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            futs = [ex.submit(_fetch_one, n, t) for n, t in _tickers.items()]
            for f in concurrent.futures.as_completed(futs):
                name, data = f.result()
                result[name] = data
        return result

    data = await asyncio.to_thread(_run_all)
    _QUOTES_CACHE["ts"]   = time.time()
    _QUOTES_CACHE["data"] = data
    return JSONResponse(data)


_DIVO_CACHE: dict = {"ts": 0, "data": None}  # ts=0 forces reload on first request
_DIVO_TTL = 3600  # 1 h

import logging as _logging
_divo_log = _logging.getLogger("divo")

_YF_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}


def _parse_yf_chart(j: dict) -> list:
    """Extrai série mensal de um response da v8/finance/chart do Yahoo Finance."""
    chart = j.get("chart") or {}
    results = chart.get("result") or []
    if not results:
        return []
    res = results[0]
    timestamps = res.get("timestamp") or []
    indicators = res.get("indicators") or {}
    # prefer adjclose
    adjclose_list = indicators.get("adjclose") or []
    adj = adjclose_list[0].get("adjclose") if adjclose_list else None
    if not adj:
        quote_list = indicators.get("quote") or []
        adj = quote_list[0].get("close") if quote_list else []
    adj = adj or []
    out = []
    for ts, val in zip(timestamps, adj):
        if val is None:
            continue
        d = datetime.utcfromtimestamp(ts)
        out.append({"date": f"{d.year}-{d.month:02d}-01", "value": float(val)})
    return out


async def _fetch_yf(ticker: str) -> list:
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
           f"?interval=1mo&range=max")
    async with httpx.AsyncClient(follow_redirects=True, timeout=25) as c:
        r = await c.get(url, headers=_YF_HEADERS)
    _divo_log.info("YF %s status=%s len=%d", ticker, r.status_code, len(r.content))
    return _parse_yf_chart(r.json())


async def _fetch_cdi() -> list:
    # Série 4189: Selic/CDI acumulada no mês — valores em % a.a. (taxa anualizada base 12)
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4189/dados?formato=json"
    async with httpx.AsyncClient(follow_redirects=True, timeout=30) as c:
        r = await c.get(url)
    items = r.json()
    _divo_log.info("BCB CDI(4189) status=%s items=%d", r.status_code, len(items))
    items_sorted = sorted(items, key=lambda x: (x["data"][6:], x["data"][3:5], x["data"][:2]))
    cur = 1.0
    out: list = []
    for item in items_sorted:
        parts = item["data"].split("/")  # dd/mm/yyyy
        date = f"{parts[2]}-{parts[1]}-{parts[0]}"
        # valor = % a.a. (annualized); convert to monthly factor
        annual_pct = float(item["valor"])
        monthly_rate = (1 + annual_pct / 100) ** (1 / 12) - 1
        cur *= 1 + monthly_rate
        out.append({"date": date, "value": cur})
    return out


@app.get("/api/debug-mt5")
async def api_debug_mt5() -> JSONResponse:
    import time as _t
    import traceback as _tb
    result = {"cache": dict(_MT5_DI_CACHE), "direct": None, "error": None}
    try:
        import MetaTrader5 as mt5
        ok = mt5.initialize()
        result["init"] = ok
        if ok:
            tick = mt5.symbol_info_tick("DI1F33")
            result["tick_last"] = float(tick.last) if tick else None
            mt5.shutdown()
    except Exception as e:
        result["error"] = _tb.format_exc()
    return JSONResponse(result)


@app.get("/api/divo-data")
async def api_divo_data() -> JSONResponse:
    now = time.time()
    if _DIVO_CACHE["data"] and now - _DIVO_CACHE["ts"] < _DIVO_TTL:
        return JSONResponse(_DIVO_CACHE["data"])
    try:
        divo_data, bvsp_data, cdi_data = await asyncio.gather(
            _fetch_yf("DIVO11.SA"),
            _fetch_yf("%5EBVSP"),
            _fetch_cdi(),
        )
        result = {"divo": divo_data, "ibov": bvsp_data, "cdi": cdi_data}
        _DIVO_CACHE["data"] = result
        _DIVO_CACHE["ts"] = now
        return JSONResponse(result)
    except Exception as e:
        import traceback
        _divo_log.error("api_divo_data error: %s\n%s", e, traceback.format_exc())
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/divo", response_class=HTMLResponse)
@app.get("/divo/", response_class=HTMLResponse)
def divo_page() -> HTMLResponse:
    p = Path(__file__).parent / "divo11_ibov_cdi.html"
    if p.exists():
        headers = {"Cache-Control": "no-cache, no-store, must-revalidate"}
        return HTMLResponse(p.read_text(encoding="utf-8"), headers=headers)
    return HTMLResponse("<p style='color:#fff;padding:40px'>Arquivo divo11_ibov_cdi.html não encontrado.</p>", status_code=404)


# ── Entry point ───────────────────────────────────────────────────────────────

async def _daily_update_loop() -> None:
    """Dispara updates diários dos projetos que não têm scheduler próprio."""
    UPDATE_HOUR, UPDATE_MIN = 18, 35   # 18h35 — após MacroDashboard rodar às 18h30

    while True:
        now = datetime.now()
        target = now.replace(hour=UPDATE_HOUR, minute=UPDATE_MIN, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        await asyncio.sleep((target - now).total_seconds())

        # P1 — Intermarket (trigger via REST)
        try:
            async with httpx.AsyncClient(timeout=120.0) as cl:
                await cl.post(f"http://127.0.0.1:{PORT_INTERMARKET}/api/collect/trigger")
            print("  [auto-update] P1 Intermarket: OK", flush=True)
        except Exception as e:
            print(f"  [auto-update] P1 erro: {e}", flush=True)


        # P2 (Breadth) e P4 (Macro) têm schedulers próprios — não precisam de trigger externo


@app.on_event("startup")
async def _start_scheduler() -> None:
    asyncio.create_task(_daily_update_loop())
    # Watchdog em thread separada (não bloqueia o event loop)
    import threading as _threading
    _threading.Thread(target=_watchdog_loop, daemon=True, name="watchdog").start()


if __name__ == "__main__":
    print()
    print("  ==========================================")
    print("            Macro Desk v1.1")
    print("  ==========================================")
    print(f"  Shell       -> http://localhost:{PORT_SHELL}")
    print(f"  Intermarket -> http://localhost:{PORT_INTERMARKET}")
    print(f"  Breadth     -> http://localhost:{PORT_BREADTH}")
    print(f"  Macro       -> http://localhost:{PORT_MACRO}")
    print(f"  Ibov Calls  -> http://localhost:{PORT_IBOV}")
    print("  ==========================================")
    print()

    _start_subservers()

    print(f"  Hub iniciado -> http://localhost:{PORT_SHELL}")
    print()

    uvicorn.run(app, host="0.0.0.0", port=PORT_SHELL, log_level="warning")
