"""Funcoes utilitarias gerais."""
import webbrowser
from pathlib import Path


def open_in_browser(path: Path) -> None:
    """Abre um arquivo HTML no navegador padrao."""
    webbrowser.open(path.resolve().as_uri())


def fmt_pct(value: float) -> str:
    """Formata percentual com uma casa decimal."""
    return f"{value:.1f}%"


def fmt_brl(value: float) -> str:
    """Formata valor em reais."""
    return f"R$ {value:,.2f}"