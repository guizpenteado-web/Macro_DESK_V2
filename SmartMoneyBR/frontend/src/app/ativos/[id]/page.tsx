"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { api, Asset, AssetHolder, AssetTimelinePoint } from "@/lib/api";
import MovementBadge from "@/components/MovementBadge";
import SortableTh from "@/components/SortableTh";
import { sortRows, useSort } from "@/lib/sort";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

function fmtPct(v: number | null) {
  if (v === null) return "—";
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}%`;
}

export default function AssetDetailPage() {
  const params = useParams();
  const assetId = Number(params.id);

  const [asset, setAsset] = useState<Asset | null>(null);
  const [holders, setHolders] = useState<AssetHolder[]>([]);
  const [timeline, setTimeline] = useState<AssetTimelinePoint[]>([]);
  const [flow, setFlow] = useState<{ net_qty_delta: number; net_value_delta: number; n_funds_buying: number; n_funds_selling: number } | null>(null);

  const holdersSort = useSort<"fund_name" | "classification" | "quantity" | "market_value" | "pct_of_fund" | "fund_net_asset_value" | "fund_n_shareholders">();
  const holdersWithPct = holders.map((h) => ({
    ...h,
    pct_of_fund: h.fund_net_asset_value ? (h.market_value / h.fund_net_asset_value) * 100 : null,
  }));
  const sortedHolders = holdersSort.sortKey
    ? sortRows(holdersWithPct, (h) => h[holdersSort.sortKey!], holdersSort.sortDir)
    : holdersWithPct;

  useEffect(() => {
    if (!assetId) return;
    api.getAsset(assetId).then(setAsset);
    api.getAssetHolders(assetId).then(setHolders);
    api.getAssetTimeline(assetId).then(setTimeline);
    api.getAssetMovements(assetId).then(setFlow);
  }, [assetId]);

  // CDA (posicao de carteira dos fundos) e revisado pela CVM por semanas apos
  // o fim de cada mes conforme administradoras entregam declaracoes atrasadas
  // — os ultimos 3 meses de competencia sempre aparecem artificialmente baixos
  // e sobem sozinhos com o tempo. Mesma janela que o job de reingestao usa
  // (job_cda_recent, backend). Marcamos visualmente pra nao parecer venda real.
  const PROVISIONAL_MONTHS = 3;
  const provisionalFrom = Math.max(0, timeline.length - PROVISIONAL_MONTHS);

  const chartOption = {
    backgroundColor: "transparent",
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: { type: "category", data: timeline.map((t) => t.ref_date), axisLine: { lineStyle: { color: "#565f75" } } },
    yAxis: { type: "value", axisLine: { lineStyle: { color: "#565f75" } }, splitLine: { lineStyle: { color: "#232838" } } },
    tooltip: { trigger: "axis" },
    series: [
      {
        name: "Nº de fundos detentores",
        type: "line",
        data: timeline.map((t) => t.n_holders),
        lineStyle: { color: "#00e5ff" },
        itemStyle: { color: "#00e5ff" },
        areaStyle: { color: "rgba(0,229,255,0.08)" },
        markArea:
          timeline.length > PROVISIONAL_MONTHS
            ? {
                itemStyle: { color: "rgba(255,183,0,0.08)" },
                data: [[{ xAxis: timeline[provisionalFrom].ref_date }, { xAxis: timeline[timeline.length - 1].ref_date }]],
              }
            : undefined,
      },
    ],
  };

  if (!asset) return <div style={{ color: "var(--text2)" }}>Carregando...</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold flex items-center gap-2">
          {asset.ticker}
          {asset.asset_type === "bdr" && (
            <span className="smb-badge" style={{ color: "var(--amber)", border: "1px solid var(--amber)" }}>
              BDR
            </span>
          )}
          <span style={{ color: "var(--text3)", fontWeight: 400 }}>{asset.company_name}</span>
        </h1>
      </div>

      {flow && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="smb-card p-4">
            <div className="text-xs" style={{ color: "var(--text3)" }}>Fluxo líquido (valor)</div>
            <div className="font-bold" style={{ color: flow.net_value_delta >= 0 ? "var(--green)" : "var(--red)" }}>
              {fmtBRL(flow.net_value_delta)}
            </div>
          </div>
          <div className="smb-card p-4">
            <div className="text-xs" style={{ color: "var(--text3)" }}>Fundos comprando</div>
            <div className="font-bold" style={{ color: "var(--green)" }}>{flow.n_funds_buying}</div>
          </div>
          <div className="smb-card p-4">
            <div className="text-xs" style={{ color: "var(--text3)" }}>Fundos vendendo</div>
            <div className="font-bold" style={{ color: "var(--red)" }}>{flow.n_funds_selling}</div>
          </div>
          <div className="smb-card p-4">
            <div className="text-xs" style={{ color: "var(--text3)" }}>Total de detentores</div>
            <div className="font-bold">{timeline.at(-1)?.n_holders ?? "—"}</div>
          </div>
        </div>
      )}

      <div className="smb-card p-4">
        <div className="font-semibold mb-2">Timeline — nº de fundos detentores</div>
        <ReactECharts option={chartOption} style={{ height: 240 }} />
        {timeline.length > PROVISIONAL_MONTHS && (
          <div className="text-xs mt-2" style={{ color: "var(--amber)" }}>
            Área sombreada = últimos {PROVISIONAL_MONTHS} meses. A CVM ainda está recebendo declarações atrasadas de
            fundos para esse período — os números tendem a subir nas próximas semanas, não é necessariamente venda real.
          </div>
        )}
      </div>

      <div>
        <div className="flex items-center gap-2 mb-2">
          <h2 className="font-semibold">Detentores</h2>
          {holders[0] && (
            <span className="text-xs" style={{ color: "var(--text3)" }}>
              (posição divulgada em: {holders[0].ref_date})
            </span>
          )}
        </div>
        <div className="smb-card smb-table-wrap">
          <table className="smb-table w-full">
            <thead>
              <tr>
                <SortableTh label="Fundo" active={holdersSort.sortKey === "fund_name"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("fund_name")} />
                <SortableTh label="Status" active={holdersSort.sortKey === "classification"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("classification")} />
                <SortableTh label="Qtd" align="right" active={holdersSort.sortKey === "quantity"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("quantity")} />
                <SortableTh label="Valor" align="right" active={holdersSort.sortKey === "market_value"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("market_value")} />
                <SortableTh label="% do PL do fundo" align="right" active={holdersSort.sortKey === "pct_of_fund"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("pct_of_fund")} />
                <SortableTh label="Patrimônio do fundo" align="right" active={holdersSort.sortKey === "fund_net_asset_value"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("fund_net_asset_value")} />
                <SortableTh label="Cotistas" align="right" active={holdersSort.sortKey === "fund_n_shareholders"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("fund_n_shareholders")} />
              </tr>
            </thead>
            <tbody>
              {sortedHolders.map((h) => (
                <tr key={h.fund_id}>
                  <td>
                    <Link href={`/fundos/${h.fund_id}`} style={{ color: "var(--cyan)" }}>
                      {h.fund_name}
                    </Link>
                  </td>
                  <td>{h.classification && <MovementBadge classification={h.classification} />}</td>
                  <td className="num">{h.quantity.toLocaleString("pt-BR")}</td>
                  <td className="num">{fmtBRL(h.market_value)}</td>
                  <td className="num" style={{ fontWeight: 600 }}>{fmtPct(h.pct_of_fund)}</td>
                  <td className="num" style={{ color: "var(--text2)" }}>{h.fund_net_asset_value !== null ? fmtBRL(h.fund_net_asset_value) : "—"}</td>
                  <td className="num" style={{ color: "var(--text2)" }}>{h.fund_n_shareholders !== null ? h.fund_n_shareholders.toLocaleString("pt-BR") : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
