"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Asset, Fund } from "@/lib/api";

export default function GlobalSearch() {
  const router = useRouter();
  const boxRef = useRef<HTMLDivElement>(null);

  const [q, setQ] = useState("");
  const [assets, setAssets] = useState<Asset[]>([]);
  const [funds, setFunds] = useState<Fund[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  useEffect(() => {
    if (q.trim().length < 2) {
      setAssets([]);
      setFunds([]);
      return;
    }
    setLoading(true);
    const handle = setTimeout(() => {
      Promise.all([
        api.searchAssets({ search: q, limit: 6 }),
        api.searchFunds({ search: q, limit: 6 }),
      ])
        .then(([a, f]) => {
          setAssets(a);
          setFunds(f);
        })
        .catch(() => {
          setAssets([]);
          setFunds([]);
        })
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(handle);
  }, [q]);

  function goToAsset(id: number) {
    setOpen(false);
    setQ("");
    router.push(`/ativos/${id}`);
  }

  function goToFund(id: number) {
    setOpen(false);
    setQ("");
    router.push(`/fundos/${id}`);
  }

  const hasResults = assets.length > 0 || funds.length > 0;

  return (
    <div ref={boxRef} className="relative">
      <input
        className="smb-card px-3 py-1.5 text-sm outline-none"
        style={{ width: 220, color: "var(--text)" }}
        placeholder="Buscar ticker ou fundo..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
        onFocus={() => setOpen(true)}
      />
      {open && q.trim().length >= 2 && (
        <div
          className="smb-card absolute mt-1 overflow-hidden"
          style={{ width: 340, maxHeight: 360, overflowY: "auto", zIndex: 50, right: 0 }}
        >
          {loading && (
            <div className="px-3 py-2 text-xs" style={{ color: "var(--text3)" }}>
              Buscando...
            </div>
          )}
          {!loading && !hasResults && (
            <div className="px-3 py-2 text-xs" style={{ color: "var(--text3)" }}>
              Nada encontrado para &quot;{q}&quot;.
            </div>
          )}
          {assets.length > 0 && (
            <div>
              <div className="px-3 pt-2 pb-1 text-xs font-semibold" style={{ color: "var(--text3)" }}>
                Ativos
              </div>
              {assets.map((a) => (
                <button
                  key={a.id}
                  onClick={() => goToAsset(a.id)}
                  className="w-full text-left px-3 py-2 text-sm flex items-center justify-between"
                  style={{ color: "var(--text)" }}
                  onMouseDown={(e) => e.preventDefault()}
                >
                  <span>
                    <span style={{ color: "var(--cyan)", fontWeight: 600 }}>{a.ticker}</span>
                    {a.company_name && (
                      <span className="ml-2 text-xs" style={{ color: "var(--text3)" }}>
                        {a.company_name}
                      </span>
                    )}
                  </span>
                  {a.asset_type === "bdr" && (
                    <span className="smb-badge" style={{ color: "var(--amber)", border: "1px solid var(--amber)" }}>
                      BDR
                    </span>
                  )}
                </button>
              ))}
            </div>
          )}
          {funds.length > 0 && (
            <div>
              <div className="px-3 pt-2 pb-1 text-xs font-semibold" style={{ color: "var(--text3)" }}>
                Fundos
              </div>
              {funds.map((f) => (
                <button
                  key={f.id}
                  onClick={() => goToFund(f.id)}
                  className="w-full text-left px-3 py-2 text-sm"
                  style={{ color: "var(--text)" }}
                  onMouseDown={(e) => e.preventDefault()}
                >
                  {f.name}
                  <div className="text-xs" style={{ color: "var(--text3)" }}>
                    {f.cnpj}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
