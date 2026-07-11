"use client";

import { useEffect, useState } from "react";
import { api, Buyback, BuybackSortField } from "@/lib/api";
import SortableTh from "@/components/SortableTh";

function fmtNum(v: number | null) {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR");
}

function StatusBadge({ status }: { status: string }) {
  const isActive = status === "Em Andamento";
  return (
    <span
      className="smb-badge"
      style={{
        color: isActive ? "var(--green)" : "var(--text3)",
        border: `1px solid ${isActive ? "var(--green)" : "var(--border)"}`,
      }}
    >
      {status}
    </span>
  );
}

const STATUS_OPTIONS: { value: "" | "Em Andamento" | "Encerrado"; label: string }[] = [
  { value: "Em Andamento", label: "Em andamento" },
  { value: "Encerrado", label: "Encerrados" },
  { value: "", label: "Todos" },
];

export default function RecomprasPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | "Em Andamento" | "Encerrado">("Em Andamento");
  const [sortBy, setSortBy] = useState<BuybackSortField>("declared_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [rows, setRows] = useState<Buyback[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      api
        .getBuybacks({ search: q, status, sortBy, sortDir, limit: 150 })
        .then(setRows)
        .catch(() => setRows([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [q, status, sortBy, sortDir]);

  function toggleSort(field: BuybackSortField) {
    if (field === sortBy) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("asc");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Recompras</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
          Programas de recompra de ações declarados à CVM — dado oficial (Eventos Societários Especiais), atualizado diariamente.
        </p>
      </div>

      <input
        className="smb-card w-full px-4 py-2 outline-none"
        placeholder="Buscar por ticker, empresa ou CNPJ..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <div className="smb-card p-3 flex flex-wrap gap-3 items-end">
        <div className="flex gap-2">
          {STATUS_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setStatus(o.value)}
              className="smb-card px-3 py-1.5 text-sm"
              style={{ color: status === o.value ? "var(--cyan)" : "var(--text2)" }}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="smb-card smb-table-wrap">
        <table className="smb-table w-full">
          <thead>
            <tr>
              <SortableTh label="Empresa" active={sortBy === "ticker"} dir={sortDir} onClick={() => toggleSort("ticker")} />
              <th>CNPJ</th>
              <th>Situação</th>
              <th>Tipo</th>
              <SortableTh label="Declarado em" align="right" active={sortBy === "declared_at"} dir={sortDir} onClick={() => toggleSort("declared_at")} />
              <SortableTh label="Prazo final" align="right" active={sortBy === "deadline"} dir={sortDir} onClick={() => toggleSort("deadline")} />
              <SortableTh label="Qtd ON" align="right" active={sortBy === "qty_common_shares"} dir={sortDir} onClick={() => toggleSort("qty_common_shares")} />
              <SortableTh label="Qtd PN" align="right" active={sortBy === "qty_preferred_shares"} dir={sortDir} onClick={() => toggleSort("qty_preferred_shares")} />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} title={r.reason ?? undefined}>
                <td style={{ color: "var(--text)" }}>
                  <div style={{ fontWeight: 600 }}>{r.ticker ?? "—"}</div>
                  <div className="text-xs" style={{ color: "var(--text3)" }}>{r.company_name}</div>
                </td>
                <td style={{ color: "var(--text3)" }}>{r.cnpj}</td>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td style={{ color: "var(--text3)" }}>{r.operation_type ?? "—"}</td>
                <td className="num" style={{ color: "var(--text3)" }}>{r.declared_at}</td>
                <td className="num" style={{ color: "var(--text3)" }}>{r.deadline ?? "—"}</td>
                <td className="num">{fmtNum(r.qty_common_shares)}</td>
                <td className="num">{fmtNum(r.qty_preferred_shares)}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={8} style={{ color: "var(--text3)" }}>
                  Nenhum programa de recompra encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
