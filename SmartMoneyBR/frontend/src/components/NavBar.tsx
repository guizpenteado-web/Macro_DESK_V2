"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import AlertsNavLink from "@/components/AlertsNavLink";
import GlobalSearch from "@/components/GlobalSearch";

const LINKS = [
  { href: "/fundos", label: "Fundos" },
  { href: "/ativos", label: "Ativos" },
  { href: "/rankings", label: "Rankings" },
  { href: "/top20", label: "Top 20", accent: "var(--amber)" },
  { href: "/recompras", label: "Recompras" },
  { href: "/insiders", label: "Insiders" },
];

export default function NavBar() {
  const pathname = usePathname();

  function isActive(href: string) {
    return pathname === href || pathname.startsWith(href + "/");
  }

  function renderLink(href: string, label: string, accent?: string) {
    const active = isActive(href);
    return (
      <Link
        key={href}
        href={href}
        className={`smb-nav-btn text-sm${active ? " active" : ""}`}
        style={!active && accent ? { color: accent, borderColor: accent } : undefined}
      >
        {label}
      </Link>
    );
  }

  return (
    <nav className="flex items-center gap-2 text-sm flex-wrap">
      {LINKS.map((l) => renderLink(l.href, l.label, l.accent))}
      <AlertsNavLink active={isActive("/alertas")} />
      {/* Agrupados pra quebrar de linha JUNTOS (flex-wrap quebra por item —
          sem isso Favoritos ficava numa linha e Carteira+busca em outra,
          mesmo vindo logo em seguida no DOM). Os 3 sempre ficam colados,
          e se nao couber na linha, o bloco inteiro desce junto. */}
      <div className="flex items-center gap-2">
        {renderLink("/favoritos", "Favoritos")}
        {renderLink("/carteira", "Carteira")}
        <GlobalSearch />
      </div>
    </nav>
  );
}
