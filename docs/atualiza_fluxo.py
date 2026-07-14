"""
Baixa novos dados de fluxo estrangeiro do dadosdemercado.com.br,
atualiza o CSV, regenera o Pine Script e copia para a Area de Trabalho.
Roda via Task Scheduler todo dia util.
"""

import csv, os, re, sys, shutil, subprocess
from datetime import datetime, timedelta
import requests
from bs4 import BeautifulSoup

DOCS_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(DOCS_DIR, "fluxo_estrangeiro.csv")
BUILD_PATH = os.path.join(DOCS_DIR, "build_pine.py")
PINE_PATH  = os.path.join(DOCS_DIR, "FluxoEstrangeiro_IBOV_FINAL.pine")
DESKTOP    = os.path.join(os.path.expanduser("~"), "Desktop", "FluxoExt_PINE.pine")
LOG_PATH   = os.path.join(DOCS_DIR, "atualiza_fluxo.log")

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def ler_ultimo_csv():
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    last = rows[-1]
    last_date = datetime.strptime(last["date"], "%Y-%m-%d").date()
    last_acum = float(last["close"])
    return last_date, last_acum, rows

def buscar_dados_site():
    url = "https://www.dadosdemercado.com.br/fluxo"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = requests.get(url, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    dados = []
    tabela = soup.find("table")
    if not tabela:
        log("ERRO: tabela nao encontrada na pagina")
        return dados

    for tr in tabela.find_all("tr")[1:]:
        tds = tr.find_all("td")
        if len(tds) < 2:
            continue
        try:
            # data no formato dd/mm/yyyy
            data_str = tds[0].get_text(strip=True)
            raw      = tds[1].get_text(strip=True)
            mult     = 1000.0 if "bi" in raw else 1.0
            dia_str  = raw.replace("mi", "").replace("bi", "").strip()
            dia_str  = dia_str.replace(".", "").replace(",", ".")
            dia_val  = float(dia_str) * mult
            dt       = datetime.strptime(data_str, "%d/%m/%Y").date()
            dados.append((dt, dia_val))
        except Exception:
            continue

    dados.sort(key=lambda x: x[0])
    return dados

def atualizar_csv(last_date, last_acum, novos):
    adicionados = 0
    prev_acum = last_acum
    with open(CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for dt, dia in novos:
            if dt <= last_date:
                continue
            new_acum = round(prev_acum + dia, 2)
            op = round(prev_acum, 2)
            cl = new_acum
            hi = round(max(op, cl), 2)
            lo = round(min(op, cl), 2)
            vo = round(abs(dia), 2)
            writer.writerow([dt.strftime("%Y-%m-%d"), op, hi, lo, cl, vo])
            log(f"  + {dt}  DIA={dia:+.2f}  ACUM={new_acum:.2f}")
            prev_acum = new_acum
            adicionados += 1
    return adicionados

def main():
    log("=" * 50)
    log("Iniciando atualizacao de fluxo estrangeiro")

    last_date, last_acum, _ = ler_ultimo_csv()
    log(f"Ultimo dado no CSV: {last_date}  ACUM={last_acum:.2f}")

    dados_site = buscar_dados_site()
    log(f"Dados obtidos do site: {len(dados_site)} registros")

    novos = [(dt, dia) for dt, dia in dados_site if dt > last_date]
    log(f"Novos registros a adicionar: {len(novos)}")

    if not novos:
        log("Nenhum dado novo. Pine ja esta atualizado.")
    else:
        n = atualizar_csv(last_date, last_acum, novos)
        log(f"{n} registro(s) adicionado(s) ao CSV")

    # Regenerar Pine Script
    python = sys.executable
    result = subprocess.run([python, BUILD_PATH], capture_output=True, text=True)
    if result.returncode != 0:
        log(f"ERRO ao gerar Pine: {result.stderr}")
        sys.exit(1)
    log(result.stdout.strip())

    # Copiar para Desktop
    shutil.copy2(PINE_PATH, DESKTOP)
    log(f"Pine copiado para: {DESKTOP}")
    log("Concluido.")

if __name__ == "__main__":
    main()
