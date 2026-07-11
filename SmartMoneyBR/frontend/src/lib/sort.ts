import { useState } from "react";

export type SortDir = "asc" | "desc";

export function sortRows<T>(
  rows: T[],
  getValue: (row: T) => string | number | null | undefined,
  dir: SortDir
): T[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const av = getValue(a);
    const bv = getValue(b);
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    if (typeof av === "string" || typeof bv === "string") {
      return sign * String(av).localeCompare(String(bv), "pt-BR", { numeric: true });
    }
    return sign * (av - bv);
  });
}

// Sort state for click-to-sort table headers. Starts at sortKey=null so
// tables render in their original (API-provided, already meaningful) order
// until the user actively clicks a column.
export function useSort<K extends string>(initialKey: K | null = null, initialDir: SortDir = "asc") {
  const [sortKey, setSortKey] = useState<K | null>(initialKey);
  const [sortDir, setSortDir] = useState<SortDir>(initialDir);

  function toggle(key: K) {
    if (key === sortKey) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  return { sortKey, sortDir, toggle };
}
