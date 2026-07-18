"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, RankingRow, ConsensusRow } from "@/lib/api";
import SortableTh from "@/components/SortableTh";
import { sortRows, useSort } from "@/lib/sort";

const KINDS = [
  { key: "most-bought", label: "Mais comprado" },
  { key: "most-sold", label: "Mais vendido" },
  { key: "most-increased", label: "Mais aumentado" },
  { key: "most-decreased", label: "Mais reduzido" },
  { key: "most-new", label: "Novas posições" },
  { key: "most-closed", label: "Zeragens" },
];

const NEW_POSITIONS_SINCE_MARCH = "2026-03-01";

function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

export default function RankingsPage() {
  const [kind, setKind] = useState("most-bought");
  const [rows, setRows] = useState<RankingRow[]>([]);
  const [consensusRows, setConsensusRows] = useState<ConsensusRow[]>([]);
  const [refDate, setRefDate] = useState<string | null>(null);
  const [refDateFrom, setRefDateFrom] = useState<string | null>(null);
  const [consensus, setConsensus] = useState(false);
  const [sinceMarch, setSinceMarch] = useState(false);

  const rankSort = useSort<"ticker" | "n_funds" | "net_qty_delta" | "net_value_delta">();
  const sortedRows = rankSort.sortKey ? sortRows(rows, (r) => r[rankSort.sortKey!], rankSort.sortDir) : rows;

  const consensusSort = useSort<"ticker" | "n_funds" | "total_value">();
  const sortedConsensusRows = consensusSort.sortKey
    ? sortRows(consensusRows, (r) => r[consensusSort.sortKey!], consensusSort.sortDir)
    : consensusRows;

  useEffect(() => {
    if (consensus) {
      api.getConsensus().then((r) => {
        setConsensusRows(r.rows);
        setRefDate(r.ref_date);
      });
    } else {
      const since = kind === "most-new" && sinceMarch ? NEW_POSITIONS_SINCE_MARCH : undefined;
      api.getRanking(kind, since).then((r) => {
        setRows(r.rows);
        setRefDate(r.ref_date);
        setRefDateFrom(r.ref_date_from);
      });
    }
  }, [kind, consensus, sinceMarch]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Rankings</h1>
        {refDate && (
          <span className="text-sm" style={{ color: "var(--text3)" }}>
            Referência: {!consensus && refDateFrom ? `${refDateFrom} a ${refDate}` : refDate}
          </span>
        )}
      </div>

      <div className="flex gap-2 flex-wrap items-center">
        {KINDS.map((k) => (
          <button
            key={k.key}
            onClick={() => {
              setConsensus(false);
              setKind(k.key);
            }}
            className="smb-card px-3 py-1.5 text-sm"
            style={{ color: !consensus && kind === k.key ? "var(--gold)" : "var(--text2)" }}
          >
            {k.label}
          </button>
        ))}
        <button
          onClick={() => setConsensus(true)}
          className="smb-card px-3 py-1.5 text-sm"
          style={{ color: consensus ? "var(--gold)" : "var(--text2)" }}
        >
          Consenso institucional
        </button>
        {!consensus && kind === "most-new" && (
          <button
            onClick={() => setSinceMarch((v) => !v)}
            className="smb-card px-3 py-1.5 text-sm"
            style={{ color: sinceMarch ? "var(--gold)" : "var(--text2)" }}
          >
            Desde março
          </button>
        )}
      </div>

      <div className="smb-card smb-table-wrap">
        {consensus ? (
          <table className="smb-table w-full">
            <thead>
              <tr>
                <th className="num">#</th>
                <SortableTh label="Ativo" active={consensusSort.sortKey === "ticker"} dir={consensusSort.sortDir} onClick={() => consensusSort.toggle("ticker")} />
                <SortableTh label="Nº fundos detentores" align="right" active={consensusSort.sortKey === "n_funds"} dir={consensusSort.sortDir} onClick={() => consensusSort.toggle("n_funds")} />
                <SortableTh label="Valor total em carteira" align="right" active={consensusSort.sortKey === "total_value"} dir={consensusSort.sortDir} onClick={() => consensusSort.toggle("total_value")} />
              </tr>
            </thead>
            <tbody>
              {sortedConsensusRows.map((r, i) => (
                <tr key={r.asset_id}>
                  <td className="num" style={{ color: "var(--text3)" }}>{i + 1}</td>
                  <td>
                    <Link href={`/ativos/${r.asset_id}`} style={{ color: "var(--gold)" }}>
                      {r.ticker}
                    </Link>
                    <span className="ml-2 text-xs" style={{ color: "var(--text3)" }}>{r.company_name}</span>
                  </td>
                  <td className="num">{r.n_funds}</td>
                  <td className="num">{fmtBRL(r.total_value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <table className="smb-table w-full">
            <thead>
              <tr>
                <th className="num">#</th>
                <SortableTh label="Ativo" active={rankSort.sortKey === "ticker"} dir={rankSort.sortDir} onClick={() => rankSort.toggle("ticker")} />
                <SortableTh label="Nº fundos" align="right" active={rankSort.sortKey === "n_funds"} dir={rankSort.sortDir} onClick={() => rankSort.toggle("n_funds")} />
                <SortableTh label="Δ Qtd líquida" align="right" active={rankSort.sortKey === "net_qty_delta"} dir={rankSort.sortDir} onClick={() => rankSort.toggle("net_qty_delta")} />
                <SortableTh label="Δ Valor líquido" align="right" active={rankSort.sortKey === "net_value_delta"} dir={rankSort.sortDir} onClick={() => rankSort.toggle("net_value_delta")} />
              </tr>
            </thead>
            <tbody>
              {sortedRows.map((r, i) => (
                <tr key={r.asset_id}>
                  <td className="num" style={{ color: "var(--text3)" }}>{i + 1}</td>
                  <td>
                    <Link href={`/ativos/${r.asset_id}`} style={{ color: "var(--gold)" }}>
                      {r.ticker}
                    </Link>
                    <span className="ml-2 text-xs" style={{ color: "var(--text3)" }}>{r.company_name}</span>
                  </td>
                  <td className="num">{r.n_funds}</td>
                  <td className="num">{r.net_qty_delta.toLocaleString("pt-BR")}</td>
                  <td className="num" style={{ color: r.net_value_delta >= 0 ? "var(--green)" : "var(--red)" }}>{fmtBRL(r.net_value_delta)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
