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

const LINKS_AFTER_ALERTS = [
  { href: "/favoritos", label: "Favoritos" },
  { href: "/carteira", label: "Carteira" },
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
      {LINKS_AFTER_ALERTS.map((l) => renderLink(l.href, l.label))}
      <GlobalSearch />
    </nav>
  );
}
