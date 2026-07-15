"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { api, Asset, AssetHolder, AssetTimelinePoint } from "@/lib/api";
import FundAssetPositionChart from "@/components/FundAssetPositionChart";
import MovementBadge from "@/components/MovementBadge";
import SortableTh from "@/components/SortableTh";
import { sortRows, useSort } from "@/lib/sort";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const TOP_N = 10;

function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

function fmtBRLmi(v: number) {
  return `${(v / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}mi`;
}

function fmtPct(v: number | null) {
  if (v === null) return "—";
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}%`;
}

function fmtPrice(v: number | null) {
  if (v === null) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function truncateName(name: string, max = 30) {
  return name.length > max ? name.slice(0, max - 1) + "…" : name;
}

const MONTH_ABBR = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];
function fmtMonth(dateStr: string) {
  const [y, m] = dateStr.split("-");
  return `${MONTH_ABBR[Number(m) - 1]}/${y.slice(2)}`;
}

export default function AssetDetailPage() {
  const params = useParams();
  const assetId = Number(params.id);

  const [asset, setAsset] = useState<Asset | null>(null);
  const [holders, setHolders] = useState<AssetHolder[]>([]);
  const [timeline, setTimeline] = useState<AssetTimelinePoint[]>([]);
  const [flow, setFlow] = useState<{ net_qty_delta: number; net_value_delta: number; n_funds_buying: number; n_funds_selling: number } | null>(null);
  const [topMetric, setTopMetric] = useState<"pct" | "valor">("pct");

  const [selectedFund, setSelectedFund] = useState<{ id: number; name: string } | null>(null);
  const [fundSearch, setFundSearch] = useState("");
  const [direction, setDirection] = useState<"comprados" | "vendidos">("comprados");
  const [showZeroed, setShowZeroed] = useState(false);
  const [monthFilter, setMonthFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"" | "NEW" | "INCREASED" | "DECREASED" | "UNCHANGED">("");

  // "Vendidos" so existe entre as posicoes zeradas — precisa desse dado do
  // backend independente do toggle "Exibir Zeradas" (que so afeta a aba
  // Comprados, misturando as zeradas junto).
  const includeClosed = showZeroed || direction === "vendidos";

  const holdersSort = useSort<"fund_name" | "classification" | "quantity" | "market_value" | "price_at_ref_date" | "pct_of_fund" | "fund_net_asset_value" | "fund_n_shareholders" | "ref_date">();
  const holdersWithPct = holders.map((h) => ({
    ...h,
    pct_of_fund: h.fund_net_asset_value ? (h.market_value / h.fund_net_asset_value) * 100 : null,
  }));

  const availableMonths = Array.from(new Set(holders.map((h) => h.ref_date.slice(0, 7)))).sort().reverse();
  const mostRecentMonth = availableMonths[0];

  const filteredHolders = holdersWithPct.filter((h) => {
    if (direction === "vendidos" ? h.quantity !== 0 : !(showZeroed || h.quantity > 0)) return false;
    if (fundSearch && !h.fund_name.toLowerCase().includes(fundSearch.toLowerCase())) return false;
    if (monthFilter && h.ref_date.slice(0, 7) !== monthFilter) return false;
    if (statusFilter && h.classification !== statusFilter) return false;
    return true;
  });

  // Top N fundos com maior posição comprada nesse ativo — mesma ideia do
  // "Maiores Posições" de sites tipo CarteiraFundos.com, com toggle entre
  // % do PL do fundo e valor absoluto. Barra horizontal, maior no topo.
  const top10 = [...holdersWithPct]
    .filter((h) => (topMetric === "pct" ? h.pct_of_fund !== null : true))
    .sort((a, b) => (topMetric === "pct" ? (b.pct_of_fund ?? 0) - (a.pct_of_fund ?? 0) : b.market_value - a.market_value))
    .slice(0, TOP_N)
    .reverse(); // ECharts categoria desenha de baixo pra cima — reverso pra maior ficar no topo

  const topChartOption = {
    backgroundColor: "transparent",
    grid: { left: 210, right: 50, top: 10, bottom: 30 },
    xAxis: {
      type: "value",
      axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
      splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } },
      axisLabel: {
        // ECharts desenha em canvas, nao em CSS/DOM — var(--x) do globals.css
        // nao resolve aqui (cai no preto padrao do canvas). Precisa ser hex
        // literal, sempre, em qualquer cor dentro do "option" do ECharts.
        color: "#4a5b73",
        formatter: (v: number) => (topMetric === "pct" ? `${v}%` : fmtBRLmi(v)),
      },
    },
    yAxis: {
      type: "category",
      data: top10.map((h) => truncateName(h.fund_name)),
      axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
      axisLabel: { color: "#c9a227", fontSize: 11 },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const arr = params as { dataIndex: number }[];
        const h = top10[arr[0].dataIndex];
        if (!h) return "";
        const leverageNote =
          (h.pct_of_fund ?? 0) > 100
            ? "<br/><span style=\"color:#8a8f98;font-size:11px\">fundo alavancado/colateralizado — PL líquido de dívida</span>"
            : "";
        return `${h.fund_name}<br/>% do PL: ${fmtPct(h.pct_of_fund)}<br/>Valor: ${fmtBRL(h.market_value)}${leverageNote}`;
      },
    },
    series: [
      {
        type: "bar",
        data: top10.map((h) => (topMetric === "pct" ? h.pct_of_fund ?? 0 : h.market_value)),
        itemStyle: { color: "#c9a227", borderRadius: [0, 4, 4, 0] },
        barMaxWidth: 22,
      },
    ],
  };
  const sortedHolders = holdersSort.sortKey
    ? sortRows(filteredHolders, (h) => h[holdersSort.sortKey!], holdersSort.sortDir)
    : filteredHolders;

  useEffect(() => {
    if (!assetId) return;
    api.getAsset(assetId).then(setAsset);
    api.getAssetTimeline(assetId).then(setTimeline);
    api.getAssetMovements(assetId).then(setFlow);
  }, [assetId]);

  useEffect(() => {
    if (!assetId) return;
    api.getAssetHolders(assetId, includeClosed).then(setHolders);
  }, [assetId, includeClosed]);

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

      {top10.length > 0 && (
        <div>
          <h2 className="font-semibold mb-2">Maiores Posições</h2>
          <div className="smb-card p-4">
            <div className="flex items-center justify-between flex-wrap gap-3 mb-4">
              <span
                className="smb-badge"
                style={{ color: "var(--green)", border: "1px solid var(--green)", padding: "4px 12px", fontSize: 12 }}
              >
                Comprados
              </span>
              <div className="text-xl font-bold text-center flex-1">{asset.ticker}</div>
              <div className="flex gap-2">
                <button
                  onClick={() => setTopMetric("pct")}
                  className="smb-card px-3 py-1.5 text-sm"
                  style={{ color: topMetric === "pct" ? "var(--gold)" : "var(--text2)" }}
                >
                  % PL
                </button>
                <button
                  onClick={() => setTopMetric("valor")}
                  className="smb-card px-3 py-1.5 text-sm"
                  style={{ color: topMetric === "valor" ? "var(--gold)" : "var(--text2)" }}
                >
                  Valor
                </button>
              </div>
            </div>
            <ReactECharts option={topChartOption} style={{ height: TOP_N * 34 + 40 }} notMerge />
            {topMetric === "pct" && top10.some((h) => (h.pct_of_fund ?? 0) > 100) && (
              <div className="text-xs mt-2" style={{ color: "var(--text3)" }}>
                % acima de 100% pode ocorrer em fundos com estrutura de dívida/alavancagem
                que usam o ativo como garantia — o patrimônio líquido divulgado pela CVM já é
                líquido dessas obrigações, podendo ficar menor que o valor de mercado da posição.
              </div>
            )}
          </div>
        </div>
      )}

      {selectedFund && asset && (
        <div className="smb-card p-4">
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold">
              Evolução da posição de <span style={{ color: "var(--gold)" }}>{selectedFund.name}</span> em {asset.ticker}
            </div>
            <button onClick={() => setSelectedFund(null)} style={{ color: "var(--text3)" }}>
              fechar ✕
            </button>
          </div>
          <FundAssetPositionChart fundId={selectedFund.id} assetId={assetId} ticker={asset.ticker} />
        </div>
      )}

      <div>
        <h2 className="font-semibold mb-2">Detalhes das Posições</h2>

        <div className="smb-card p-3 flex flex-wrap gap-3 items-center mb-3">
          <input
            className="smb-card px-3 py-1.5 text-sm outline-none"
            style={{ minWidth: 220, color: "var(--text)" }}
            placeholder="Buscar fundo..."
            value={fundSearch}
            onChange={(e) => setFundSearch(e.target.value)}
          />
          <div className="flex gap-2">
            <button
              onClick={() => setDirection("comprados")}
              className="smb-card px-3 py-1.5 text-sm"
              style={{ color: direction === "comprados" ? "var(--green)" : "var(--text2)", borderColor: direction === "comprados" ? "var(--green)" : undefined }}
            >
              Comprados
            </button>
            <button
              onClick={() => setDirection("vendidos")}
              className="smb-card px-3 py-1.5 text-sm"
              style={{ color: direction === "vendidos" ? "var(--red)" : "var(--text2)", borderColor: direction === "vendidos" ? "var(--red)" : undefined }}
            >
              Vendidos
            </button>
          </div>
          <select
            className="smb-card px-2 py-1.5 outline-none text-sm"
            style={{ color: "var(--text)" }}
            value={monthFilter}
            onChange={(e) => setMonthFilter(e.target.value)}
          >
            <option value="">Filtrar mês: todos</option>
            {availableMonths.map((m) => (
              <option key={m} value={m}>
                {fmtMonth(`${m}-01`)}
              </option>
            ))}
          </select>
          <select
            className="smb-card px-2 py-1.5 outline-none text-sm"
            style={{ color: "var(--text)" }}
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          >
            <option value="">Status: todos</option>
            <option value="NEW">Nova</option>
            <option value="INCREASED">Aumentou</option>
            <option value="DECREASED">Reduziu</option>
            <option value="UNCHANGED">Manteve</option>
          </select>
          <button
            onClick={() => setShowZeroed((v) => !v)}
            className="smb-card px-3 py-1.5 text-sm"
            style={{ color: showZeroed ? "var(--amber)" : "var(--text2)", borderColor: showZeroed ? "var(--amber)" : undefined }}
          >
            {showZeroed ? "✓ " : ""}Exibir Zeradas
          </button>
        </div>

        <div className="smb-card smb-table-wrap">
          <table className="smb-table w-full">
            <thead>
              <tr>
                <SortableTh label="Fundo" active={holdersSort.sortKey === "fund_name"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("fund_name")} />
                <SortableTh label="Status" active={holdersSort.sortKey === "classification"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("classification")} />
                <SortableTh label="Qtd" align="right" active={holdersSort.sortKey === "quantity"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("quantity")} />
                <SortableTh label="Valor" align="right" active={holdersSort.sortKey === "market_value"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("market_value")} />
                <SortableTh label="Preço" align="right" active={holdersSort.sortKey === "price_at_ref_date"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("price_at_ref_date")} />
                <SortableTh label="% do PL do fundo" align="right" active={holdersSort.sortKey === "pct_of_fund"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("pct_of_fund")} />
                <SortableTh label="Patrimônio do fundo" align="right" active={holdersSort.sortKey === "fund_net_asset_value"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("fund_net_asset_value")} />
                <SortableTh label="Cotistas" align="right" active={holdersSort.sortKey === "fund_n_shareholders"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("fund_n_shareholders")} />
                <SortableTh label="Mês" align="right" active={holdersSort.sortKey === "ref_date"} dir={holdersSort.sortDir} onClick={() => holdersSort.toggle("ref_date")} />
              </tr>
            </thead>
            <tbody>
              {sortedHolders.map((h) => (
                <tr key={h.fund_id}>
                  <td>
                    <Link href={`/fundos/${h.fund_id}`} style={{ color: "var(--gold)" }}>
                      {h.fund_name}
                    </Link>
                    <button
                      onClick={() => setSelectedFund({ id: h.fund_id, name: h.fund_name })}
                      title="Ver evolução da posição"
                      className="ml-2"
                      style={{ color: "var(--text3)" }}
                    >
                      📈
                    </button>
                  </td>
                  <td>{h.classification && <MovementBadge classification={h.classification} />}</td>
                  <td className="num">{h.quantity.toLocaleString("pt-BR")}</td>
                  <td className="num">{fmtBRL(h.market_value)}</td>
                  <td className="num" style={{ color: "var(--text2)" }} title="Fechamento da B3 no pregão mais próximo dessa declaração — não é o preço exato pago pelo fundo (a CVM não divulga isso)">
                    {fmtPrice(h.price_at_ref_date)}
                  </td>
                  <td
                    className="num"
                    style={{ fontWeight: 600, color: (h.pct_of_fund ?? 0) > 100 ? "var(--amber)" : undefined }}
                    title={
                      (h.pct_of_fund ?? 0) > 100
                        ? "Fundo com estrutura de dívida/alavancagem que usa o ativo como garantia — o patrimônio líquido divulgado já é líquido dessas obrigações."
                        : undefined
                    }
                  >
                    {fmtPct(h.pct_of_fund)}
                  </td>
                  <td className="num" style={{ color: "var(--text2)" }}>{h.fund_net_asset_value !== null ? fmtBRL(h.fund_net_asset_value) : "—"}</td>
                  <td className="num" style={{ color: "var(--text2)" }}>{h.fund_n_shareholders !== null ? h.fund_n_shareholders.toLocaleString("pt-BR") : "—"}</td>
                  <td className="num">
                    <span
                      className="smb-badge"
                      style={
                        h.ref_date.slice(0, 7) === mostRecentMonth
                          ? { color: "var(--text3)", border: "1px solid var(--border)" }
                          : { color: "var(--amber)", border: "1px solid var(--amber)" }
                      }
                      title={h.ref_date.slice(0, 7) === mostRecentMonth ? "Mês mais recente disponível" : "Fundo ainda não entregou meses mais recentes à CVM — posição pode estar desatualizada"}
                    >
                      {fmtMonth(h.ref_date)}
                    </span>
                  </td>
                </tr>
              ))}
              {sortedHolders.length === 0 && (
                <tr>
                  <td colSpan={9} style={{ color: "var(--text3)" }}>
                    Nenhum detentor encontrado com esses filtros.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
