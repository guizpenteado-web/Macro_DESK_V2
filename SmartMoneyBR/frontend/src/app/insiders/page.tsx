"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { api, InsiderTrade, InsiderSortField, PricePoint } from "@/lib/api";
import SortableTh from "@/components/SortableTh";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

function NumField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text3)" }}>
      {label}
      <input
        type="number"
        className="smb-card px-2 py-1 outline-none text-sm"
        style={{ color: "var(--text)" }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="flex flex-col gap-1 text-xs" style={{ color: "var(--text3)" }}>
      {label}
      <input
        type="date"
        className="smb-card px-2 py-1 outline-none text-sm"
        style={{ color: "var(--text)" }}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </label>
  );
}

// dataZoom "inside" nao suporta arrasto vertical nativo combinado com o
// horizontal (achado 14/jul/2026) — pan vertical feito manualmente via
// zrender + dispatchAction. Duas causas raiz do "travado" that a 1a tentativa
// (so tirar yAxis.scale:true) e a 2a tentativa (mousedown/mousemove sem
// containPixel nem dataZoomId, achando o componente por yAxisIndex) nao
// resolveram, confirmadas com instrumentacao (achado 14/jul/2026):
// 1. dispatchAction({type:'dataZoom', yAxisIndex, start, end}) SEM
//    dataZoomIndex/dataZoomId explicito atualiza os 4 componentes (X e Y dos
//    dois grids) ao MESMO tempo com os MESMOS valores -- arrastar o eixo Y do
//    candlestick tambem reescrevia o zoom X dos dois graficos, produzindo
//    comportamento erratico que parecia "travado". Fix: cada dataZoom tem um
//    id proprio, dispatch usa dataZoomId (nao axisIndex) pra atingir so um.
// 2. Os dois handlers (grid 0 e grid 1) ficavam escutando o zrender inteiro
//    sem checar sobre qual grid o mouse estava -- arrastar no candlestick
//    tambem disparava o pan do histograma embaixo. Fix: chart.containPixel
//    checa se o ponto do mousedown cai dentro do grid antes de comecar o
//    drag.
function attachVerticalPan(chart: any, gridIndex: number, dataZoomId: string) {
  const zr = chart.getZr();
  let dragging = false;
  let lastY = 0;

  function onDown(params: any) {
    if (!chart.containPixel({ gridIndex }, [params.offsetX, params.offsetY])) return;
    dragging = true;
    lastY = params.offsetY;
  }
  function onMove(params: any) {
    if (!dragging) return;
    const dy = params.offsetY - lastY;
    lastY = params.offsetY;
    if (!dy) return;

    const opt = chart.getOption();
    const dz = (opt.dataZoom || []).find((d: any) => d.id === dataZoomId);
    if (!dz) return;
    const start = dz.start ?? 0;
    const end = dz.end ?? 100;
    const span = end - start;
    const height = chart.getHeight();
    // arrastar pra baixo revela valores mais altos, como arrastar um mapa
    // (achado 14/jul/2026: sinal estava invertido — usuario reportou eixo
    // vertical de tras pra frente).
    const deltaPct = (dy / height) * span;
    let newStart = start + deltaPct;
    let newEnd = end + deltaPct;
    if (newStart < 0) {
      newEnd += -newStart;
      newStart = 0;
    }
    if (newEnd > 100) {
      newStart -= newEnd - 100;
      newEnd = 100;
    }
    chart.dispatchAction({ type: "dataZoom", dataZoomId, start: newStart, end: newEnd });
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

// Toggles independentes (nao mais radio Compras/Vendas) — pedido do usuario
// 14/jul/2026. Cada um liga/desliga por conta propria; os dois desligados
// manda direction="NONE" pro backend (nao "sem filtro", que traria de volta
// tipo_movimentacao societario com direction=None, ja excluido de proposito
// antes: Outras Entradas, Desligamento/saida, Grupamento, Subscricao etc).
function directionParam(showCompras: boolean, showVendas: boolean): "COMPRA" | "VENDA" | "COMPRA,VENDA" | "NONE" {
  if (showCompras && showVendas) return "COMPRA,VENDA";
  if (showCompras) return "COMPRA";
  if (showVendas) return "VENDA";
  return "NONE";
}

// Candlestick (grid 0) 100% limpo — nada sobreposto. Triangulos de insider
// foram removidos: negociacoes de insider as vezes vem com preco_unitario=0
// no dado bruto da CVM (ex: "Outras Entradas", que nao e' uma compra/venda
// de mercado de verdade) — um ponto assim na mesma escala Y do candlestick
// distorcia o auto-scale do preco, espremendo o candlestick real la em cima.
// Insiders aparecem SO no histograma embaixo (grid 1), e agregados por MES
// (nao por dia) — com 10 anos de dado diario cada barra ficaria com menos de
// 1px de largura e sumiria sem dar zoom; agregado por mes vira ~120 barras,
// sempre visiveis, sem precisar de zoom nenhum nesse grafico.
// Log aplicado ao eixo Y do candlestick (grid 0) usa yAxis.type:"log" direto
// (preco e' sempre positivo). Ja o histograma de insiders (grid 1) tem
// barra negativa (venda liquida) — log axis nativo do ECharts exige valor
// estritamente positivo, entao "log" ali e' feito transformando o proprio
// dado (sign(v) * log10(1+abs(v))) em vez do tipo do eixo, com o
// axisLabel formatado de volta pra escala real (achado 14/jul/2026).
function symlog(v: number) {
  return Math.sign(v) * Math.log10(1 + Math.abs(v));
}
function invSymlog(v: number) {
  return Math.sign(v) * (Math.pow(10, Math.abs(v)) - 1);
}

function buildChartOption(
  priceHistory: PricePoint[],
  insiderTrades: InsiderTrade[],
  logPrice: boolean,
  logInsiders: boolean,
  showBuyMarkers: boolean,
  showSellMarkers: boolean
) {
  const dates = priceHistory.map((p) => p.date);

  // min/max fixo (calculado uma vez, com folga de 8%) em vez de yAxis.scale:true
  // — scale:true recalcula o range toda vez que o grafico atualiza (inclusive
  // apos um pan/zoom manual), entao qualquer arraste vertical do usuario era
  // desfeito no proximo re-render, dando a sensacao de que so dava pra
  // navegar horizontalmente (achado 14/jul/2026).
  let priceMin = Infinity;
  let priceMax = -Infinity;
  for (const p of priceHistory) {
    priceMin = Math.min(priceMin, p.low);
    priceMax = Math.max(priceMax, p.high);
  }
  const pricePad = (priceMax - priceMin) * 0.08 || 1;
  const yPriceMinRaw = priceHistory.length ? priceMin - pricePad : undefined;
  const yPriceMax = priceHistory.length ? priceMax + pricePad : undefined;
  // eixo log nao aceita min <= 0 — se o padding linear derrubar o piso pra
  // zero/negativo, deixa o ECharts auto-calcular o minimo em modo log.
  const yPriceMin = logPrice && yPriceMinRaw !== undefined && yPriceMinRaw <= 0 ? undefined : yPriceMinRaw;

  const tradesByDate = new Map<string, InsiderTrade[]>();
  for (const t of insiderTrades) {
    if (!t.data_movimentacao) continue;
    tradesByDate.set(t.data_movimentacao, [...(tradesByDate.get(t.data_movimentacao) ?? []), t]);
  }

  // Marcadores de compra/venda no proprio candlestick — reintroduzidos
  // 14/jul/2026 como toggle opcional (tinham sido tirados antes por
  // distorcer o auto-scale do preco quando preco_unitario vinha 0 no dado
  // bruto da CVM). Agora que yPriceMin/yPriceMax sao fixos calculados so a
  // partir do proprio candlestick (nao mais scale:true), plotar os
  // marcadores no fechamento do dia (nao no preco_unitario, que pode ser 0
  // ou nao bater com a cotacao de fechamento) nao mexe em nada do eixo.
  const closeByDate = new Map(priceHistory.map((p) => [p.date, p.close]));
  const buyMarkerData: [string, number][] = [];
  const sellMarkerData: [string, number][] = [];
  for (const t of insiderTrades) {
    if (!t.data_movimentacao) continue;
    const close = closeByDate.get(t.data_movimentacao);
    if (close === undefined) continue;
    if (t.direction === "COMPRA") buyMarkerData.push([t.data_movimentacao, close]);
    else if (t.direction === "VENDA") sellMarkerData.push([t.data_movimentacao, close]);
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
    // So conta negociacao real (Compra/Venda classificadas na ingestao) —
    // tipo_movimentacao como Grupamento, Desdobramento/bonificacao,
    // Subscricao, Homologacao de subscricao e Acoes de plano de
    // remuneracao (direction=None) sao eventos societarios, nao compra/
    // venda de mercado, e vem com quantidade na casa dos bilhoes —
    // dominava a escala do eixo Y pra qualquer ativo que tivesse um desses
    // no historico, achatando os meses com negociacao real de verdade
    // (achado 14/jul/2026).
    if (t.direction !== "COMPRA" && t.direction !== "VENDA") continue;
    const idx = monthIndex.get(t.data_movimentacao.slice(0, 7));
    if (idx === undefined) continue;
    const signedQty = t.direction === "VENDA" ? -t.quantidade : t.quantidade;
    insiderMonthlyData[idx] = (insiderMonthlyData[idx] ?? 0) + signedQty;
  }
  const insiderMonthlyPlotData = logInsiders ? insiderMonthlyData.map((v) => (v === null ? null : symlog(v))) : insiderMonthlyData;

  return {
    backgroundColor: "transparent",
    animation: false,
    grid: [
      { left: 64, right: 24, top: 30, height: "62%" },
      { left: 64, right: 24, top: "80%", height: "14%" },
    ],
    legend: {
      data: ["Cotação", "Insiders (qtd negociada)"],
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
        type: logPrice ? "log" : "value",
        gridIndex: 0,
        min: yPriceMin,
        max: logPrice ? undefined : yPriceMax,
        name: "R$",
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } },
        axisLabel: { color: "#4a5b73" },
      },
      {
        id: "yInsiders",
        type: "value",
        gridIndex: 1,
        name: "Qtd insiders/mês",
        nameTextStyle: { color: "#4a5b73" },
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
        splitLine: { show: false },
        axisLabel: {
          color: "#4a5b73",
          formatter: logInsiders ? (val: number) => fmtNum(Math.round(invSymlog(val))) : undefined,
        },
      },
    ],
    // X mantem o dataZoom "inside" nativo (arrastar horizontal ja funciona
    // bem). Y fica num componente PROPRIO com moveOnMouseMove desligado —
    // o pan vertical e' feito manualmente por attachVerticalPan (o gesto
    // embutido do ECharts pra eixo Y combinado com X nao respondia ao
    // arrasto vertical, achado 14/jul/2026). Zoom por scroll continua nos
    // dois eixos normalmente.
    dataZoom: [
      { id: "xz0", type: "inside", xAxisIndex: [0], zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
      { id: "yz0", type: "inside", yAxisIndex: [0], zoomOnMouseWheel: true, moveOnMouseMove: false, moveOnMouseWheel: false },
      { id: "xz1", type: "inside", xAxisIndex: [1], zoomOnMouseWheel: true, moveOnMouseMove: true, moveOnMouseWheel: false },
      { id: "yz1", type: "inside", yAxisIndex: [1], zoomOnMouseWheel: true, moveOnMouseMove: false, moveOnMouseWheel: false },
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
        name: "Compras insiders",
        type: "scatter",
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: "triangle",
        symbolSize: 11,
        itemStyle: { color: "#22c55e", borderColor: "#0b1220", borderWidth: 1 },
        data: showBuyMarkers ? buyMarkerData : [],
        tooltip: { show: false },
        z: 5,
      },
      {
        name: "Vendas insiders",
        type: "scatter",
        xAxisIndex: 0,
        yAxisIndex: 0,
        symbol: "triangle",
        symbolRotate: 180,
        symbolSize: 11,
        itemStyle: { color: "#ef4444", borderColor: "#0b1220", borderWidth: 1 },
        data: showSellMarkers ? sellMarkerData : [],
        tooltip: { show: false },
        z: 5,
      },
      {
        name: "Insiders (qtd negociada)",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: insiderMonthlyPlotData,
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
  const [showCompras, setShowCompras] = useState(true);
  const [showVendas, setShowVendas] = useState(false);
  const [cargo, setCargo] = useState("");
  const [cargos, setCargos] = useState<string[]>([]);
  const [showFilters, setShowFilters] = useState(false);
  const [minQuantidade, setMinQuantidade] = useState("");
  const [maxQuantidade, setMaxQuantidade] = useState("");
  const [minVolume, setMinVolume] = useState("");
  const [maxVolume, setMaxVolume] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [sortBy, setSortBy] = useState<InsiderSortField>("data_movimentacao");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");
  const [rows, setRows] = useState<InsiderTrade[]>([]);
  const [loading, setLoading] = useState(false);
  const panCleanupRef = useRef<(() => void)[]>([]);

  function onChartReady(chart: any) {
    panCleanupRef.current.forEach((fn) => fn());
    panCleanupRef.current = [attachVerticalPan(chart, 0, "yz0"), attachVerticalPan(chart, 1, "yz1")];
  }

  const [selectedTicker, setSelectedTicker] = useState<string | null>(null);
  const [priceHistory, setPriceHistory] = useState<PricePoint[]>([]);
  const [tickerTrades, setTickerTrades] = useState<InsiderTrade[]>([]);
  const [chartLoading, setChartLoading] = useState(false);
  const [logPrice, setLogPrice] = useState(false);
  const [logInsiders, setLogInsiders] = useState(false);
  const [showBuyMarkers, setShowBuyMarkers] = useState(false);
  const [showSellMarkers, setShowSellMarkers] = useState(false);

  useEffect(() => {
    api.getInsiderCargos().then(setCargos).catch(() => setCargos([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    const handle = setTimeout(() => {
      api
        .getInsiderTrades({
          search: q,
          direction: directionParam(showCompras, showVendas),
          cargo,
          dateFrom: dateFrom || undefined,
          dateTo: dateTo || undefined,
          minQuantidade: minQuantidade ? Number(minQuantidade) : undefined,
          maxQuantidade: maxQuantidade ? Number(maxQuantidade) : undefined,
          minVolume: minVolume ? Number(minVolume) : undefined,
          maxVolume: maxVolume ? Number(maxVolume) : undefined,
          sortBy,
          sortDir,
          limit: 150,
        })
        .then(setRows)
        .catch(() => setRows([]))
        .finally(() => setLoading(false));
    }, 300);
    return () => clearTimeout(handle);
  }, [q, showCompras, showVendas, cargo, dateFrom, dateTo, minQuantidade, maxQuantidade, minVolume, maxVolume, sortBy, sortDir]);

  useEffect(() => {
    if (!selectedTicker) return;
    setChartLoading(true);
    Promise.all([
      api.getPriceHistory(selectedTicker, PRICE_YEARS),
      // todas as negociacoes do ticker, direction="" (compra+venda), sem
      // depender do filtro da tabela — o grafico mostra tudo, sempre.
      // limit alto (nao 500): achado 14/jul/2026 — RADL3 sozinho tem 5.853
      // negociacoes datadas, ITUB3 3.227, BBDC3 2.460 etc.; com limit:500 e
      // sort padrao (data desc), o grafico "Qtd insiders/mes" silenciosamente
      // cortava tudo que fosse mais antigo que as ~500 negociacoes mais
      // recentes — sumindo meses inteiros de historico pra qualquer acao
      // com muitos insiders/anos de negociacao.
      api.getInsiderTrades({ search: selectedTicker, direction: "", limit: 20000 }),
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
              Cotação ({PRICE_YEARS} anos) — <span style={{ color: "var(--gold)" }}>{selectedTicker}</span>
            </div>
            <div className="flex items-center gap-3 flex-wrap justify-end">
              <button
                className="text-xs px-2 py-1 smb-card"
                style={{ color: showBuyMarkers ? "var(--green)" : "var(--text3)" }}
                title="Marcar no gráfico os dias com compra de insider"
                onClick={() => setShowBuyMarkers((v) => !v)}
              >
                ▲ Compras
              </button>
              <button
                className="text-xs px-2 py-1 smb-card"
                style={{ color: showSellMarkers ? "var(--red)" : "var(--text3)" }}
                title="Marcar no gráfico os dias com venda de insider"
                onClick={() => setShowSellMarkers((v) => !v)}
              >
                ▼ Vendas
              </button>
              <button
                className="text-xs px-2 py-1 smb-card"
                style={{ color: logPrice ? "var(--gold)" : "var(--text3)" }}
                title="Escala vertical da cotação: linear/log"
                onClick={() => setLogPrice((v) => !v)}
              >
                Log
              </button>
              <button
                className="text-xs px-2 py-1 smb-card"
                style={{ color: logInsiders ? "var(--gold)" : "var(--text3)" }}
                title="Escala vertical de Qtd insiders/mês: linear/log"
                onClick={() => setLogInsiders((v) => !v)}
              >
                Log insiders
              </button>
              <button onClick={() => setSelectedTicker(null)} style={{ color: "var(--text3)" }}>
                fechar ✕
              </button>
            </div>
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
                option={buildChartOption(priceHistory, tickerTrades, logPrice, logInsiders, showBuyMarkers, showSellMarkers)}
                style={{ height: 620 }}
                notMerge
                onChartReady={onChartReady}
              />
              <div className="text-xs mt-1" style={{ color: "var(--text3)" }}>
                Candlestick = cotação diária real via B3 (COTAHIST), não vem da CVM. Histograma embaixo = negociações
                de insider dessa empresa agregadas por mês (verde = compra líquida, vermelho = venda líquida) — mesma
                lista da tabela abaixo. Recompras da empresa foram tiradas daqui por enquanto. Botões ▲ Compras/▼
                Vendas marcam no próprio candlestick os dias exatos com negociação de insider (posição = fechamento do
                dia, não o preço da negociação em si). Arraste em qualquer direção (tempo e escala vertical juntos) e
                role o mouse pra dar zoom — funciona nos dois gráficos, cada um de forma independente.
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
          <button
            onClick={() => setShowCompras((v) => !v)}
            className="smb-card px-3 py-1.5 text-sm"
            style={{
              color: showCompras ? "var(--green)" : "var(--text2)",
              border: showCompras ? "1px solid var(--green)" : undefined,
            }}
          >
            Compras
          </button>
          <button
            onClick={() => setShowVendas((v) => !v)}
            className="smb-card px-3 py-1.5 text-sm"
            style={{
              color: showVendas ? "var(--red)" : "var(--text2)",
              border: showVendas ? "1px solid var(--red)" : undefined,
            }}
          >
            Vendas
          </button>
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

        <button
          className="smb-card px-3 py-1.5 text-sm"
          style={{ color: showFilters ? "var(--gold)" : "var(--text2)" }}
          onClick={() => setShowFilters((v) => !v)}
        >
          Filtros {showFilters ? "▲" : "▼"}
        </button>
      </div>

      {showFilters && (
        <div className="smb-card p-3 flex flex-wrap gap-3 items-end">
          <NumField label="Qtd mín" value={minQuantidade} onChange={setMinQuantidade} />
          <NumField label="Qtd máx" value={maxQuantidade} onChange={setMaxQuantidade} />
          <NumField label="Volume mín (R$)" value={minVolume} onChange={setMinVolume} />
          <NumField label="Volume máx (R$)" value={maxVolume} onChange={setMaxVolume} />
          <DateField label="Data de" value={dateFrom} onChange={setDateFrom} />
          <DateField label="Data até" value={dateTo} onChange={setDateTo} />
          <button
            className="smb-card px-3 py-1.5 text-sm"
            style={{ color: "var(--text3)" }}
            onClick={() => {
              setMinQuantidade("");
              setMaxQuantidade("");
              setMinVolume("");
              setMaxVolume("");
              setDateFrom("");
              setDateTo("");
            }}
          >
            Limpar filtros
          </button>
        </div>
      )}

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
                  <div style={{ fontWeight: 600, color: r.ticker ? "var(--gold)" : "var(--text)" }}>{r.ticker ?? "—"}</div>
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
