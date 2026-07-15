"use client";

import { useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import { api, AssetHistoryPoint, PricePoint } from "@/lib/api";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

const PRICE_YEARS = 10;

function fmtPrice(v: number) {
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtBRLmi(v: number) {
  return `R$ ${(v / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}mi`;
}

// Mesma tecnica de pan vertical manual do insiders/page.tsx e recompras/page.tsx
// — dataZoom "inside" do ECharts nao responde a arrasto vertical mesmo com
// xAxisIndex+yAxisIndex combinados (achado 14/jul/2026), entao cada grid tem
// seu proprio pan feito via zrender + dispatchAction.
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
    // arrastar pra baixo revela valores mais altos, como arrastar um mapa
    // (achado 14/jul/2026: sinal estava invertido).
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

// Layout: candlestick (grid 0) + 3 paineis empilhados (%PL, Qtd Ações,
// Valor da Posição) — mesmo espirito do "carteirafundos.com" que o usuário
// trouxe como referência (14/jul/2026), sem o painel de "Exposição
// Relativa" (definição não confirmada, deixado de fora por pedido do
// usuário).
//
// Eixo X tipo "time" (nao "category") em todos os 4 grids — achado
// 14/jul/2026: com eixo category, cada grid espalha seus proprios pontos
// igualmente pela largura (candlestick tem ~2500 pregões diários, os
// paineis mensais tem ~56 pontos), entao uma mesma data cai em pixels
// DIFERENTES em cada grid — desalinha visualmente ao longo dos 10 anos.
// Eixo "time" posiciona pelo valor real da data, entao series com
// densidades bem diferentes ficam alinhadas de verdade.
function buildOption(priceHistory: PricePoint[], history: AssetHistoryPoint[]) {
  let priceMin = Infinity;
  let priceMax = -Infinity;
  for (const p of priceHistory) {
    priceMin = Math.min(priceMin, p.low);
    priceMax = Math.max(priceMax, p.high);
  }
  const pricePad = (priceMax - priceMin) * 0.08 || 1;
  const yPriceMin = priceHistory.length ? priceMin - pricePad : undefined;
  const yPriceMax = priceHistory.length ? priceMax + pricePad : undefined;

  // Cada grid com eixo "time" auto-escala pro proprio intervalo de datas da
  // SUA serie — se a carteira do fundo nesse ativo nao cobre exatamente o
  // mesmo periodo da cotacao de 10 anos (ex: fundo so passou a ter posicao
  // a partir de 2019), os 4 eixos ficam com inicio/fim diferentes mesmo
  // sendo todos "time", e um ponto no meio do grafico ainda cai em datas
  // diferentes por grid (achado 14/jul/2026, restante do desalinhamento
  // apos trocar category->time). Forcar o MESMO min/max explicito (uniao
  // das duas series) nos 4 eixos resolve de vez.
  const allDates = [...priceHistory.map((p) => p.date), ...history.map((h) => h.ref_date)].sort();
  const xMin = allDates.length ? allDates[0] : undefined;
  const xMax = allDates.length ? allDates[allDates.length - 1] : undefined;

  // O eixo cobre os 10 anos inteiros de cotacao, mas a maioria dos fundos so
  // segurou o ativo numa janela bem menor que isso (ex: 14 meses) — sem isso,
  // as barras de posicao ficam espremidas numa fatia minuscula no canto
  // direito, com um vazio enorme a esquerda que parece bug (achado 14/jul/2026,
  // usuario reportou "gaps enormes e desajustados" em varios ativos). O dado
  // em si esta certo (fundo so passou a ter posicao naquela data) — o que
  // precisa mudar e' o ZOOM inicial, nao o eixo: comeca focado no periodo em
  // que o fundo realmente teve posicao (+ folga), mas o usuario ainda
  // consegue arrastar/dar zoom out pra ver os 10 anos completos se quiser.
  const histDates = history.map((h) => h.ref_date).sort();
  let dataZoomStart = 0;
  let dataZoomEnd = 100;
  if (histDates.length && xMin && xMax) {
    const xMinTs = new Date(xMin).getTime();
    const xMaxTs = new Date(xMax).getTime();
    const histMinTs = new Date(histDates[0]).getTime();
    const histMaxTs = new Date(histDates[histDates.length - 1]).getTime();
    const totalSpan = xMaxTs - xMinTs || 1;
    const DAY = 24 * 60 * 60 * 1000;
    const pad = Math.max((histMaxTs - histMinTs) * 0.15, 60 * DAY);
    dataZoomStart = Math.max(0, ((histMinTs - pad - xMinTs) / totalSpan) * 100);
    dataZoomEnd = Math.min(100, ((histMaxTs + pad - xMinTs) / totalSpan) * 100);
  }

  const axisLineStyle = { lineStyle: { color: "rgba(255,255,255,.08)" } };

  return {
    backgroundColor: "transparent",
    animation: false,
    grid: [
      { left: 70, right: 24, top: 24, height: "38%" },
      { left: 70, right: 24, top: "46%", height: "14%" },
      { left: 70, right: 24, top: "65%", height: "14%" },
      { left: 70, right: 24, top: "84%", height: "14%" },
    ],
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    xAxis: [
      { type: "time", gridIndex: 0, min: xMin, max: xMax, axisLine: axisLineStyle, axisLabel: { show: false }, axisTick: { show: false } },
      { type: "time", gridIndex: 1, min: xMin, max: xMax, axisLine: axisLineStyle, axisLabel: { show: false }, axisTick: { show: false } },
      { type: "time", gridIndex: 2, min: xMin, max: xMax, axisLine: axisLineStyle, axisLabel: { show: false }, axisTick: { show: false } },
      { type: "time", gridIndex: 3, min: xMin, max: xMax, axisLine: axisLineStyle, axisLabel: { color: "#4a5b73" } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, min: yPriceMin, max: yPriceMax, name: "R$", axisLine: axisLineStyle, splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } }, axisLabel: { color: "#4a5b73" } },
      { type: "value", gridIndex: 1, name: "% PL", nameTextStyle: { color: "#4a5b73" }, axisLine: axisLineStyle, splitLine: { show: false }, axisLabel: { color: "#4a5b73" } },
      { type: "value", gridIndex: 2, name: "Qtd Ações", nameTextStyle: { color: "#4a5b73" }, axisLine: axisLineStyle, splitLine: { show: false }, axisLabel: { color: "#4a5b73" } },
      { type: "value", gridIndex: 3, name: "Valor", nameTextStyle: { color: "#4a5b73" }, axisLine: axisLineStyle, splitLine: { show: false }, axisLabel: { color: "#4a5b73", formatter: (v: number) => fmtBRLmi(v) } },
    ],
    // X compartilhado entre os 4 grids num dataZoom so — arrastar/dar zoom
    // em qualquer painel move todos juntos (igual ao site de referencia).
    // Y continua um dataZoom por grid (escalas bem diferentes entre painéis).
    dataZoom: [
      {
        type: "inside",
        xAxisIndex: [0, 1, 2, 3],
        start: dataZoomStart,
        end: dataZoomEnd,
        zoomOnMouseWheel: true,
        moveOnMouseMove: true,
        moveOnMouseWheel: false,
      },
      { type: "inside", yAxisIndex: [0], zoomOnMouseWheel: true, moveOnMouseMove: false, moveOnMouseWheel: false },
      { type: "inside", yAxisIndex: [1], zoomOnMouseWheel: true, moveOnMouseMove: false, moveOnMouseWheel: false },
      { type: "inside", yAxisIndex: [2], zoomOnMouseWheel: true, moveOnMouseMove: false, moveOnMouseWheel: false },
      { type: "inside", yAxisIndex: [3], zoomOnMouseWheel: true, moveOnMouseMove: false, moveOnMouseWheel: false },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "cross" },
      formatter: (params: unknown) => {
        const arr = params as { seriesType: string; seriesName: string; dataIndex: number }[];
        const priceParam = arr.find((p) => p.seriesType === "candlestick");
        if (priceParam) {
          const p = priceHistory[priceParam.dataIndex];
          if (!p) return "";
          return `${p.date}<br/>Abertura: ${fmtPrice(p.open)}<br/>Máxima: ${fmtPrice(p.high)}<br/>Mínima: ${fmtPrice(p.low)}<br/>Fechamento: ${fmtPrice(p.close)}`;
        }
        const barParam = arr.find((p) => p.seriesType === "bar");
        if (barParam) {
          const h = history[barParam.dataIndex];
          if (!h) return "";
          return (
            `${h.ref_date}<br/>` +
            `% do PL: ${h.pct_of_fund !== null ? h.pct_of_fund.toFixed(2) + "%" : "—"}<br/>` +
            `Qtd ações: ${h.quantity.toLocaleString("pt-BR")}<br/>` +
            `Valor: ${fmtBRLmi(h.market_value)}`
          );
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
        data: priceHistory.map((p) => [p.date, p.open, p.close, p.low, p.high]),
        encode: { x: 0, y: [1, 2, 3, 4] },
        itemStyle: { color: "#22c55e", color0: "#ef4444", borderColor: "#22c55e", borderColor0: "#ef4444" },
      },
      {
        name: "% do PL",
        type: "bar",
        xAxisIndex: 1,
        yAxisIndex: 1,
        data: history.map((h) => [h.ref_date, h.pct_of_fund]),
        barMaxWidth: 14,
        itemStyle: { color: "#58a6ff" },
      },
      {
        name: "Qtd Ações",
        type: "bar",
        xAxisIndex: 2,
        yAxisIndex: 2,
        data: history.map((h) => [h.ref_date, h.quantity]),
        barMaxWidth: 14,
        itemStyle: { color: "#94a3b8" },
      },
      {
        name: "Valor da Posição",
        type: "bar",
        xAxisIndex: 3,
        yAxisIndex: 3,
        data: history.map((h) => [h.ref_date, h.market_value]),
        barMaxWidth: 14,
        itemStyle: { color: "#22c55e" },
      },
    ],
  };
}

export default function FundAssetPositionChart({
  fundId,
  assetId,
  ticker,
}: {
  fundId: number;
  assetId: number;
  ticker: string;
}) {
  const [priceHistory, setPriceHistory] = useState<PricePoint[]>([]);
  const [history, setHistory] = useState<AssetHistoryPoint[]>([]);
  const [loading, setLoading] = useState(false);
  const panCleanupRef = useRef<(() => void)[]>([]);

  useEffect(() => {
    setLoading(true);
    Promise.all([api.getPriceHistory(ticker, PRICE_YEARS), api.getFundAssetHistory(fundId, assetId)])
      .then(([price, hist]) => {
        setPriceHistory(price);
        setHistory(hist);
      })
      .catch(() => {
        setPriceHistory([]);
        setHistory([]);
      })
      .finally(() => setLoading(false));
  }, [fundId, assetId, ticker]);

  function onChartReady(chart: any) {
    panCleanupRef.current.forEach((fn) => fn());
    panCleanupRef.current = [0, 1, 2, 3].map((i) => attachVerticalPan(chart, i));
  }

  if (loading) {
    return (
      <div className="text-sm" style={{ color: "var(--text3)" }}>
        Carregando cotação (primeira consulta de um ano novo pode levar alguns segundos)...
      </div>
    );
  }
  if (priceHistory.length === 0) {
    return (
      <div className="text-sm" style={{ color: "var(--text3)" }}>
        Sem cotação na B3 pra {ticker} (pode ser ticker sem negociação em bolsa, FII, ou código incorreto).
      </div>
    );
  }

  return (
    <>
      <ReactECharts option={buildOption(priceHistory, history)} style={{ height: 720 }} notMerge onChartReady={onChartReady} />
      <div className="text-xs mt-1" style={{ color: "var(--text3)" }}>
        Candlestick = cotação diária real via B3 (COTAHIST). Painéis abaixo = % do PL do fundo, quantidade de ações e
        valor da posição nesse ativo, mês a mês. Visão inicial focada no período em que o fundo teve posição — role o
        mouse pra dar zoom out e ver os 10 anos completos de cotação. Arraste em qualquer direção (tempo e escala
        vertical juntos) — funciona em cada gráfico de forma independente.
      </div>
    </>
  );
}
