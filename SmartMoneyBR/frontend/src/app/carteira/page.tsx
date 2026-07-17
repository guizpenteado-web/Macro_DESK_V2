"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, Asset } from "@/lib/api";

function fmtBRLmi(v: number) {
  return `R$ ${(v / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}mi`;
}

function fmtPct(v: number | null) {
  if (v === null || v === undefined) return "—";
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
}

export default function CarteiraPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const [q, setQ] = useState("");
  const [results, setResults] = useState<Asset[]>([]);
  const [searching, setSearching] = useState(false);
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  function load() {
    setLoading(true);
    setError(false);
    api
      .getPortfolio()
      .then((ids) => Promise.all(ids.map((id) => api.getAsset(id).catch(() => null))))
      .then((res) => setAssets(res.filter((a): a is Asset => a !== null)))
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    setSearching(true);
    const handle = setTimeout(() => {
      api
        .searchAssets({ search: q, limit: 8 })
        .then(setResults)
        .catch(() => setResults([]))
        .finally(() => setSearching(false));
    }, 250);
    return () => clearTimeout(handle);
  }, [q]);

  function addAsset(assetId: number) {
    api.addToPortfolio(assetId).then(() => {
      setQ("");
      setResults([]);
      setOpen(false);
      load();
    });
  }

  function removeAsset(assetId: number) {
    api.removeFromPortfolio(assetId).then(() => setAssets((prev) => prev.filter((a) => a.id !== assetId)));
  }

  const inPortfolio = new Set(assets.map((a) => a.id));

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Carteira</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
          Ações ou BDRs que você quer acompanhar. Lista pessoal — só você vê os ativos que adicionar aqui.
        </p>
      </div>

      <div ref={boxRef} className="relative smb-card p-3">
        <input
          className="w-full px-3 py-2 text-sm outline-none"
          style={{ background: "var(--bg3)", color: "var(--text)", borderRadius: 8 }}
          placeholder="Buscar ticker ou empresa pra adicionar..."
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onFocus={() => setOpen(true)}
        />
        {open && q.trim().length >= 2 && (
          <div
            className="smb-card absolute mt-1 overflow-hidden"
            style={{ width: "100%", left: 0, maxHeight: 320, overflowY: "auto", zIndex: 50 }}
          >
            {searching && (
              <div className="px-3 py-2 text-xs" style={{ color: "var(--text3)" }}>
                Buscando...
              </div>
            )}
            {!searching && results.length === 0 && (
              <div className="px-3 py-2 text-xs" style={{ color: "var(--text3)" }}>
                Nada encontrado para &quot;{q}&quot;.
              </div>
            )}
            {results.map((a) => {
              const already = inPortfolio.has(a.id);
              return (
                <button
                  key={a.id}
                  onClick={() => !already && addAsset(a.id)}
                  disabled={already}
                  className="w-full px-3 py-2 text-sm flex items-center justify-between gap-2 text-left"
                  style={{ cursor: already ? "default" : "pointer" }}
                >
                  <span className="flex-1 min-w-0">
                    <span style={{ color: "var(--gold)", fontWeight: 600 }}>{a.ticker}</span>
                    {a.company_name && (
                      <span className="ml-2 text-xs" style={{ color: "var(--text3)" }}>
                        {a.company_name}
                      </span>
                    )}
                  </span>
                  <span className="text-xs shrink-0" style={{ color: already ? "var(--text3)" : "var(--gold)" }}>
                    {already ? "já na carteira" : "+ adicionar"}
                  </span>
                </button>
              );
            })}
          </div>
        )}
      </div>

      <div className="smb-card smb-table-wrap">
        <table className="smb-table w-full">
          <thead>
            <tr>
              <th>Ticker</th>
              <th>Empresa</th>
              <th>Tipo</th>
              <th className="num">Valor de mercado (posição agregada)</th>
              <th className="num">Retorno (12m)</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {assets.map((a) => (
              <tr key={a.id}>
                <td>
                  <Link href={`/ativos/${a.id}`} style={{ color: "var(--gold)", fontWeight: 600 }}>
                    {a.ticker}
                  </Link>
                </td>
                <td style={{ color: "var(--text2)" }}>{a.company_name ?? "—"}</td>
                <td>
                  {a.asset_type === "bdr" ? (
                    <span className="smb-badge" style={{ color: "var(--amber)", border: "1px solid var(--amber)" }}>
                      BDR
                    </span>
                  ) : (
                    <span style={{ color: "var(--text3)" }}>Ação</span>
                  )}
                </td>
                <td className="num">{a.total_market_value !== null ? fmtBRLmi(a.total_market_value) : "—"}</td>
                <td className="num" style={{ color: (a.return_pct_12m ?? 0) >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                  {fmtPct(a.return_pct_12m)}
                </td>
                <td className="num">
                  <button
                    onClick={() => removeAsset(a.id)}
                    title="Remover da carteira"
                    className="smb-card"
                    style={{
                      color: "var(--red)",
                      width: 26,
                      height: 26,
                      lineHeight: "24px",
                      textAlign: "center",
                      padding: 0,
                      borderRadius: 6,
                    }}
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))}
            {!loading && !error && assets.length === 0 && (
              <tr>
                <td colSpan={6} style={{ color: "var(--text3)" }}>
                  Nenhum ativo na carteira ainda. Busque um ticker acima pra adicionar.
                </td>
              </tr>
            )}
            {error && (
              <tr>
                <td colSpan={6} style={{ color: "var(--red)" }}>
                  Não foi possível carregar a carteira. É preciso estar logado no Hub.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
