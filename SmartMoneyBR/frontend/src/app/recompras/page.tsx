"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { api, Buyback, BuybackSortField, PricePoint } from "@/lib/api";
import SortableTh from "@/components/SortableTh";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const PRICE_YEARS = 10;

// Mesmo motivo/implementacao do insiders/page.tsx: dataZoom "inside" do
// ECharts nao respondia ao arrasto vertical mesmo com xAxisIndex+yAxisIndex
// juntos — pan vertical feito manualmente via zrender + dispatchAction.
function attachVerticalPan(chart: any, yAxisIndex: number) {
  const zr = chart.getZr();
  let dragging = false;
  let lastY = 0;

  function onDown(params: any) {
    dragging = true;
    lastY = params.offsetY;
  }
  function onMove(params: any) {
    if (!dragging) return;
    const dy = params.offsetY - lastY;
    lastY = params.offsetY;
    if (!dy) return;

    const opt = chart.getOption();
    const dzList: any[] = opt.dataZoom || [];
    const dz = dzList.find((d) => Array.isArray(d.yAxisIndex) && d.yAxisIndex.includes(yAxisIndex));
    if (!dz) return;
    const start = dz.start ?? 0;
    const end = dz.end ?? 100;
    const span = end - start;
    const height = chart.getHeight();
    const deltaPct = (dy / height) * span;
    let newStart = start - deltaPct;
    let newEnd = end - deltaPct;
    if (newStart < 0) {
      newEnd += -newStart;
      newStart = 0;
    }
    if (newEnd > 100) {
      newStart -= newEnd - 100;
      newEnd = 100;
    }
    chart.dispatchAction({ type: "dataZoom", yAxisIndex, start: newStart, end: newEnd });
  }
  function onUp() {
    dragging = false;
  }

  zr.on("mousedown", onDown);
  zr.on("mousemove", onMove);
  zr.on("mouseup", onUp);
  zr.on("globalout", onUp);

  return () => {
    zr.off("mousedown", onDown);
    zr.off("mousemove", onMove);
    zr.off("mouseup", onUp);
    zr.off("globalout", onUp);
  };
}

function fmtNum(v: number | null) {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR");
}

function fmtPrice(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function StatusBadge({ status }: { status: string }) {
  const isActive = status === "Em Andamento";
  return (
    <span
      className="smb-badge"
      style={{
        color: isActive ? "var(--green)" : "var(--text3)",
        border: `1px solid ${isActive ? "var(--green)" : "var(--border)"}`,
      }}
    >
      {status}
    </span>
  );
}

const STATUS_OPTIONS: { value: "" | "Em Andamento" | "Encerrado"; label: string }[] = [
  { value: "Em Andamento", label: "Em andamento" },
  { value: "Encerrado", label: "Encerrados" },
  { value: "", label: "Todos" },
];

// Mesmo padrao visual/interacao do grafico de cotacao da aba Insiders
// (candlestick + histograma embaixo, dataZoom combinado X+Y, min/max fixo
// em vez de scale:true pra nao brigar com pan manual). Diferenca: CVM so
// entrega o PROGRAMA de recompra declarado (data + quantidade autorizada),
// nao a execucao diaria — entao o histograma agrega por mes a quantidade
// TOTAL autorizada (ON+PN) nos programas declarados naquele mes, nao
// "acoes efetivamente recompradas no dia" (esse dado nao existe na fonte).
function buildChartOption(priceHistory: PricePoint[], buybacks: Buyback[]) {
  const dates = priceHistory.map((p) => p.date);

  let priceMin = Infinity;
  let priceMax = -Infinity;
  for (const p of priceHistory) {
    priceMin = Math.min(priceMin, p.low);
    priceMax = Math.max(priceMax, p.high);
  }
  const pricePad = (priceMax - priceMin) * 0.08 || 1;
  const yPriceMin = priceHistory.length ? priceMin - pricePad : undefined;
  const yPriceMax = priceHistory.length ? priceMax + pricePad : undefined;

  const buybacksByDate = new Map<string, Buyback[]>();
  for (const b of buybacks) {
    buybacksByDate.set(b.declared_at, [...(buybacksByDate.get(b.declared_at) ?? []), b]);
  }

  const months: string[] = [];
  if (dates.length > 0) {
    let y = Number(dates[0].slice(0, 4));
    let m = Number(dates[0].slice(5, 7));
    const endY = Number(dates[dates.length - 1].slice(0, 4));
    const endM = Number(dates[dates.length - 1].slice(5, 7));
    while (y < endY || (y === endY && m <= endM)) {
      months.push(`${y}-${String(m).padStart(2, "0")}`);
      m++;
      if (m > 12) {
        m = 1;
        y++;
      }
    }
  }
  const monthIndex = new Map(months.map((mo, i) => [mo, i]));
  const buybackMonthlyData: (number | null)[] = new Array(months.length).fill(null);
  for (const b of buybacks) {
    const idx = monthIndex.get(b.declared_at.slice(0, 7));
    if (idx === undefined) continue;
    const qty = (b.qty_common_shares ?? 0) + (b.qty_preferred_shares ?? 0);
    buybackMonthlyData[idx] = (buybackMonthlyData[idx] ?? 0) + qty;
  }

  return {
    backgroundColor: "transparent",
    animation: false,
    grid: [
      { left: 64, right: 24, top: 30, height: "62%" },
      { left: 64, right: 24, top: "80%", height: "14%" },
    ],
    legend: {
      data: ["Cotação", "Recompra (qtd autorizada)"],
      textStyle: { color: "#7d90a8" },
      top: 0,
    },
    xAxis: [
      {
        type: "category",
        gridIndex: 0,
        data: dates,
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
        axisLabel: { show: false },
        axisTick: { show: false },
      },
      {
        type: "category",
        gridIndex: 1,
        data: months,
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
        axisLabel: { color: "#4a5b73", interval: Math.ceil(months.length / 12) },
      },
    ],
    yAxis: [
      {
        id: "yPrice",
        type: "value",
        gridIndex: 0,
        min: yPriceMin,
        max: yPriceMax,
        name: "R$",
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } },
        axisLabel: { color: "#4a5b73" },
      },
      {
        id: "yBuyback",
        type: "value",
        gridIndex: 1,
        name: "Qtd autorizada",
        nameTextStyle: { color: "#4a5b73" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
        splitLine: { show: false },
        axisLabel: { color: "#4a5b73" },
      },
    ],
    dataZoom: [
      { type: "inside", xAxisIndex: [0], zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
      { type: "inside", yAxisIndex: [0], zoomOnMouseWheel: true, moveOnMouseMove: false, moveOnMouseWheel: false },
      { type: "inside", xAxisIndex: [1], zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
      { type: "inside", yAxisIndex: [1], zoomOnMouseWheel: true, moveOnMouseMove: false, moveOnMouseWheel: false },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: (params: unknown) => {
        const arr = params as { seriesType: string; dataIndex: number }[];
        const priceParam = arr.find((p) => p.seriesType === "candlestick");
        if (priceParam) {
          const p = priceHistory[priceParam.dataIndex];
          if (!p) return "";
          let html = `${p.date}<br/>Abertura: ${fmtPrice(p.open)}<br/>Máxima: ${fmtPrice(p.high)}<br/>Mínima: ${fmtPrice(p.low)}<br/>Fechamento: ${fmtPrice(p.close)}`;
          const progs = buybacksByDate.get(p.date);
          if (progs?.length) {
            for (const b of progs) {
              const qty = (b.qty_common_shares ?? 0) + (b.qty_preferred_shares ?? 0);
              html += `<br/><b style="color:#22c55e">Recompra declarada: ${qty.toLocaleString("pt-BR")} ações (${b.status})</b>`;
            }
          }
          return html;
        }
        const barParam = arr.find((p) => p.seriesType === "bar");
        if (barParam) {
          const val = buybackMonthlyData[barParam.dataIndex];
          return `${months[barParam.dataIndex]}<br/>Qtd autorizada: ${val !== null ? val.toLocaleString("pt-BR") : 0}`;
        }
        return "";
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
        name: "Recompra (qtd autorizada)",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: buybackMonthlyData,
        barMaxWidth: 14,
        itemStyle: { color: "#22c55e" },
      },
    ],
  };
}

export default function RecomprasPage() {
  const [q, setQ] = useState("");
  const [status, setStatus] = useState<"" | "Em Andamento" | "Encerrado">("Em Andamento");
  const [sortBy, setSortBy] = useState<BuybackSortField>("declared_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [rows, setRows] = useState<Buyback[]>([]);
  const [loading, setLoading] = useState(false);
  const panCleanupRef = useRef<(() => void)[]>([]);

  function onChartReady(chart: any) {
    panCleanupRef.current.forEach((fn) => fn());
    panCleanupRef.current = [attachVerticalPan(chart, 0), attachVerticalPan(chart, 1)];
  }

  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [priceHistory, setPriceHistory] = useState<PricePoint[]>([]);
  const [tickerBuybacks, setTickerBuybacks] = useState<Buyback[]>([]);
  const [chartLoading, setChartLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      api
        .getBuybacks({ search: q, status, sortBy, sortDir, limit: 150 })
        .then(setRows)
        .catch(() => setRows([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [q, status, sortBy, sortDir]);

  useEffect(() => {
    if (!selectedTicker) return;
    setChartLoading(true);
    Promise.all([
      api.getPriceHistory(selectedTicker, PRICE_YEARS),
      // todos os programas do ticker, sem depender do filtro de status da
      // tabela — o grafico mostra tudo, sempre.
      api.getBuybacks({ search: selectedTicker, status: "", limit: 500 }),
    ])
      .then(([price, programs]) => {
        setPriceHistory(price);
        setTickerBuybacks(programs.filter((b) => b.ticker === selectedTicker));
      })
      .catch(() => {
        setPriceHistory([]);
        setTickerBuybacks([]);
      })
      .finally(() => setChartLoading(false));
  }, [selectedTicker]);

  function toggleSort(field: BuybackSortField) {
    if (field === sortBy) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortBy(field);
      setSortDir("asc");
    }
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-bold">Recompras</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
          Programas de recompra de ações declarados à CVM — dado oficial (Eventos Societários Especiais), atualizado diariamente.
          Clique num ativo da lista pra ver a cotação.
        </p>
      </div>

      {selectedTicker && (
        <div className="smb-card p-4">
          <div className="flex justify-between items-center mb-2">
            <div className="font-semibold">
              Cotação ({PRICE_YEARS} anos) — <span style={{ color: "var(--gold)" }}>{selectedTicker}</span>
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
              <ReactECharts
                option={buildChartOption(priceHistory, tickerBuybacks)}
                style={{ height: 620 }}
                notMerge
                onChartReady={onChartReady}
              />
              <div className="text-xs mt-1" style={{ color: "var(--text3)" }}>
                Candlestick = cotação diária real via B3 (COTAHIST). Histograma embaixo = quantidade TOTAL autorizada
                (ON+PN) nos programas de recompra declarados naquele mês — a CVM não divulga a execução diária (quanto
                foi de fato recomprado dia a dia), só o programa declarado. Arraste em qualquer direção (tempo e escala
                vertical juntos) e role o mouse pra dar zoom — funciona nos dois gráficos, cada um de forma independente.
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
          {STATUS_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => setStatus(o.value)}
              className="smb-card px-3 py-1.5 text-sm"
              style={{ color: status === o.value ? "var(--gold)" : "var(--text2)" }}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div className="smb-card smb-table-wrap">
        <table className="smb-table w-full">
          <thead>
            <tr>
              <SortableTh label="Empresa" active={sortBy === "ticker"} dir={sortDir} onClick={() => toggleSort("ticker")} />
              <th>CNPJ</th>
              <th>Situação</th>
              <th>Tipo</th>
              <SortableTh label="Declarado em" align="right" active={sortBy === "declared_at"} dir={sortDir} onClick={() => toggleSort("declared_at")} />
              <SortableTh label="Prazo final" align="right" active={sortBy === "deadline"} dir={sortDir} onClick={() => toggleSort("deadline")} />
              <SortableTh label="Qtd ON" align="right" active={sortBy === "qty_common_shares"} dir={sortDir} onClick={() => toggleSort("qty_common_shares")} />
              <SortableTh label="Qtd PN" align="right" active={sortBy === "qty_preferred_shares"} dir={sortDir} onClick={() => toggleSort("qty_preferred_shares")} />
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} title={r.reason ?? undefined}>
                <td
                  style={{ color: "var(--text)", cursor: r.ticker ? "pointer" : "default" }}
                  onClick={() => r.ticker && setSelectedTicker(r.ticker)}
                >
                  <div style={{ fontWeight: 600, color: r.ticker ? "var(--gold)" : "var(--text)" }}>{r.ticker ?? "—"}</div>
                  <div className="text-xs" style={{ color: "var(--text3)" }}>{r.company_name}</div>
                </td>
                <td style={{ color: "var(--text3)" }}>{r.cnpj}</td>
                <td>
                  <StatusBadge status={r.status} />
                </td>
                <td style={{ color: "var(--text3)" }}>{r.operation_type ?? "—"}</td>
                <td className="num" style={{ color: "var(--text3)" }}>{r.declared_at}</td>
                <td className="num" style={{ color: "var(--text3)" }}>{r.deadline ?? "—"}</td>
                <td className="num">{fmtNum(r.qty_common_shares)}</td>
                <td className="num">{fmtNum(r.qty_preferred_shares)}</td>
              </tr>
            ))}
            {!loading && rows.length === 0 && (
              <tr>
                <td colSpan={8} style={{ color: "var(--text3)" }}>
                  Nenhum programa de recompra encontrado.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
