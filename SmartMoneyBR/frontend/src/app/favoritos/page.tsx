"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Fund } from "@/lib/api";

function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

function fmtPct(v: number | null) {
  if (v === null || v === undefined) return "—";
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
}

export default function FavoritosPage() {
  const [funds, setFunds] = useState<Fund[]>([]);
  const [loading, setLoading] = useState(true);

  function load() {
    setLoading(true);
    api
      .getFavorites()
      .then((ids) => Promise.all(ids.map((id) => api.getFund(id).catch(() => null))))
      .then((results) => setFunds(results.filter((f): f is Fund => f !== null)))
      .catch(() => setFunds([]))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  function unfavorite(fundId: number) {
    api.removeFavorite(fundId).then(() => setFunds((prev) => prev.filter((f) => f.id !== fundId)));
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Favoritos</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
          Fundos marcados com ⭐ na própria página do fundo. Lista compartilhada entre quem tem acesso de administração.
        </p>
      </div>

      <div className="smb-card smb-table-wrap">
        <table className="smb-table w-full">
          <thead>
            <tr>
              <th>Nome</th>
              <th>CNPJ</th>
              <th>Tipo</th>
              <th className="num">Patrimônio líquido</th>
              <th className="num">Cotistas</th>
              <th className="num">Rent. Mês</th>
              <th className="num">Rent. Ano</th>
              <th className="num">Retorno (12m)</th>
              <th></th>
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
                <td className="num">
                  <button
                    onClick={() => unfavorite(f.id)}
                    title="Remover dos favoritos"
                    style={{ color: "var(--gold)", fontSize: 16 }}
                  >
                    ★
                  </button>
                </td>
              </tr>
            ))}
            {!loading && funds.length === 0 && (
              <tr>
                <td colSpan={9} style={{ color: "var(--text3)" }}>
                  Nenhum fundo favoritado ainda. Marque um fundo com ⭐ na própria página dele.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
