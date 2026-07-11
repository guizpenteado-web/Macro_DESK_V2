"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Asset, AssetSortField } from "@/lib/api";

function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

function fmtPct(v: number | null) {
  if (v === null || v === undefined) return "—";
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
}

const SORT_OPTIONS: { value: AssetSortField; label: string }[] = [
  { value: "ticker", label: "Ticker" },
  { value: "total_market_value", label: "Valor total em carteira" },
  { value: "return_pct_12m", label: "Retorno (12m)" },
];

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

const TYPE_OPTIONS: { value: "equity" | "bdr" | ""; label: string }[] = [
  { value: "", label: "Todos" },
  { value: "equity", label: "Ações" },
  { value: "bdr", label: "BDRs" },
];

export default function AtivosPage() {
  const [q, setQ] = useState("");
  const [assetType, setAssetType] = useState<"equity" | "bdr" | "">("");
  const [minValue, setMinValue] = useState("");
  const [minReturn, setMinReturn] = useState("");
  const [maxReturn, setMaxReturn] = useState("");
  const [sortBy, setSortBy] = useState<AssetSortField>("ticker");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const [assets, setAssets] = useState<Asset[]>([]);

  useEffect(() => {
    const handle = setTimeout(() => {
      api
        .searchAssets({
          search: q,
          assetType,
          minTotalMarketValue: minValue ? Number(minValue) : undefined,
          minReturnPct: minReturn ? Number(minReturn) : undefined,
          maxReturnPct: maxReturn ? Number(maxReturn) : undefined,
          sortBy,
          sortDir,
          limit: 60,
        })
        .then(setAssets)
        .catch(() => setAssets([]));
    }, 300);
    return () => clearTimeout(handle);
  }, [q, assetType, minValue, minReturn, maxReturn, sortBy, sortDir]);

  function clearFilters() {
    setMinValue("");
    setMinReturn("");
    setMaxReturn("");
  }

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold">Ativos</h1>
      <input
        className="smb-card w-full px-4 py-2 outline-none"
        placeholder="Buscar por ticker (ex: PETR4)..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <div className="smb-card p-3 flex flex-wrap gap-3 items-end">
        <div className="flex gap-2">
          {TYPE_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setAssetType(o.value)}
              className="smb-card px-3 py-1.5 text-sm"
              style={{ color: assetType === o.value ? "var(--cyan)" : "var(--text2)" }}
            >
              {o.label}
            </button>
          ))}
        </div>
        <NumField label="Valor total em carteira mín (R$)" value={minValue} onChange={setMinValue} />
        <NumField label="Retorno 12m mín (%)" value={minReturn} onChange={setMinReturn} />
        <NumField label="Retorno 12m máx (%)" value={maxReturn} onChange={setMaxReturn} />

        <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text3)" }}>
          Ordenar por
          <select
            className="smb-card px-2 py-1 outline-none text-sm"
            style={{ color: "var(--text)" }}
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as AssetSortField)}
          >
            {SORT_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <button
          className="smb-card px-3 py-1.5 text-sm"
          style={{ color: "var(--text2)" }}
          onClick={() => setSortDir(sortDir === "asc" ? "desc" : "asc")}
        >
          {sortDir === "asc" ? "↑ Crescente" : "↓ Decrescente"}
        </button>
        <button className="smb-card px-3 py-1.5 text-sm" style={{ color: "var(--text3)" }} onClick={clearFilters}>
          Limpar filtros
        </button>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {assets.map((a) => (
          <Link key={a.id} href={`/ativos/${a.id}`} className="smb-card p-4 block hover:opacity-90">
            <div className="flex items-center gap-1.5">
              <span className="font-bold" style={{ color: "var(--cyan)" }}>
                {a.ticker}
              </span>
              {a.asset_type === "bdr" && (
                <span className="smb-badge" style={{ color: "var(--amber)", border: "1px solid var(--amber)", fontSize: "9px" }}>
                  BDR
                </span>
              )}
            </div>
            <div className="text-xs truncate" style={{ color: "var(--text3)" }}>
              {a.company_name}
            </div>
            <div className="text-xs mt-2" style={{ color: "var(--text2)" }}>
              {a.total_market_value !== null ? fmtBRL(a.total_market_value) : "—"}
            </div>
            <div
              className="text-xs font-semibold"
              style={{ color: (a.return_pct_12m ?? 0) >= 0 ? "var(--green)" : "var(--red)" }}
            >
              {fmtPct(a.return_pct_12m)}
            </div>
          </Link>
        ))}
        {assets.length === 0 && (
          <div className="col-span-full text-sm" style={{ color: "var(--text3)" }}>
            Nenhum ativo encontrado.
          </div>
        )}
      </div>
    </div>
  );
}
