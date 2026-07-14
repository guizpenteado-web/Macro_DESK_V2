"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Fund, FundSortField } from "@/lib/api";
import SortableTh from "@/components/SortableTh";

function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

function fmtPct(v: number | null) {
  if (v === null || v === undefined) return "—";
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
}

function NumField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text3)" }}>
      {label}
      <input
        type="number"
        className="smb-card px-2 py-1 outline-none text-sm"
        style={{ color: "var(--text)" }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

export default function FundosPage() {
  const [q, setQ] = useState("");
  const [minNav, setMinNav] = useState("");
  const [minShareholders, setMinShareholders] = useState("");
  const [maxShareholders, setMaxShareholders] = useState("");
  const [minReturn, setMinReturn] = useState("");
  const [maxReturn, setMaxReturn] = useState("");
  const [sortBy, setSortBy] = useState<FundSortField>("name");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const [funds, setFunds] = useState<Fund[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      api
        .searchFunds({
          search: q,
          minNetAssetValue: minNav ? Number(minNav) : undefined,
          minShareholders: minShareholders ? Number(minShareholders) : undefined,
          maxShareholders: maxShareholders ? Number(maxShareholders) : undefined,
          minReturnPct: minReturn ? Number(minReturn) : undefined,
          maxReturnPct: maxReturn ? Number(maxReturn) : undefined,
          sortBy,
          sortDir,
          limit: 50,
        })
        .then((r) => {
          setFunds(r);
          setError(null);
        })
        .catch((e) => {
          setFunds([]);
          setError(String(e?.message ?? e));
        })
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [q, minNav, minShareholders, maxShareholders, minReturn, maxReturn, sortBy, sortDir]);

  function toggleSort(field: FundSortField) {
    if (field === sortBy) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("asc");
    }
  }

  function clearFilters() {
    setMinNav("");
    setMinShareholders("");
    setMaxShareholders("");
    setMinReturn("");
    setMaxReturn("");
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Fundos</h1>
      {error && (
        <div className="smb-card p-3 text-sm" style={{ color: "var(--red)", border: "1px solid var(--red)" }}>
          Erro ao buscar fundos: {error}
        </div>
      )}
      <input
        className="smb-card w-full px-4 py-2 outline-none"
        placeholder="Buscar por nome ou CNPJ..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <div className="smb-card p-3 flex flex-wrap gap-3 items-end">
        <NumField label="Patrimônio líq. mín (R$)" value={minNav} onChange={setMinNav} />
        <NumField label="Cotistas mín" value={minShareholders} onChange={setMinShareholders} />
        <NumField label="Cotistas máx" value={maxShareholders} onChange={setMaxShareholders} />
        <NumField label="Retorno 12m mín (%)" value={minReturn} onChange={setMinReturn} />
        <NumField label="Retorno 12m máx (%)" value={maxReturn} onChange={setMaxReturn} />
        <button className="smb-card px-3 py-1.5 text-sm" style={{ color: "var(--text3)" }} onClick={clearFilters}>
          Limpar filtros
        </button>
      </div>

      <div className="smb-card smb-table-wrap">
        <table className="smb-table w-full">
          <thead>
            <tr>
              <SortableTh label="Nome" active={sortBy === "name"} dir={sortDir} onClick={() => toggleSort("name")} />
              <th>CNPJ</th>
              <th>Tipo</th>
              <SortableTh label="Patrimônio líquido" align="right" active={sortBy === "net_asset_value"} dir={sortDir} onClick={() => toggleSort("net_asset_value")} />
              <SortableTh label="Cotistas" align="right" active={sortBy === "n_shareholders"} dir={sortDir} onClick={() => toggleSort("n_shareholders")} />
              <SortableTh label="Rent. Mês" align="right" active={sortBy === "return_pct_mtd"} dir={sortDir} onClick={() => toggleSort("return_pct_mtd")} />
              <SortableTh label="Rent. Ano" align="right" active={sortBy === "return_pct_ytd"} dir={sortDir} onClick={() => toggleSort("return_pct_ytd")} />
              <SortableTh label="Retorno (12m)" align="right" active={sortBy === "return_pct_12m"} dir={sortDir} onClick={() => toggleSort("return_pct_12m")} />
              <SortableTh label="Divulgação" align="right" active={sortBy === "financials_ref_date"} dir={sortDir} onClick={() => toggleSort("financials_ref_date")} />
            </tr>
          </thead>
          <tbody>
            {funds.map((f) => (
              <tr key={f.id}>
                <td>
                  <Link href={`/fundos/${f.id}`} style={{ color: "var(--gold)" }}>
                    {f.name}
                  </Link>
                </td>
                <td style={{ color: "var(--text2)" }}>{f.cnpj}</td>
                <td style={{ color: "var(--text3)" }}>{f.fund_class_type}</td>
                <td className="num">{f.net_asset_value !== null ? fmtBRL(f.net_asset_value) : "—"}</td>
                <td className="num">{f.n_shareholders !== null ? f.n_shareholders.toLocaleString("pt-BR") : "—"}</td>
                <td className="num" style={{ color: (f.return_pct_mtd ?? 0) >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                  {fmtPct(f.return_pct_mtd)}
                </td>
                <td className="num" style={{ color: (f.return_pct_ytd ?? 0) >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                  {fmtPct(f.return_pct_ytd)}
                </td>
                <td className="num" style={{ color: (f.return_pct_12m ?? 0) >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                  {fmtPct(f.return_pct_12m)}
                </td>
                <td className="num" style={{ color: "var(--text3)" }}>{f.financials_ref_date ?? "—"}</td>
              </tr>
            ))}
            {!loading && funds.length === 0 && (
              <tr>
                <td colSpan={9} style={{ color: "var(--text3)" }}>
                  Nenhum fundo encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
