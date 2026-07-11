"use client";

import { useEffect, useState } from "react";
import { api, InsiderTrade, InsiderSortField } from "@/lib/api";
import SortableTh from "@/components/SortableTh";

function fmtBRL(v: number | null) {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 });
}

function fmtNum(v: number | null) {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR");
}

function DirectionBadge({ direction }: { direction: "COMPRA" | "VENDA" | null }) {
  if (!direction) return <span style={{ color: "var(--text3)" }}>—</span>;
  const isBuy = direction === "COMPRA";
  return (
    <span className="smb-badge" style={{ color: isBuy ? "var(--green)" : "var(--red)", border: `1px solid ${isBuy ? "var(--green)" : "var(--red)"}` }}>
      {isBuy ? "COMPRA" : "VENDA"}
    </span>
  );
}

const DIRECTION_OPTIONS: { value: "COMPRA" | "VENDA" | ""; label: string }[] = [
  { value: "COMPRA", label: "Compras" },
  { value: "VENDA", label: "Vendas" },
  { value: "", label: "Todos" },
];

export default function InsidersPage() {
  const [q, setQ] = useState("");
  const [direction, setDirection] = useState<"COMPRA" | "VENDA" | "">("COMPRA");
  const [cargo, setCargo] = useState("");
  const [cargos, setCargos] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<InsiderSortField>("data_movimentacao");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [rows, setRows] = useState<InsiderTrade[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.getInsiderCargos().then(setCargos).catch(() => setCargos([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      api
        .getInsiderTrades({ search: q, direction, cargo, sortBy, sortDir, limit: 150 })
        .then(setRows)
        .catch(() => setRows([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [q, direction, cargo, sortBy, sortDir]);

  function toggleSort(field: InsiderSortField) {
    if (field === sortBy) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("desc");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Insiders</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
          Negociação de administradores, conselheiros e controladores com ações da própria companhia (CVM VLMO). Não
          há nome do indivíduo nos dados abertos da CVM — só o cargo agregado.
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
          {DIRECTION_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setDirection(o.value)}
              className="smb-card px-3 py-1.5 text-sm"
              style={{ color: direction === o.value ? "var(--cyan)" : "var(--text2)" }}
            >
              {o.label}
            </button>
          ))}
        </div>

        <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text3)" }}>
          Cargo
          <select
            className="smb-card px-2 py-1 outline-none text-sm"
            style={{ color: "var(--text)" }}
            value={cargo}
            onChange={(e) => setCargo(e.target.value)}
          >
            <option value="">Todos</option>
            {cargos.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="smb-card smb-table-wrap">
        <table className="smb-table w-full">
          <thead>
            <tr>
              <SortableTh label="Empresa" active={sortBy === "ticker"} dir={sortDir} onClick={() => toggleSort("ticker")} />
              <th>Cargo</th>
              <th>Negociante</th>
              <th>Movimentação</th>
              <th>Ativo</th>
              <SortableTh label="Data" align="right" active={sortBy === "data_movimentacao"} dir={sortDir} onClick={() => toggleSort("data_movimentacao")} />
              <SortableTh label="Qtd" align="right" active={sortBy === "quantidade"} dir={sortDir} onClick={() => toggleSort("quantidade")} />
              <SortableTh label="Preço" align="right" active={sortBy === "preco_unitario"} dir={sortDir} onClick={() => toggleSort("preco_unitario")} />
              <SortableTh label="Volume" align="right" active={sortBy === "volume"} dir={sortDir} onClick={() => toggleSort("volume")} />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td style={{ color: "var(--text)" }}>
                  <div style={{ fontWeight: 600 }}>{r.ticker ?? "—"}</div>
                  <div className="text-xs" style={{ color: "var(--text3)" }}>{r.company_name}</div>
                </td>
                <td style={{ color: "var(--text3)" }}>{r.tipo_cargo ?? "—"}</td>
                <td style={{ color: "var(--text3)" }}>{r.empresa ?? "—"}</td>
                <td>
                  <DirectionBadge direction={r.direction} />
                  <span className="ml-2 text-xs" style={{ color: "var(--text3)" }}>
                    {r.tipo_movimentacao}
                  </span>
                </td>
                <td style={{ color: "var(--text3)" }}>{r.tipo_ativo ?? "—"}</td>
                <td className="num" style={{ color: "var(--text3)" }}>{r.data_movimentacao ?? "—"}</td>
                <td className="num">{fmtNum(r.quantidade)}</td>
                <td className="num">{fmtBRL(r.preco_unitario)}</td>
                <td className="num" style={{ fontWeight: 600 }}>{fmtBRL(r.volume)}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={9} style={{ color: "var(--text3)" }}>
                  Nenhuma negociação encontrada.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
