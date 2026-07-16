import type { Metadata } from "next";
import Link from "next/link";
import NavBar from "@/components/NavBar";
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
          {/* Sem max-width aqui de proposito (diferente do <main> abaixo):
              com 9 botoes de nav + busca, um container limitado a 1152px
              (max-w-6xl) forcava quebra de linha mesmo em telas largas. */}
          <div className="w-full px-6 py-3 flex items-center gap-6">
            <Link href="/" className="font-bold tracking-tight text-xl" style={{ color: "var(--gold)" }}>
              SmartMoney<span style={{ color: "var(--text)" }}>BR</span>
            </Link>
            <NavBar />
          </div>
        </header>
        <main className="flex-1 max-w-6xl w-full mx-auto px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
