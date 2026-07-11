const LABELS: Record<string, string> = {
  NEW: "NOVA",
  INCREASED: "AUMENTOU",
  DECREASED: "REDUZIU",
  CLOSED: "ZEROU",
  UNCHANGED: "MANTEVE",
};

export default function MovementBadge({ classification }: { classification: string }) {
  const cls = `smb-badge smb-badge-${classification.toLowerCase()}`;
  return <span className={cls}>{LABELS[classification] ?? classification}</span>;
}
