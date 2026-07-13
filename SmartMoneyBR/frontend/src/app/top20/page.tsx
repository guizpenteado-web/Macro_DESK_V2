"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, TopPerformerRow } from "@/lib/api";
import SortableTh from "@/components/SortableTh";
import { sortRows, useSort } from "@/lib/sort";

const WINDOWS = [5, 10, 15, 20];

function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

export default function Top20Page() {
  const [years, setYears] = useState(20);
  const [rows, setRows] = useState<TopPerformerRow[]>([]);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const sort = useSort<"fund_name" | "pct_return" | "net_asset_value" | "n_shareholders" | "first_date" | "financials_ref_date">();
  const sortedRows = sort.sortKey ? sortRows(rows, (r) => r[sort.sortKey!], sort.sortDir) : rows;

  useEffect(() => {
    setLoading(true);
    api
      .getTopPerformers(years)
      .then((r) => {
        setRows(r.rows);
        setAsOf(r.as_of);
      })
      .finally(() => setLoading(false));
  }, [years]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold">Top 20 — Melhor performance</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
            Retorno real via valor da cota (não confundir com crescimento de patrimônio, que pode vir só de captação nova).
          </p>
        </div>
        {asOf && <span className="text-sm" style={{ color: "var(--text3)" }}>Referência: {asOf}</span>}
      </div>

      <div className="flex gap-2">
        {WINDOWS.map((w) => (
          <button
            key={w}
            onClick={() => setYears(w)}
            className="smb-card px-3 py-1.5 text-sm"
            style={{ color: years === w ? "var(--amber)" : "var(--text2)" }}
          >
            {w} anos
          </button>
        ))}
      </div>

      <div className="smb-card smb-table-wrap">
        <table className="smb-table w-full">
          <thead>
            <tr>
              <th className="num">#</th>
              <SortableTh label="Fundo" active={sort.sortKey === "fund_name"} dir={sort.sortDir} onClick={() => sort.toggle("fund_name")} />
              <SortableTh label="Retorno no período" align="right" active={sort.sortKey === "pct_return"} dir={sort.sortDir} onClick={() => sort.toggle("pct_return")} />
              <SortableTh label="Patrimônio líquido" align="right" active={sort.sortKey === "net_asset_value"} dir={sort.sortDir} onClick={() => sort.toggle("net_asset_value")} />
              <SortableTh label="Cotistas" align="right" active={sort.sortKey === "n_shareholders"} dir={sort.sortDir} onClick={() => sort.toggle("n_shareholders")} />
              <SortableTh label="Desde" align="right" active={sort.sortKey === "first_date"} dir={sort.sortDir} onClick={() => sort.toggle("first_date")} />
              <SortableTh label="Divulgação" align="right" active={sort.sortKey === "financials_ref_date"} dir={sort.sortDir} onClick={() => sort.toggle("financials_ref_date")} />
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((r, i) => (
              <tr key={r.fund_id}>
                <td className="num" style={{ color: i < 3 ? "var(--amber)" : "var(--text3)" }}>{i + 1}º</td>
                <td>
                  <Link href={`/fundos/${r.fund_id}`} style={{ color: "var(--gold)" }}>
                    {r.fund_name}
                  </Link>
                  <div className="text-xs" style={{ color: "var(--text3)" }}>{r.fund_cnpj}</div>
                </td>
                <td className="num" style={{ color: r.pct_return >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                  {r.pct_return >= 0 ? "+" : ""}
                  {r.pct_return.toLocaleString("pt-BR")}%
                </td>
                <td className="num">{r.net_asset_value !== null ? fmtBRL(r.net_asset_value) : "—"}</td>
                <td className="num">{r.n_shareholders !== null ? r.n_shareholders.toLocaleString("pt-BR") : "—"}</td>
                <td className="num" style={{ color: "var(--text3)" }}>{r.first_date}</td>
                <td className="num" style={{ color: "var(--text3)" }}>{r.financials_ref_date ?? "—"}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={7} style={{ color: "var(--text3)" }}>
                  Sem dados suficientes de valor de cota para esta janela ainda.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
