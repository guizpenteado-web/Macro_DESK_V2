"""
Gerador de CSV para o indicador TradingView - Fluxo Estrangeiro IBOV
Fonte: dadosdemercado.com.br/fluxo

Instalar dependencias (apenas uma vez):
    pip install requests beautifulsoup4 lxml

Executar:
    python gerar_csv.py

Resultado:
    fluxo_estrangeiro.csv  (importar no TradingView conforme instrucoes)
"""

import requests
from bs4 import BeautifulSoup
import csv
import os
from datetime import datetime
from decimal import Decimal, InvalidOperation

URL = "https://www.dadosdemercado.com.br/fluxo"
OUTPUT = "fluxo_estrangeiro.csv"


def fetch_page():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    resp = requests.get(URL, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.text


def parse_number(text):
    """Converte '1.234,56' ou '-1.234,56' para Decimal."""
    if not text:
        return None
    t = text.strip()
    if t in ("-", "", "n/d", "---"):
        return None
    # Remove R$, espacos, pontos de milhar; troca virgula decimal por ponto
    t = t.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    # Manter apenas digitos, ponto e sinal
    clean = ""
    for ch in t:
        if ch.isdigit() or ch in ".-":
            clean += ch
    try:
        return Decimal(clean)
    except InvalidOperation:
        return None


def parse_date(text):
    """Converte 'dd/mm/aaaa' para 'aaaa-mm-dd'."""
    t = text.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(t, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def find_estrangeiro_table(soup):
    """
    Localiza a tabela de fluxo do investidor estrangeiro.
    Tenta varios seletores para ser robusto a mudancas no layout.
    """
    candidatos = []

    # Estrategia 1: tabela cujo cabecalho menciona 'estrangeiro'
    for table in soup.find_all("table"):
        header = table.find("thead") or table.find("tr")
        if header and ("estrangeiro" in header.get_text().lower()
                       or "externo" in header.get_text().lower()):
            candidatos.append(table)

    # Estrategia 2: secao/div com titulo 'estrangeiro' que contem tabela
    if not candidatos:
        for heading in soup.find_all(["h1", "h2", "h3", "h4", "caption"]):
            if "estrangeiro" in heading.get_text().lower():
                parent = heading.find_parent(["section", "div", "article"])
                if parent:
                    tb = parent.find("table")
                    if tb:
                        candidatos.append(tb)

    # Estrategia 3: qualquer tabela com coluna de data + valores numericos
    if not candidatos:
        for table in soup.find_all("table"):
            trs = table.find_all("tr")
            if len(trs) > 5:
                primeira_linha = [td.get_text(strip=True) for td in trs[1].find_all("td")]
                if len(primeira_linha) >= 2 and parse_date(primeira_linha[0]):
                    candidatos.append(table)

    return candidatos[0] if candidatos else None


def extract_rows(html):
    soup = BeautifulSoup(html, "lxml")
    table = find_estrangeiro_table(soup)

    if not table:
        return []

    rows = []
    trs = table.find_all("tr")

    # Detectar indice das colunas pelo cabecalho
    header_row = trs[0] if trs else None
    cols_header = []
    if header_row:
        cols_header = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

    idx_data   = 0  # padrão: primeira coluna
    idx_saldo  = 1  # padrão: segunda coluna (saldo do dia)
    idx_acum   = None

    for i, h in enumerate(cols_header):
        if "data" in h or "pregao" in h:
            idx_data = i
        elif "acumul" in h:
            idx_acum = i
        elif "saldo" in h and i > 0 and idx_saldo == 1:
            idx_saldo = i

    for tr in trs[1:]:
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cols) < 2:
            continue

        data = parse_date(cols[idx_data]) if idx_data < len(cols) else None
        saldo_dia = parse_number(cols[idx_saldo]) if idx_saldo < len(cols) else None

        if not data or saldo_dia is None:
            continue

        saldo_acum = None
        if idx_acum is not None and idx_acum < len(cols):
            saldo_acum = parse_number(cols[idx_acum])

        rows.append({
            "data": data,
            "saldo_dia": saldo_dia,
            "saldo_acumulado": saldo_acum,
        })

    return rows


def calcular_acumulado(rows):
    """Recalcula saldo acumulado para garantir consistencia."""
    rows.sort(key=lambda r: r["data"])
    acum = Decimal("0")
    for row in rows:
        acum += row["saldo_dia"]
        if row["saldo_acumulado"] is None:
            row["saldo_acumulado"] = acum
    return rows


def gerar_csv(rows, output=OUTPUT):
    """
    Formato do CSV para o TradingView:
      close  = saldo_acumulado          (serie principal do indicador)
      open   = saldo_acumulado - saldo_dia  (acumulado do dia anterior)
      high   = max(open, close)
      low    = min(open, close)
      volume = abs(saldo_dia)

    Portanto no Pine Script: close - open = saldo_dia
    """
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "open", "high", "low", "close", "volume"])
        for r in rows:
            acum = float(r["saldo_acumulado"])
            dia  = float(r["saldo_dia"])
            prev = acum - dia  # acumulado do dia anterior
            writer.writerow([
                r["data"],
                round(prev, 2),
                round(max(prev, acum), 2),
                round(min(prev, acum), 2),
                round(acum, 2),
                round(abs(dia), 2),
            ])
    return os.path.abspath(output)


def main():
    print("=" * 60)
    print("Gerador de CSV - Fluxo Estrangeiro IBOV")
    print("Fonte: dadosdemercado.com.br/fluxo")
    print("=" * 60)
    print()

    print("[1/3] Buscando dados...")
    try:
        html = fetch_page()
    except requests.RequestException as e:
        print(f"ERRO de conexao: {e}")
        print("Verifique sua conexao com a internet e tente novamente.")
        return 1

    print("[2/3] Extraindo tabela de fluxo estrangeiro...")
    rows = extract_rows(html)

    if not rows:
        print()
        print("ATENCAO: Nenhum dado encontrado na pagina.")
        print("A estrutura do site pode ter mudado.")
        print("Solucao manual:")
        print("  1. Acesse: https://www.dadosdemercado.com.br/fluxo")
        print("  2. Copie a tabela de 'Investidor Estrangeiro'")
        print("  3. Cole em uma planilha Excel/Google Sheets")
        print("  4. Exporte como CSV no formato descrito no Instalacao_TradingView.md")
        return 1

    rows = calcular_acumulado(rows)
    print(f"    {len(rows)} registros encontrados.")

    print("[3/3] Gerando CSV...")
    caminho = gerar_csv(rows)

    print()
    print("=" * 60)
    print(f"SUCESSO! Arquivo gerado:")
    print(f"  {caminho}")
    print()
    print("PROXIMOS PASSOS NO TRADINGVIEW:")
    print()
    print("  1. Abra qualquer grafico no TradingView (ex: IBOV)")
    print("  2. Clique em '+' (topo) -> 'Indicador' -> aba 'Dados personalizados'")
    print("  3. Clique em 'Carregar dados de arquivo'")
    print("  4. Selecione o arquivo: fluxo_estrangeiro.csv")
    print("  5. Em 'Nome do simbolo', digite exatamente: FLUXO_EST_IBOV")
    print("  6. Clique em 'Importar'")
    print("  7. No Pine Editor, cole o conteudo de FluxoEstrangeiro_IBOV.pine")
    print("  8. Clique em 'Adicionar ao grafico'")
    print()
    print("Para atualizar os dados diariamente: execute este script novamente")
    print("e reimporte o CSV no TradingView.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    exit(main())
