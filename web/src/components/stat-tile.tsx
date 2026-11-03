/** A figure in a `dl`: label, value, and an optional note, under a green rule. */
export function StatTile({
  label,
  value,
  note,
}: {
  label: string;
  value: React.ReactNode;
  note?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-t-[3px] border-border border-t-chart-1 bg-card px-4 py-3">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-[28px] leading-tight font-bold tabular-nums">{value}</dd>
      {note && <dd className="text-xs text-muted-foreground tabular-nums">{note}</dd>}
    </div>
  );
}
