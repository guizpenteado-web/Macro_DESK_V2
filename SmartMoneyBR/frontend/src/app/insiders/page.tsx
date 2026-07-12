"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api, InsiderTrade, InsiderSortField, PricePoint } from "@/lib/api";
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

// Candlestick (grid 0) 100% limpo — nada sobreposto. Triangulos de insider
// foram removidos: negociacoes de insider as vezes vem com preco_unitario=0
// no dado bruto da CVM (ex: "Outras Entradas", que nao e' uma compra/venda
// de mercado de verdade) — um ponto assim na mesma escala Y do candlestick
// distorcia o auto-scale do preco, espremendo o candlestick real la em cima.
// Insiders aparecem SO no histograma embaixo (grid 1), e agregados por MES
// (nao por dia) — com 10 anos de dado diario cada barra ficaria com menos de
// 1px de largura e sumiria sem dar zoom; agregado por mes vira ~120 barras,
// sempre visiveis, sem precisar de zoom nenhum nesse grafico.
function buildChartOption(priceHistory: PricePoint[], insiderTrades: InsiderTrade[]) {
  const dates = priceHistory.map((p) => p.date);

  const tradesByDate = new Map<string, InsiderTrade[]>();
  for (const t of insiderTrades) {
    if (!t.data_movimentacao) continue;
    tradesByDate.set(t.data_movimentacao, [...(tradesByDate.get(t.data_movimentacao) ?? []), t]);
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
  const insiderMonthlyData: (number | null)[] = new Array(months.length).fill(null);
  for (const t of insiderTrades) {
    if (!t.data_movimentacao || t.quantidade === null) continue;
    const idx = monthIndex.get(t.data_movimentacao.slice(0, 7));
    if (idx === undefined) continue;
    const signedQty = t.direction === "VENDA" ? -t.quantidade : t.quantidade;
    insiderMonthlyData[idx] = (insiderMonthlyData[idx] ?? 0) + signedQty;
  }

  return {
    backgroundColor: "transparent",
    animation: false,
    grid: [
      { left: 64, right: 24, top: 30, height: "62%" },
      { left: 64, right: 24, top: "80%", height: "14%" },
    ],
    legend: {
      data: ["Cotação", "Insiders (qtd negociada)"],
      textStyle: { color: "var(--text2)" },
      top: 0,
    },
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
        data: months,
        axisLine: { lineStyle: { color: "#565f75" } },
        axisLabel: { color: "var(--text3)", interval: Math.ceil(months.length / 12) },
      },
    ],
    yAxis: [
      {
        id: "yPrice",
        type: "value",
        gridIndex: 0,
        scale: true,
        name: "R$",
        axisLine: { lineStyle: { color: "#565f75" } },
        splitLine: { lineStyle: { color: "#232838" } },
        axisLabel: { color: "var(--text3)" },
      },
      {
        id: "yInsiders",
        type: "value",
        gridIndex: 1,
        name: "Qtd insiders/mês",
        nameTextStyle: { color: "var(--text3)" },
        axisLine: { lineStyle: { color: "#565f75" } },
        splitLine: { show: false },
        axisLabel: { color: "var(--text3)" },
      },
    ],
    // Um dataZoom "inside" POR GRID, cada um controlando X e Y JUNTOS do seu
    // proprio grid (nao compartilhados entre si) — arrastar em qualquer
    // direcao move o grafico (tempo E escala vertical ao mesmo tempo), rolar
    // o mouse da zoom nos dois eixos. Ter os dois eixos no MESMO componente
    // (em vez de um componente so pra X e outro so pra Y) evita a disputa de
    // gesto que já causou bug antes — cada grid e' totalmente independente.
    dataZoom: [
      { type: "inside", xAxisIndex: [0], yAxisIndex: [0], zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
      { type: "inside", xAxisIndex: [1], yAxisIndex: [1], zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
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
          const trades = tradesByDate.get(p.date);
          if (trades?.length) {
            for (const t of trades) {
              html += `<br/><b style="color:${t.direction === "VENDA" ? "#ef4444" : "#22c55e"}">${t.direction ?? "—"} insider: ${t.quantidade?.toLocaleString("pt-BR")}${t.preco_unitario ? ` @ ${fmtPrice(t.preco_unitario)}` : ""}</b>`;
            }
          }
          return html;
        }
        const barParam = arr.find((p) => p.seriesType === "bar");
        if (barParam) {
          const val = insiderMonthlyData[barParam.dataIndex];
          return `${months[barParam.dataIndex]}<br/>Qtd insiders: ${val !== null ? val.toLocaleString("pt-BR") : 0}`;
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
        name: "Insiders (qtd negociada)",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: insiderMonthlyData,
        barMaxWidth: 14,
        itemStyle: {
          color: (p: { value: number | null }) => ((p.value ?? 0) >= 0 ? "#22c55e" : "#ef4444"),
        },
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
  const [tickerTrades, setTickerTrades] = useState<InsiderTrade[]>([]);
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
    Promise.all([
      api.getPriceHistory(selectedTicker, PRICE_YEARS),
      // todas as negociacoes do ticker, direction="" (compra+venda), sem
      // depender do filtro da tabela — o grafico mostra tudo, sempre.
      api.getInsiderTrades({ search: selectedTicker, direction: "", limit: 500 }),
    ])
      .then(([price, trades]) => {
        setPriceHistory(price);
        setTickerTrades(trades.filter((t) => t.ticker === selectedTicker));
      })
      .catch(() => {
        setPriceHistory([]);
        setTickerTrades([]);
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
              <ReactECharts option={buildChartOption(priceHistory, tickerTrades)} style={{ height: 620 }} notMerge />
              <div className="text-xs mt-1" style={{ color: "var(--text3)" }}>
                Candlestick = cotação diária real via B3 (COTAHIST), não vem da CVM. Histograma embaixo = negociações
                de insider dessa empresa agregadas por mês (verde = compra líquida, vermelho = venda líquida) — mesma
                lista da tabela abaixo. Recompras da empresa foram tiradas daqui por enquanto. Arraste em qualquer
                direção (tempo e escala vertical juntos) e role o mouse pra dar zoom — funciona nos dois gráficos,
                cada um de forma independente.
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
