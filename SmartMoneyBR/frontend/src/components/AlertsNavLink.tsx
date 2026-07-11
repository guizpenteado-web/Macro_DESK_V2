"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function AlertsNavLink() {
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    function load() {
      api
        .getUnreadAlertCount()
        .then((r) => setUnread(r.unread))
        .catch(() => {});
    }
    load();
    const interval = setInterval(load, 60_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <Link href="/alertas" className="flex items-center gap-1.5">
      Alertas
      {unread > 0 && (
        <span
          className="smb-badge"
          style={{ color: "var(--bg)", background: "var(--cyan)", fontSize: "10px", padding: "1px 6px" }}
        >
          {unread > 99 ? "99+" : unread}
        </span>
      )}
    </Link>
  );
}
