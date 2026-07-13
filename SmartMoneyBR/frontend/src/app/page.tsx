import Link from "next/link";

export default function Home() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">SmartMoneyBR</h1>
        <p style={{ color: "var(--text2)" }} className="mt-1 text-sm">
          Rastreamento do posicionamento de fundos de investimento em ações brasileiras — dados oficiais CVM (CDA).
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Link href="/fundos" className="smb-card p-5 block hover:opacity-90">
          <div className="text-sm font-semibold" style={{ color: "var(--gold)" }}>Fundos</div>
          <div className="mt-1 text-sm" style={{ color: "var(--text2)" }}>
            Busque um fundo e veja carteira atual, histórico e movimentos mês a mês.
          </div>
        </Link>
        <Link href="/ativos" className="smb-card p-5 block hover:opacity-90">
          <div className="text-sm font-semibold" style={{ color: "var(--gold)" }}>Ativos</div>
          <div className="mt-1 text-sm" style={{ color: "var(--text2)" }}>
            Veja quem compra/vende um ticker, ranking de compradores/vendedores e timeline.
          </div>
        </Link>
        <Link href="/rankings" className="smb-card p-5 block hover:opacity-90">
          <div className="text-sm font-semibold" style={{ color: "var(--gold)" }}>Rankings</div>
          <div className="mt-1 text-sm" style={{ color: "var(--text2)" }}>
            Mais comprado, mais vendido, novas posições, zeragens e consenso institucional.
          </div>
        </Link>
      </div>
    </div>
  );
}
