"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Alert } from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  buyback_new: "Recompra declarada",
  insider_buy: "Insider comprando",
  fund_reopened: "Fundo reabriu posição",
};

const TYPE_OPTIONS = [
  { value: "", label: "Todos" },
  { value: "buyback_new", label: "Recompras" },
  { value: "insider_buy", label: "Insiders" },
  { value: "fund_reopened", label: "Fundos" },
];

const TYPE_SOURCE: Record<string, string> = {
  buyback_new: "CVM — Programas de Recompra",
  insider_buy: "CVM — VLMO (Negociações de Insiders)",
  fund_reopened: "CVM — CDA (Composição da Carteira dos Fundos)",
};

function formatDetectedAt(iso: string): string {
  const d = new Date(iso + (iso.endsWith("Z") ? "" : "Z"));
  return d.toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
}

function severityColor(sev: string) {
  if (sev === "success") return "var(--green)";
  if (sev === "warning") return "var(--amber)";
  return "var(--gold)";
}

function entityHref(a: Alert): string | null {
  if (a.entity_type === "fund" && a.entity_id) return `/fundos/${a.entity_id}`;
  return null;
}

export default function AlertasPage() {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [onlyUnread, setOnlyUnread] = useState(true);
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      api
        .getAlerts(onlyUnread, type, q)
        .then(setAlerts)
        .catch(() => setAlerts([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [onlyUnread, type, q]);

  function load() {
    setLoading(true);
    api
      .getAlerts(onlyUnread, type, q)
      .then(setAlerts)
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
  }

  function markRead(id: number) {
    api.markAlertRead(id).then(() => setAlerts((prev) => prev.map((a) => (a.id === id ? { ...a, is_read: true } : a))));
  }

  function markAllRead() {
    api.markAllAlertsRead().then(load);
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div>
          <h1 className="text-xl font-bold">Alertas</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
            Gerado automaticamente a partir dos dados já rastreados: novo programa de recompra, insider comprando
            acima de R$ 100 mil, fundo reabrindo uma posição que tinha zerado.
          </p>
        </div>
        <button className="smb-card px-3 py-1.5 text-sm" style={{ color: "var(--text2)" }} onClick={markAllRead}>
          Marcar tudo como lido
        </button>
      </div>

      <input
        className="smb-card w-full px-4 py-2 outline-none"
        placeholder="Buscar por ticker, empresa ou fundo..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <div className="smb-card p-3 flex flex-wrap gap-3 items-end">
        <button
          className="smb-card px-3 py-1.5 text-sm"
          style={{ color: onlyUnread ? "var(--gold)" : "var(--text2)" }}
          onClick={() => setOnlyUnread(!onlyUnread)}
        >
          {onlyUnread ? "Mostrando não lidos" : "Mostrando todos"}
        </button>
        <div className="flex gap-2">
          {TYPE_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setType(o.value)}
              className="smb-card px-3 py-1.5 text-sm"
              style={{ color: type === o.value ? "var(--gold)" : "var(--text2)" }}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-2">
        {alerts.map((a) => {
          const href = entityHref(a);
          const content = (
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="smb-badge" style={{ color: severityColor(a.severity), border: `1px solid ${severityColor(a.severity)}` }}>
                    {TYPE_LABELS[a.type] ?? a.type}
                  </span>
                  <span className="text-xs" style={{ color: "var(--text3)" }}>
                    Público em {a.ref_date}
                  </span>
                  {!a.is_read && <span className="w-2 h-2 rounded-full" style={{ background: "var(--gold)" }} />}
                </div>
                <div className="font-semibold mt-1" style={{ color: "var(--text)" }}>
                  {a.title}
                </div>
                {a.message && (
                  <div className="text-sm mt-0.5" style={{ color: "var(--text2)" }}>
                    {a.message}
                  </div>
                )}
                <div className="text-xs mt-1.5" style={{ color: "var(--text3)" }}>
                  Detectado em {formatDetectedAt(a.created_at)} · Fonte: {TYPE_SOURCE[a.type] ?? "CVM"}
                </div>
              </div>
              {!a.is_read && (
                <button
                  className="text-xs px-2 py-1 shrink-0"
                  style={{ color: "var(--text3)" }}
                  onClick={(e) => {
                    e.preventDefault();
                    markRead(a.id);
                  }}
                >
                  marcar lido
                </button>
              )}
            </div>
          );
          return (
            <div key={a.id} className="smb-card p-4" style={{ opacity: a.is_read ? 0.6 : 1 }}>
              {href ? (
                <Link href={href} onClick={() => !a.is_read && markRead(a.id)}>
                  {content}
                </Link>
              ) : (
                content
              )}
            </div>
          );
        })}
        {!loading && alerts.length === 0 && (
          <div className="smb-card p-4 text-sm" style={{ color: "var(--text3)" }}>
            Nenhum alerta {onlyUnread ? "não lido" : ""} no momento.
          </div>
        )}
      </div>
    </div>
  );
}
