import type { Metadata } from "next";
import Link from "next/link";
import AlertsNavLink from "@/components/AlertsNavLink";
import GlobalSearch from "@/components/GlobalSearch";
import "./globals.css";

export const metadata: Metadata = {
  title: "SmartMoneyBR",
  description: "Monitoramento de posicionamento institucional no mercado brasileiro",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className="h-full antialiased">
      <body className="min-h-full flex flex-col">
        <header className="border-b" style={{ borderColor: "var(--border)", background: "var(--bg2)" }}>
          <div className="max-w-6xl mx-auto px-6 py-3 flex items-center gap-6">
            <Link href="/" className="font-bold tracking-tight text-xl" style={{ color: "var(--cyan)" }}>
              SmartMoney<span style={{ color: "var(--text)" }}>BR</span>
            </Link>
            <nav className="flex items-center gap-4 text-sm" style={{ color: "var(--text2)" }}>
              <Link href="/fundos">Fundos</Link>
              <Link href="/ativos">Ativos</Link>
              <Link href="/rankings">Rankings</Link>
              <Link href="/top20" style={{ color: "var(--amber)" }}>Top 20</Link>
              <Link href="/recompras">Recompras</Link>
              <Link href="/insiders">Insiders</Link>
              <AlertsNavLink />
              <Link href="/evolucao">Evolução</Link>
              <GlobalSearch />
            </nav>
          </div>
        </header>
        <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
