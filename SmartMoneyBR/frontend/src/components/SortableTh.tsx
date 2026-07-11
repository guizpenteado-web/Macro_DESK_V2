import { SortDir } from "@/lib/sort";

export default function SortableTh({
  label,
  active,
  dir,
  onClick,
  align = "left",
}: {
  label: string;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  align?: "left" | "right";
}) {
  return (
    <th className={align === "right" ? "num" : undefined} onClick={onClick} style={{ cursor: "pointer", userSelect: "none" }}>
      {label}
      <span style={{ marginLeft: 4, fontSize: "0.7em", opacity: active ? 1 : 0.25 }}>
        {dir === "asc" ? "▲" : "▼"}
      </span>
    </th>
  );
}
