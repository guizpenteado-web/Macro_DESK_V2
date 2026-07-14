"""VLMO ingestion — negociacao de administradores/conselheiros/controladores
com valores mobiliarios da propria companhia. Verificado 10/jul/2026 baixando
dado real: o CSV nao tem chave natural de linha (nenhum ID_* como o de
recompra), entao cada reingestao de um ano faz DELETE+INSERT completo das
linhas daquele source_year — mais simples e seguro do que tentar casar uma
chave composta artificial.

Schema real (vlmo_cia_aberta_con_{year}.csv): CNPJ_Companhia;Nome_Companhia;
Data_Referencia;Versao;Tipo_Empresa;Empresa;Tipo_Cargo;Tipo_Movimentacao;
Descricao_Movimentacao;Tipo_Operacao;Tipo_Ativo;
Caracteristica_Valor_Mobiliario;Intermediario;Data_Movimentacao;Quantidade;
Preco_Unitario;Volume. "Saldo Inicial" (~60% das linhas) tem
Data_Movimentacao vazia — e um saldo de abertura de cargo, nao um evento
datado; ingerido mas sem data.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import IngestionLog, InsiderTrade
from app.services.cvm_client import download_vlmo_zip, extract_member

logger = logging.getLogger(__name__)

# Tipo_Movimentacao -> direcao simplificada, usada pro filtro "compra/venda"
# no endpoint (o resto — desdobramento, doacao, emprestimo, saldo inicial —
# fica com direction=None, continua visivel mas fora do filtro padrao).
#
# Achado 14/jul/2026: "Compra a termo"/"Venda a termo" (sem crase) nunca
# batia com o dado real da CVM, que vem com crase ("Compra à termo"/"Venda
# à termo") — 1.055 + 185 negociacoes a termo genuinas ficavam com
# direction=None e sumiam do grafico "Qtd insiders/mes" (que so soma linhas
# com direction=COMPRA/VENDA desde o fix da distorcao por eventos
# societarios). Tambem faltava mapear exercicio de opcao que resulta em
# posicao real (credito de acoes/units por exercicio de compra = aquisicao
# de verdade; debito por exercicio de opcao de venda = reducao de verdade)
# — sao eventos de mercado genuinos, diferentes de bonificacao/subscricao/
# plano de remuneracao (que continuam de fora, propositalmente).
_DIRECTION_MAP = {
    "Compra": "COMPRA",
    "Compra à vista": "COMPRA",
    "Compra a termo": "COMPRA",
    "Compra à termo": "COMPRA",
    "Ações decorrentes de exercício de opção de compra": "COMPRA",
    "Units decorrentes de exercício de opção de compra": "COMPRA",
    "Venda": "VENDA",
    "Venda à vista": "VENDA",
    "Venda a termo": "VENDA",
    "Venda à termo": "VENDA",
    "Ações reduzidas (exercício de opção de venda)": "VENDA",
    "Units reduzidas (exercício de opção de venda)": "VENDA",
}


def _parse(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding="latin-1")
    df["Data_Referencia"] = pd.to_datetime(df["Data_Referencia"], errors="coerce").dt.date
    df["Data_Movimentacao"] = pd.to_datetime(df["Data_Movimentacao"], errors="coerce").dt.date
    return df


def ingest_vlmo_year(db: Session, year: int, force_download: bool = True) -> int:
    log = IngestionLog(source="vlmo", ref_date=datetime.utcnow().date(), status="running")
    db.add(log)
    db.flush()
    try:
        zip_path = download_vlmo_zip(year, force=force_download)
        raw = extract_member(zip_path, f"vlmo_cia_aberta_con_{year}.csv")
        if raw is None:
            raise FileNotFoundError(f"vlmo_cia_aberta_con_{year}.csv nao encontrado no zip")
        df = _parse(raw)

        rows = [
            {
                "source_year": year,
                "cnpj_companhia": r.CNPJ_Companhia,
                "company_name": r.Nome_Companhia,
                "data_referencia": r.Data_Referencia,
                "versao": int(r.Versao) if pd.notna(r.Versao) else None,
                "tipo_empresa": r.Tipo_Empresa if pd.notna(r.Tipo_Empresa) else None,
                "empresa": r.Empresa if pd.notna(r.Empresa) else None,
                "tipo_cargo": r.Tipo_Cargo if pd.notna(r.Tipo_Cargo) else None,
                "tipo_movimentacao": r.Tipo_Movimentacao,
                "direction": _DIRECTION_MAP.get(r.Tipo_Movimentacao),
                "tipo_operacao": r.Tipo_Operacao if pd.notna(r.Tipo_Operacao) else None,
                "tipo_ativo": r.Tipo_Ativo if pd.notna(r.Tipo_Ativo) else None,
                "caracteristica_valor_mobiliario": r.Caracteristica_Valor_Mobiliario
                if pd.notna(r.Caracteristica_Valor_Mobiliario)
                else None,
                "intermediario": r.Intermediario if pd.notna(r.Intermediario) else None,
                "data_movimentacao": r.Data_Movimentacao if pd.notna(r.Data_Movimentacao) else None,
                "quantidade": float(r.Quantidade) if pd.notna(r.Quantidade) else None,
                "preco_unitario": float(r.Preco_Unitario) if pd.notna(r.Preco_Unitario) else None,
                "volume": float(r.Volume) if pd.notna(r.Volume) else None,
            }
            for r in df.itertuples()
            if pd.notna(r.CNPJ_Companhia) and pd.notna(r.Data_Referencia)
        ]

        db.execute(delete(InsiderTrade).where(InsiderTrade.source_year == year))
        if rows:
            db.bulk_insert_mappings(InsiderTrade, rows)

        db.commit()
        log.status = "success"
        log.rows_processed = len(rows)
        log.finished_at = datetime.utcnow()
        db.commit()
        logger.info("vlmo %d: %d movimentacoes", year, len(rows))
        return len(rows)
    except Exception:
        db.rollback()
        log.status = "failed"
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        logger.exception("vlmo %d: falhou", year)
        raise
