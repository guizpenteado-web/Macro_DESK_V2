"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { api, FlowEvolution } from "@/lib/api";

const ReactECharts = dynamic(() => import("echarts-for-react"), { ssr: false });

function fmtBRL(v: number) {
  if (Math.abs(v) >= 1_000_000_000) return `R$ ${(v / 1_000_000_000).toFixed(1)}bi`;
  if (Math.abs(v) >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(0)}mi`;
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
}

function fmtX(v: number) {
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}x`;
}

export default function EvolucaoPage() {
  const [data, setData] = useState<FlowEvolution | null>(null);

  useEffect(() => {
    api.getFlowEvolution().then(setData).catch(() => setData({ months: [], avg_total_value_bought: null, avg_n_funds_buying: null }));
  }, []);

  if (!data) return <div style={{ color: "var(--text2)" }}>Carregando...</div>;

  const months = data.months;
  const top5 = [...months].sort((a, b) => b.coordination_score - a.coordination_score).slice(0, 8);

  const chartOption = {
    backgroundColor: "transparent",
    grid: { left: 70, right: 70, top: 40, bottom: 60 },
    legend: {
      data: ["Valor investido (novas/aumentadas)", "Nº de fundos comprando"],
      textStyle: { color: "#7d90a8" },
      top: 0,
    },
    xAxis: {
      type: "category",
      data: months.map((m) => m.ref_date),
      axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
      axisLabel: { rotate: 45, color: "#4a5b73" },
    },
    yAxis: [
      {
        type: "value",
        name: "Valor (R$)",
        position: "left",
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
        splitLine: { lineStyle: { color: "rgba(255,255,255,.05)" } },
        axisLabel: { formatter: (v: number) => fmtBRL(v), color: "#4a5b73" },
      },
      {
        type: "value",
        name: "Nº fundos",
        position: "right",
        axisLine: { lineStyle: { color: "rgba(255,255,255,.08)" } },
        splitLine: { show: false },
        axisLabel: { color: "#4a5b73" },
      },
    ],
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const arr = params as { dataIndex: number }[];
        const m = months[arr[0].dataIndex];
        return `${m.ref_date}<br/>Valor: ${fmtBRL(m.total_value_bought)} (${fmtX(m.value_vs_avg)} da média)<br/>Fundos comprando: ${m.n_funds_buying} / ${m.n_funds_active} (${fmtX(m.funds_vs_avg)} da média)<br/><b>Score de coordenação: ${m.coordination_score.toFixed(2)}</b>`;
      },
    },
    series: [
      {
        name: "Valor investido (novas/aumentadas)",
        type: "bar",
        yAxisIndex: 0,
        data: months.map((m) => m.total_value_bought),
        itemStyle: { color: "#22c55e" },
      },
      {
        name: "Nº de fundos comprando",
        type: "line",
        yAxisIndex: 1,
        data: months.map((m) => m.n_funds_buying),
        lineStyle: { color: "#c9a227", width: 2 },
        itemStyle: { color: "#c9a227" },
        symbol: "circle",
        symbolSize: 6,
      },
    ],
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">Evolução</h1>
        <p className="text-sm mt-1" style={{ color: "var(--text2)" }}>
          Fluxo agregado de TODOS os fundos rastreados, mês a mês: valor total investido em posições novas/aumentadas
          e quantos fundos distintos compraram junto. O insight: quando valor E número de fundos sobem acima da
          média ao mesmo tempo, é sinal de fluxo institucional coordenado — mais chance de mover preço.
        </p>
        {data.avg_total_value_bought !== null && (
          <div className="flex gap-4 mt-2 text-sm">
            <span style={{ color: "var(--text3)" }}>
              Média mensal: <span style={{ color: "var(--text)", fontWeight: 600 }}>{fmtBRL(data.avg_total_value_bought)}</span>
            </span>
            <span style={{ color: "var(--text3)" }}>
              Fundos comprando em média: <span style={{ color: "var(--text)", fontWeight: 600 }}>{Math.round(data.avg_n_funds_buying ?? 0)}</span>
            </span>
          </div>
        )}
      </div>

      <div className="smb-card p-4">
        {months.length > 0 ? (
          <ReactECharts option={chartOption} style={{ height: 380 }} />
        ) : (
          <div className="text-sm" style={{ color: "var(--text3)" }}>Sem dados suficientes ainda.</div>
        )}
      </div>

      <div>
        <h2 className="font-semibold mb-2">Picos de fluxo coordenado</h2>
        <p className="text-xs mb-2" style={{ color: "var(--text3)" }}>
          Meses onde valor investido E número de fundos comprando ficaram, juntos, mais acima da média — ordenado
          pelo score de coordenação (valor acima da média × fundos acima da média).
        </p>
        <div className="smb-card smb-table-wrap">
          <table className="smb-table w-full">
            <thead>
              <tr>
                <th className="num">#</th>
                <th className="num">Mês</th>
                <th className="num">Valor investido</th>
                <th className="num">vs. média</th>
                <th className="num">Fundos comprando</th>
                <th className="num">% dos fundos ativos</th>
                <th className="num">vs. média</th>
                <th className="num">Score de coordenação</th>
              </tr>
            </thead>
            <tbody>
              {top5.map((m, i) => (
                <tr key={m.ref_date}>
                  <td className="num" style={{ color: i < 3 ? "var(--amber)" : "var(--text3)" }}>{i + 1}º</td>
                  <td className="num" style={{ color: "var(--text)", fontWeight: 600 }}>{m.ref_date}</td>
                  <td className="num">{fmtBRL(m.total_value_bought)}</td>
                  <td className="num" style={{ color: "var(--green)" }}>{fmtX(m.value_vs_avg)}</td>
                  <td className="num">
                    {m.n_funds_buying} / {m.n_funds_active}
                  </td>
                  <td className="num" style={{ color: "var(--text3)" }}>{m.pct_funds_buying !== null ? `${(m.pct_funds_buying * 100).toFixed(0)}%` : "—"}</td>
                  <td className="num" style={{ color: "var(--gold)" }}>{fmtX(m.funds_vs_avg)}</td>
                  <td className="num" style={{ fontWeight: 700, color: "var(--amber)" }}>{m.coordination_score.toFixed(2)}</td>
                </tr>
              ))}
              {top5.length === 0 && (
                <tr>
                  <td colSpan={8} style={{ color: "var(--text3)" }}>Sem dados suficientes ainda.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
