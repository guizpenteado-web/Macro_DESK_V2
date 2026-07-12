"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api, Buyback, InsiderTrade, InsiderSortField, PricePoint } from "@/lib/api";
import SortableTh from "@/components/SortableTh";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const PRICE_YEARS = 10;

function fmtBRL(v: number | null) {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 });
}

function fmtNum(v: number | null) {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR");
}

function fmtPrice(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function DirectionBadge({ direction }: { direction: "COMPRA" | "VENDA" | null }) {
  if (!direction) return <span style={{ color: "var(--text3)" }}>—</span>;
  const isBuy = direction === "COMPRA";
  return (
    <span className="smb-badge" style={{ color: isBuy ? "var(--green)" : "var(--red)", border: `1px solid ${isBuy ? "var(--green)" : "var(--red)"}` }}>
      {isBuy ? "COMPRA" : "VENDA"}
    </span>
  );
}

const DIRECTION_OPTIONS: { value: "COMPRA" | "VENDA" | ""; label: string }[] = [
  { value: "COMPRA", label: "Compras" },
  { value: "VENDA", label: "Vendas" },
  { value: "", label: "Todos" },
];

// Candlestick (grid 0) + histograma de recompras declaradas (grid 1), eixo X
// compartilhado por categoria (mesmo array de datas da cotacao — recompras
// sao poucos eventos esparsos, entao cada uma e' encaixada na data de pregao
// mais proxima <= data de declaracao).
function buildChartOption(priceHistory: PricePoint[], buybacks: Buyback[]) {
  const dates = priceHistory.map((p) => p.date);
  const dateIndex = new Map(dates.map((d, i) => [d, i]));

  function nearestIndex(target: string): number {
    if (dateIndex.has(target)) return dateIndex.get(target)!;
    let best = 0;
    for (let i = 0; i < dates.length; i++) {
      if (dates[i] <= target) best = i;
      else break;
    }
    return best;
  }

  const buybackData: (number | null)[] = new Array(dates.length).fill(null);
  for (const b of buybacks) {
    if (dates.length === 0) break;
    const idx = nearestIndex(b.declared_at);
    const qty = (b.qty_common_shares ?? 0) + (b.qty_preferred_shares ?? 0);
    buybackData[idx] = (buybackData[idx] ?? 0) + qty;
  }

  return {
    backgroundColor: "transparent",
    animation: false,
    grid: [
      { left: 64, right: 30, top: 10, height: "56%" },
      { left: 64, right: 30, top: "72%", height: "18%" },
    ],
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    xAxis: [
      {
        type: "category",
        gridIndex: 0,
        data: dates,
        axisLine: { lineStyle: { color: "#565f75" } },
        axisLabel: { show: false },
        axisTick: { show: false },
      },
      {
        type: "category",
        gridIndex: 1,
        data: dates,
        axisLine: { lineStyle: { color: "#565f75" } },
        axisLabel: { color: "var(--text3)" },
      },
    ],
    yAxis: [
      {
        type: "value",
        gridIndex: 0,
        scale: true,
        name: "R$",
        axisLine: { lineStyle: { color: "#565f75" } },
        splitLine: { lineStyle: { color: "#232838" } },
        axisLabel: { color: "var(--text3)" },
      },
      {
        type: "value",
        gridIndex: 1,
        name: "Ações autorizadas",
        nameTextStyle: { color: "var(--text3)" },
        axisLine: { lineStyle: { color: "#565f75" } },
        splitLine: { show: false },
        axisLabel: { color: "var(--text3)" },
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 70, end: 100 },
      { type: "slider", xAxisIndex: [0, 1], bottom: 0, height: 16, textStyle: { color: "var(--text3)" } },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: (params: unknown) => {
        const arr = params as { dataIndex: number }[];
        const idx = arr[0]?.dataIndex;
        const p = idx !== undefined ? priceHistory[idx] : undefined;
        if (!p) return "";
        let html = `${p.date}<br/>Abertura: ${fmtPrice(p.open)}<br/>Máxima: ${fmtPrice(p.high)}<br/>Mínima: ${fmtPrice(p.low)}<br/>Fechamento: ${fmtPrice(p.close)}`;
        const qty = buybackData[idx];
        if (qty) html += `<br/><b>Recompra declarada: ${qty.toLocaleString("pt-BR")} ações</b>`;
        return html;
      },
    },
    series: [
      {
        name: "Cotação",
        type: "candlestick",
        xAxisIndex: 0,
        yAxisIndex: 0,
        data: priceHistory.map((p) => [p.open, p.close, p.low, p.high]),
        itemStyle: { color: "#22c55e", color0: "#ef4444", borderColor: "#22c55e", borderColor0: "#ef4444" },
      },
      {
        name: "Recompras (ações autorizadas)",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: buybackData,
        barWidth: 6,
        itemStyle: { color: "#f5a623" },
      },
    ],
  };
}

export default function InsidersPage() {
  const [q, setQ] = useState("");
  const [direction, setDirection] = useState<"COMPRA" | "VENDA" | "">("COMPRA");
  const [cargo, setCargo] = useState("");
  const [cargos, setCargos] = useState<string[]>([]);
  const [sortBy, setSortBy] = useState<InsiderSortField>("data_movimentacao");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [rows, setRows] = useState<InsiderTrade[]>([]);
  const [loading, setLoading] = useState(false);

  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [priceHistory, setPriceHistory] = useState<PricePoint[]>([]);
  const [tickerBuybacks, setTickerBuybacks] = useState<Buyback[]>([]);
  const [chartLoading, setChartLoading] = useState(false);

  useEffect(() => {
    api.getInsiderCargos().then(setCargos).catch(() => setCargos([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      api
        .getInsiderTrades({ search: q, direction, cargo, sortBy, sortDir, limit: 150 })
        .then(setRows)
        .catch(() => setRows([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [q, direction, cargo, sortBy, sortDir]);

  useEffect(() => {
    if (!selectedTicker) return;
    setChartLoading(true);
    Promise.all([api.getPriceHistory(selectedTicker, PRICE_YEARS), api.getBuybacks({ search: selectedTicker, limit: 50 })])
      .then(([price, buybacks]) => {
        setPriceHistory(price);
        setTickerBuybacks(buybacks.filter((b) => b.ticker === selectedTicker));
      })
      .catch(() => {
        setPriceHistory([]);
        setTickerBuybacks([]);
      })
      .finally(() => setChartLoading(false));
  }, [selectedTicker]);

  function toggleSort(field: InsiderSortField) {
    if (field === sortBy) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("desc");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Insiders</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
          Negociação de administradores, conselheiros e controladores com ações da própria companhia (CVM VLMO). Não
          há nome do indivíduo nos dados abertos da CVM — só o cargo agregado. Clique num ativo da lista pra ver a
          cotação.
        </p>
      </div>

      {selectedTicker && (
        <div className="smb-card p-4">
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold">
              Cotação ({PRICE_YEARS} anos) — <span style={{ color: "var(--cyan)" }}>{selectedTicker}</span>
            </div>
            <button onClick={() => setSelectedTicker(null)} style={{ color: "var(--text3)" }}>
              fechar ✕
            </button>
          </div>
          {chartLoading && <div className="text-sm" style={{ color: "var(--text3)" }}>Carregando cotação (primeira consulta de um ano novo pode levar alguns segundos)...</div>}
          {!chartLoading && priceHistory.length === 0 && (
            <div className="text-sm" style={{ color: "var(--text3)" }}>
              Sem cotação na B3 pra {selectedTicker} (pode ser ticker sem negociação em bolsa, FII, ou código incorreto).
            </div>
          )}
          {!chartLoading && priceHistory.length > 0 && (
            <>
              <ReactECharts option={buildChartOption(priceHistory, tickerBuybacks)} style={{ height: 440 }} notMerge />
              <div className="text-xs mt-1" style={{ color: "var(--text3)" }}>
                Candlestick = cotação diária real via B3 (COTAHIST), não vem da CVM. Barras embaixo = total de ações
                autorizadas em programas de recompra declarados nesse período — a CVM não publica execução mês a mês,
                só o total autorizado por programa na data de declaração.
              </div>
            </>
          )}
        </div>
      )}

      <input
        className="smb-card w-full px-4 py-2 outline-none"
        placeholder="Buscar por ticker, empresa ou CNPJ..."
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />

      <div className="smb-card p-3 flex flex-wrap gap-3 items-end">
        <div className="flex gap-2">
          {DIRECTION_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setDirection(o.value)}
              className="smb-card px-3 py-1.5 text-sm"
              style={{ color: direction === o.value ? "var(--cyan)" : "var(--text2)" }}
            >
              {o.label}
            </button>
          ))}
        </div>

        <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text3)" }}>
          Cargo
          <select
            className="smb-card px-2 py-1 outline-none text-sm"
            style={{ color: "var(--text)" }}
            value={cargo}
            onChange={(e) => setCargo(e.target.value)}
          >
            <option value="">Todos</option>
            {cargos.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="smb-card smb-table-wrap">
        <table className="smb-table w-full">
          <thead>
            <tr>
              <SortableTh label="Empresa" active={sortBy === "ticker"} dir={sortDir} onClick={() => toggleSort("ticker")} />
              <th>Cargo</th>
              <th>Negociante</th>
              <th>Movimentação</th>
              <th>Ativo</th>
              <SortableTh label="Data" align="right" active={sortBy === "data_movimentacao"} dir={sortDir} onClick={() => toggleSort("data_movimentacao")} />
              <SortableTh label="Qtd" align="right" active={sortBy === "quantidade"} dir={sortDir} onClick={() => toggleSort("quantidade")} />
              <SortableTh label="Preço" align="right" active={sortBy === "preco_unitario"} dir={sortDir} onClick={() => toggleSort("preco_unitario")} />
              <SortableTh label="Volume" align="right" active={sortBy === "volume"} dir={sortDir} onClick={() => toggleSort("volume")} />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td
                  style={{ color: "var(--text)", cursor: r.ticker ? "pointer" : "default" }}
                  onClick={() => r.ticker && setSelectedTicker(r.ticker)}
                >
                  <div style={{ fontWeight: 600, color: r.ticker ? "var(--cyan)" : "var(--text)" }}>{r.ticker ?? "—"}</div>
                  <div className="text-xs" style={{ color: "var(--text3)" }}>{r.company_name}</div>
                </td>
                <td style={{ color: "var(--text3)" }}>{r.tipo_cargo ?? "—"}</td>
                <td style={{ color: "var(--text3)" }}>{r.empresa ?? "—"}</td>
                <td>
                  <DirectionBadge direction={r.direction} />
                  <span className="ml-2 text-xs" style={{ color: "var(--text3)" }}>
                    {r.tipo_movimentacao}
                  </span>
                </td>
                <td style={{ color: "var(--text3)" }}>{r.tipo_ativo ?? "—"}</td>
                <td className="num" style={{ color: "var(--text3)" }}>{r.data_movimentacao ?? "—"}</td>
                <td className="num">{fmtNum(r.quantidade)}</td>
                <td className="num">{fmtBRL(r.preco_unitario)}</td>
                <td className="num" style={{ fontWeight: 600 }}>{fmtBRL(r.volume)}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={9} style={{ color: "var(--text3)" }}>
                  Nenhuma negociação encontrada.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
