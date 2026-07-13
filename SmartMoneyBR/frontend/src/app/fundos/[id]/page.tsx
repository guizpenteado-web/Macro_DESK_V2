"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api, Fund, Holding, Movement, AssetHistoryPoint, FundPerformance, FundQuotaHistory, PerformanceMovement } from "@/lib/api";
import MovementBadge from "@/components/MovementBadge";
import SortableTh from "@/components/SortableTh";
import { sortRows, useSort } from "@/lib/sort";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

function fmtBRL(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

function fmtPct(v: number | null) {
  if (v === null || v === undefined) return "—";
  return `${v >= 0 ? "+" : ""}${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
}

function fmtBookPct(v: number | null) {
  if (v === null || v === undefined) return "—";
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 })}%`;
}

const MONTH_ABBR = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];
function fmtMonth(dateStr: string) {
  const [y, m] = dateStr.split("-");
  return `${MONTH_ABBR[Number(m) - 1]}/${y.slice(2)}`;
}

function MiniMovementRow({
  m,
  refDate,
  showQtyCurrent,
  showPctDelta,
  onClick,
}: {
  m: PerformanceMovement;
  refDate: string | null;
  showQtyCurrent: boolean;
  showPctDelta: boolean;
  onClick: () => void;
}) {
  return (
    <tr style={{ cursor: "pointer" }} onClick={onClick}>
      <td style={{ color: "var(--gold)" }}>{m.ticker}</td>
      <td>
        <MovementBadge classification={m.classification} />
      </td>
      <td className="num">
        {refDate ? (
          <span className="smb-badge" style={{ color: "var(--text3)", border: "1px solid var(--border)" }}>
            {fmtMonth(refDate)}
          </span>
        ) : (
          "—"
        )}
      </td>
      {showQtyCurrent && <td className="num">{m.qty_current.toLocaleString("pt-BR")}</td>}
      <td className="num" style={{ color: m.value_delta >= 0 ? "var(--green)" : "var(--red)" }}>{fmtBRL(m.value_delta)}</td>
      {showPctDelta && (
        <td className="num" style={{ color: m.value_delta >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>{fmtPct(m.pct_delta)}</td>
      )}
      <td className="num" style={{ fontWeight: 600 }}>{fmtBookPct(m.pct_of_equity_book)}</td>
    </tr>
  );
}

type MovementSortKey = "ticker" | "classification" | "qty_current" | "value_delta" | "pct_delta" | "pct_of_equity_book";

function MiniTable({
  title,
  rows,
  refDate,
  onSelect,
  showQtyCurrent = true,
  showPctDelta = true,
}: {
  title: string;
  rows: PerformanceMovement[];
  refDate: string | null;
  onSelect: (a: { id: number; ticker: string }) => void;
  showQtyCurrent?: boolean;
  showPctDelta?: boolean;
}) {
  const { sortKey, sortDir, toggle } = useSort<MovementSortKey>();
  const sorted = sortKey ? sortRows(rows, (r) => r[sortKey], sortDir) : rows;
  const colSpan = 4 + (showQtyCurrent ? 1 : 0) + (showPctDelta ? 1 : 0);

  return (
    <div className="smb-card smb-table-wrap">
      <div className="px-3 pt-3 pb-1 text-sm font-semibold" style={{ color: "var(--text)" }}>{title}</div>
      <table className="smb-table w-full">
        <thead>
          <tr>
            <SortableTh label="Ativo" active={sortKey === "ticker"} dir={sortDir} onClick={() => toggle("ticker")} />
            <SortableTh label="Status" active={sortKey === "classification"} dir={sortDir} onClick={() => toggle("classification")} />
            <SortableTh label="Mês" align="right" active={false} dir={sortDir} onClick={() => {}} />
            {showQtyCurrent && (
              <SortableTh label="Qtd atual" align="right" active={sortKey === "qty_current"} dir={sortDir} onClick={() => toggle("qty_current")} />
            )}
            <SortableTh label="Δ Valor" align="right" active={sortKey === "value_delta"} dir={sortDir} onClick={() => toggle("value_delta")} />
            {showPctDelta && (
              <SortableTh label="% relativo" align="right" active={sortKey === "pct_delta"} dir={sortDir} onClick={() => toggle("pct_delta")} />
            )}
            <SortableTh label="% da carteira" align="right" active={sortKey === "pct_of_equity_book"} dir={sortDir} onClick={() => toggle("pct_of_equity_book")} />
          </tr>
        </thead>
        <tbody>
          {sorted.map((m) => (
            <MiniMovementRow
              key={m.asset_id}
              m={m}
              refDate={refDate}
              showQtyCurrent={showQtyCurrent}
              showPctDelta={showPctDelta}
              onClick={() => onSelect({ id: m.asset_id, ticker: m.ticker })}
            />
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={colSpan} style={{ color: "var(--text3)" }}>Nenhum item.</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default function FundDetailPage() {
  const params = useParams();
  const fundId = Number(params.id);

  const [fund, setFund] = useState<Fund | null>(null);
  const [holdings, setHoldings] = useState<Holding[]>([]);
  const [movements, setMovements] = useState<Movement[]>([]);
  const [perf, setPerf] = useState<FundPerformance | null>(null);
  const [quotaHistory, setQuotaHistory] = useState<FundQuotaHistory | null>(null);
  const [selectedAsset, setSelectedAsset] = useState<{ id: number; ticker: string } | null>(null);
  const [history, setHistory] = useState<AssetHistoryPoint[]>([]);

  const movementsSort = useSort<"ticker" | "classification" | "ref_date" | "qty_current" | "qty_delta" | "value_delta" | "pct_delta">();
  const sortedMovements = movementsSort.sortKey ? sortRows(movements, (m) => m[movementsSort.sortKey!], movementsSort.sortDir) : movements;

  const holdingsSort = useSort<"ticker" | "quantity" | "market_value" | "pct_of_equity_book">();
  const sortedHoldings = holdingsSort.sortKey ? sortRows(holdings, (h) => h[holdingsSort.sortKey!], holdingsSort.sortDir) : holdings;

  useEffect(() => {
    if (!fundId) return;
    api.getFund(fundId).then(setFund);
    api.getFundHoldings(fundId).then(setHoldings);
    api.getFundMovements(fundId).then(setMovements);
    api.getFundPerformance(fundId).then(setPerf);
    api.getFundQuotaHistory(fundId, 20).then(setQuotaHistory);
  }, [fundId]);

  useEffect(() => {
    if (!selectedAsset) return;
    api.getFundAssetHistory(fundId, selectedAsset.id).then(setHistory);
  }, [fundId, selectedAsset]);

  const assetChartOption = {
    backgroundColor: "transparent",
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: { type: "category", data: history.map((h) => h.ref_date), axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } } },
    yAxis: { type: "value", axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } }, splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } } },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const p = (params as { dataIndex: number }[])[0];
        const h = history[p.dataIndex];
        return `${h.ref_date}<br/>Qtd: ${h.quantity.toLocaleString("pt-BR")}<br/>${h.classification ?? ""}`;
      },
    },
    series: [
      {
        type: "bar",
        data: history.map((h) => h.quantity),
        itemStyle: { color: "#c9a227" },
      },
    ],
  };

  const evoOption = perf && {
    backgroundColor: "transparent",
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: "category",
      data: perf.evolucao_posicoes_compradas.map((e) => e.ref_date),
      axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
    },
    yAxis: { type: "value", axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } }, splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } } },
    tooltip: { trigger: "axis" },
    series: [
      {
        name: "Valor comprado no mês",
        type: "bar",
        data: perf.evolucao_posicoes_compradas.map((e) => e.total_bought),
        itemStyle: { color: "#22c55e" },
      },
    ],
  };

  const quotaPoints = quotaHistory?.points ?? [];
  const quotaTotalReturn = quotaPoints.length > 0 ? quotaPoints[quotaPoints.length - 1].indexed! - 100 : null;

  const quotaChartOption = {
    backgroundColor: "transparent",
    grid: { left: 55, right: 20, top: 20, bottom: 40 },
    xAxis: {
      type: "category",
      data: quotaPoints.map((p) => p.ref_date),
      axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
      axisLabel: { color: "#8a94ab" },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
      splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } },
      axisLabel: { color: "#8a94ab", formatter: "{value}" },
    },
    dataZoom: [{ type: "inside", xAxisIndex: [0], yAxisIndex: [0], zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false }],
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const p = (params as { dataIndex: number }[])[0];
        const point = quotaPoints[p.dataIndex];
        if (!point) return "";
        const pct = point.indexed !== null ? point.indexed - 100 : null;
        return `${point.ref_date}<br/>Cota: ${point.quota_value.toLocaleString("pt-BR", { maximumFractionDigits: 6 })}<br/>Desde início: ${pct !== null ? fmtPct(pct) : "—"}`;
      },
    },
    series: [
      {
        type: "line",
        data: quotaPoints.map((p) => p.indexed),
        showSymbol: false,
        smooth: false,
        lineStyle: { color: "#c9a227", width: 1.5 },
        areaStyle: { color: "rgba(0, 229, 255, 0.08)" },
      },
    ],
  };

  if (!fund) return <div style={{ color: "var(--text2)" }}>Carregando...</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">{fund.name}</h1>
        <div className="text-sm" style={{ color: "var(--text2)" }}>
          {fund.cnpj} · {fund.fund_class_type}
        </div>
        <div className="flex flex-wrap gap-4 mt-2 text-sm">
          <div>
            <span style={{ color: "var(--text3)" }}>Patrimônio líquido: </span>
            <span style={{ color: "var(--text)", fontWeight: 600 }}>
              {fund.net_asset_value !== null ? fmtBRL(fund.net_asset_value) : "—"}
            </span>
          </div>
          <div>
            <span style={{ color: "var(--text3)" }}>Cotistas: </span>
            <span style={{ color: "var(--text)", fontWeight: 600 }}>
              {fund.n_shareholders !== null ? fund.n_shareholders.toLocaleString("pt-BR") : "—"}
            </span>
          </div>
          {fund.financials_ref_date && (
            <div>
              <span style={{ color: "var(--text3)" }}>Divulgação: </span>
              <span style={{ color: "var(--text)", fontWeight: 600 }}>{fund.financials_ref_date}</span>
            </div>
          )}
        </div>
      </div>

      {quotaPoints.length > 1 && (
        <div className="smb-card p-4">
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold">
              Cotação — performance{" "}
              <span style={{ color: "var(--text3)", fontWeight: 400 }}>
                ({quotaHistory?.window_start} — {quotaPoints[quotaPoints.length - 1].ref_date})
              </span>
            </div>
            {quotaTotalReturn !== null && (
              <div style={{ color: quotaTotalReturn >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>
                {fmtPct(quotaTotalReturn)}
              </div>
            )}
          </div>
          <ReactECharts option={quotaChartOption} style={{ height: 300 }} />
        </div>
      )}

      {selectedAsset && (
        <div className="smb-card p-4">
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold">
              Evolução da posição em <span style={{ color: "var(--gold)" }}>{selectedAsset.ticker}</span>
            </div>
            <button onClick={() => setSelectedAsset(null)} style={{ color: "var(--text3)" }}>
              fechar ✕
            </button>
          </div>
          <ReactECharts option={assetChartOption} style={{ height: 260 }} />
        </div>
      )}

      {perf && perf.evolucao_posicoes_compradas.length > 0 && (
        <div className="smb-card p-4">
          <div className="font-semibold mb-2">Evolução de posições compradas (valor investido em novas/aumentadas por mês)</div>
          <ReactECharts option={evoOption} style={{ height: 220 }} />
        </div>
      )}

      {perf && (
        <div>
          <h2 className="font-semibold mb-2">Principais alterações em carteira ({perf.ref_date})</h2>
          <MiniTable title="Maiores movimentos (por valor absoluto)" rows={perf.principais_alteracoes} refDate={perf.ref_date} onSelect={setSelectedAsset} />
        </div>
      )}

      {perf && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MiniTable title="🟢 O que aumentou" rows={perf.o_que_aumentou} refDate={perf.ref_date} onSelect={setSelectedAsset} />
          <MiniTable title="🔴 O que diminuiu" rows={perf.o_que_diminuiu} refDate={perf.ref_date} onSelect={setSelectedAsset} />
        </div>
      )}

      {perf && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MiniTable title="🆕 Novas posições" rows={perf.novas_posicoes} refDate={perf.ref_date} onSelect={setSelectedAsset} showPctDelta={false} />
          <MiniTable title="⚫ Zeragens" rows={perf.zeragens} refDate={perf.ref_date} onSelect={setSelectedAsset} showQtyCurrent={false} showPctDelta={false} />
        </div>
      )}

      {perf && (
        <div>
          <h2 className="font-semibold mb-2">Top posições compradas</h2>
          <MiniTable title="Maiores compras/aumentos por valor" rows={perf.top_posicoes_compradas} refDate={perf.ref_date} onSelect={setSelectedAsset} />
        </div>
      )}

      <div>
        <div className="flex items-center gap-2 mb-2">
          <h2 className="font-semibold">Todos os últimos movimentos</h2>
          {movements[0] && (
            <span className="text-xs" style={{ color: "var(--text3)" }}>
              (referência: {movements[0].ref_date} — último mês com dado disponível para este fundo)
            </span>
          )}
        </div>
        <div className="smb-card smb-table-wrap">
          <table className="smb-table w-full">
            <thead>
              <tr>
                <SortableTh label="Ativo" active={movementsSort.sortKey === "ticker"} dir={movementsSort.sortDir} onClick={() => movementsSort.toggle("ticker")} />
                <SortableTh label="Status" active={movementsSort.sortKey === "classification"} dir={movementsSort.sortDir} onClick={() => movementsSort.toggle("classification")} />
                <SortableTh label="Data" align="right" active={movementsSort.sortKey === "ref_date"} dir={movementsSort.sortDir} onClick={() => movementsSort.toggle("ref_date")} />
                <SortableTh label="Qtd atual" align="right" active={movementsSort.sortKey === "qty_current"} dir={movementsSort.sortDir} onClick={() => movementsSort.toggle("qty_current")} />
                <SortableTh label="Δ Qtd" align="right" active={movementsSort.sortKey === "qty_delta"} dir={movementsSort.sortDir} onClick={() => movementsSort.toggle("qty_delta")} />
                <SortableTh label="Δ Valor" align="right" active={movementsSort.sortKey === "value_delta"} dir={movementsSort.sortDir} onClick={() => movementsSort.toggle("value_delta")} />
                <SortableTh label="% relativo" align="right" active={movementsSort.sortKey === "pct_delta"} dir={movementsSort.sortDir} onClick={() => movementsSort.toggle("pct_delta")} />
              </tr>
            </thead>
            <tbody>
              {sortedMovements.map((m) => (
                <tr key={m.asset_id} style={{ cursor: "pointer" }} onClick={() => setSelectedAsset({ id: m.asset_id, ticker: m.ticker })}>
                  <td style={{ color: "var(--gold)" }}>{m.ticker}</td>
                  <td>
                    <MovementBadge classification={m.classification} />
                  </td>
                  <td className="num" style={{ color: "var(--text3)" }}>{m.ref_date}</td>
                  <td className="num">{m.qty_current.toLocaleString("pt-BR")}</td>
                  <td className="num" style={{ color: m.qty_delta >= 0 ? "var(--green)" : "var(--red)" }}>
                    {m.qty_delta >= 0 ? "+" : ""}
                    {m.qty_delta.toLocaleString("pt-BR")}
                  </td>
                  <td className="num" style={{ color: m.value_delta >= 0 ? "var(--green)" : "var(--red)" }}>{fmtBRL(m.value_delta)}</td>
                  <td className="num" style={{ color: m.value_delta >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>{fmtPct(m.pct_delta)}</td>
                </tr>
              ))}
              {movements.length === 0 && (
                <tr>
                  <td colSpan={7} style={{ color: "var(--text3)" }}>Este fundo ainda não tem movimentos registrados.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <div className="flex items-center gap-2 mb-2">
          <h2 className="font-semibold">Carteira atual (top posições)</h2>
          {holdings[0] && (
            <span className="text-xs" style={{ color: "var(--text3)" }}>
              (referência: {holdings[0].ref_date})
            </span>
          )}
        </div>
        <div className="smb-card smb-table-wrap">
          <table className="smb-table w-full">
            <thead>
              <tr>
                <SortableTh label="Ativo" active={holdingsSort.sortKey === "ticker"} dir={holdingsSort.sortDir} onClick={() => holdingsSort.toggle("ticker")} />
                <SortableTh label="Qtd" align="right" active={holdingsSort.sortKey === "quantity"} dir={holdingsSort.sortDir} onClick={() => holdingsSort.toggle("quantity")} />
                <SortableTh label="Valor" align="right" active={holdingsSort.sortKey === "market_value"} dir={holdingsSort.sortDir} onClick={() => holdingsSort.toggle("market_value")} />
                <SortableTh label="% da carteira (ações)" align="right" active={holdingsSort.sortKey === "pct_of_equity_book"} dir={holdingsSort.sortDir} onClick={() => holdingsSort.toggle("pct_of_equity_book")} />
              </tr>
            </thead>
            <tbody>
              {sortedHoldings.map((h) => (
                <tr key={h.asset_id} style={{ cursor: "pointer" }} onClick={() => setSelectedAsset({ id: h.asset_id, ticker: h.ticker })}>
                  <td style={{ color: "var(--gold)" }}>{h.ticker}</td>
                  <td className="num">{h.quantity.toLocaleString("pt-BR")}</td>
                  <td className="num">{fmtBRL(h.market_value)}</td>
                  <td className="num">{h.pct_of_equity_book?.toFixed(2)}%</td>
                </tr>
              ))}
              {holdings.length === 0 && (
                <tr>
                  <td colSpan={4} style={{ color: "var(--text3)" }}>Este fundo ainda não tem posições em ações registradas.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
