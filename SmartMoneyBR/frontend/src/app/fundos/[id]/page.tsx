"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api, Fund, Holding, Movement, AssetHistoryPoint, FundPerformance, PerformanceMovement } from "@/lib/api";
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

function MiniMovementRow({ m, onClick }: { m: PerformanceMovement; onClick: () => void }) {
  return (
    <tr style={{ cursor: "pointer" }} onClick={onClick}>
      <td style={{ color: "var(--cyan)" }}>{m.ticker}</td>
      <td>
        <MovementBadge classification={m.classification} />
      </td>
      <td className="num">{m.qty_current.toLocaleString("pt-BR")}</td>
      <td className="num" style={{ color: m.value_delta >= 0 ? "var(--green)" : "var(--red)" }}>{fmtBRL(m.value_delta)}</td>
      <td className="num" style={{ color: m.value_delta >= 0 ? "var(--green)" : "var(--red)", fontWeight: 600 }}>{fmtPct(m.pct_delta)}</td>
      <td className="num" style={{ fontWeight: 600 }}>{fmtBookPct(m.pct_of_equity_book)}</td>
    </tr>
  );
}

type MovementSortKey = "ticker" | "classification" | "qty_current" | "value_delta" | "pct_delta" | "pct_of_equity_book";

function MiniTable({ title, rows, onSelect }: { title: string; rows: PerformanceMovement[]; onSelect: (a: { id: number; ticker: string }) => void }) {
  const { sortKey, sortDir, toggle } = useSort<MovementSortKey>();
  const sorted = sortKey ? sortRows(rows, (r) => r[sortKey], sortDir) : rows;

  return (
    <div className="smb-card smb-table-wrap">
      <div className="px-3 pt-3 pb-1 text-sm font-semibold" style={{ color: "var(--text)" }}>{title}</div>
      <table className="smb-table w-full">
        <thead>
          <tr>
            <SortableTh label="Ativo" active={sortKey === "ticker"} dir={sortDir} onClick={() => toggle("ticker")} />
            <SortableTh label="Status" active={sortKey === "classification"} dir={sortDir} onClick={() => toggle("classification")} />
            <SortableTh label="Qtd atual" align="right" active={sortKey === "qty_current"} dir={sortDir} onClick={() => toggle("qty_current")} />
            <SortableTh label="Δ Valor" align="right" active={sortKey === "value_delta"} dir={sortDir} onClick={() => toggle("value_delta")} />
            <SortableTh label="% relativo" align="right" active={sortKey === "pct_delta"} dir={sortDir} onClick={() => toggle("pct_delta")} />
            <SortableTh label="% da carteira" align="right" active={sortKey === "pct_of_equity_book"} dir={sortDir} onClick={() => toggle("pct_of_equity_book")} />
          </tr>
        </thead>
        <tbody>
          {sorted.map((m) => (
            <MiniMovementRow key={m.asset_id} m={m} onClick={() => onSelect({ id: m.asset_id, ticker: m.ticker })} />
          ))}
          {rows.length === 0 && (
            <tr>
              <td colSpan={6} style={{ color: "var(--text3)" }}>Nenhum item.</td>
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
  }, [fundId]);

  useEffect(() => {
    if (!selectedAsset) return;
    api.getFundAssetHistory(fundId, selectedAsset.id).then(setHistory);
  }, [fundId, selectedAsset]);

  const assetChartOption = {
    backgroundColor: "transparent",
    grid: { left: 50, right: 20, top: 20, bottom: 30 },
    xAxis: { type: "category", data: history.map((h) => h.ref_date), axisLine: { lineStyle: { color: "#565f75" } } },
    yAxis: { type: "value", axisLine: { lineStyle: { color: "#565f75" } }, splitLine: { lineStyle: { color: "#232838" } } },
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
        itemStyle: { color: "#00e5ff" },
      },
    ],
  };

  const evoOption = perf && {
    backgroundColor: "transparent",
    grid: { left: 60, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: "category",
      data: perf.evolucao_posicoes_compradas.map((e) => e.ref_date),
      axisLine: { lineStyle: { color: "#565f75" } },
    },
    yAxis: { type: "value", axisLine: { lineStyle: { color: "#565f75" } }, splitLine: { lineStyle: { color: "#232838" } } },
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

      {selectedAsset && (
        <div className="smb-card p-4">
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold">
              Evolução da posição em <span style={{ color: "var(--cyan)" }}>{selectedAsset.ticker}</span>
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
          <MiniTable title="Maiores movimentos (por valor absoluto)" rows={perf.principais_alteracoes} onSelect={setSelectedAsset} />
        </div>
      )}

      {perf && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MiniTable title="🟢 O que aumentou" rows={perf.o_que_aumentou} onSelect={setSelectedAsset} />
          <MiniTable title="🔴 O que diminuiu" rows={perf.o_que_diminuiu} onSelect={setSelectedAsset} />
        </div>
      )}

      {perf && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <MiniTable title="🆕 Novas posições" rows={perf.novas_posicoes} onSelect={setSelectedAsset} />
          <MiniTable title="⚫ Zeragens" rows={perf.zeragens} onSelect={setSelectedAsset} />
        </div>
      )}

      {perf && (
        <div>
          <h2 className="font-semibold mb-2">Top posições compradas</h2>
          <MiniTable title="Maiores compras/aumentos por valor" rows={perf.top_posicoes_compradas} onSelect={setSelectedAsset} />
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
                  <td style={{ color: "var(--cyan)" }}>{m.ticker}</td>
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
                  <td style={{ color: "var(--cyan)" }}>{h.ticker}</td>
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
