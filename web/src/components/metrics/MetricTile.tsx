interface MetricTileProps {
  readonly label: string;
  readonly value: string;
  readonly unit?: string;
}

/** One number with its unit; the value is already formatted ("—" when missing). */
export function MetricTile({ label, value, unit }: MetricTileProps) {
  return (
    <div className="rounded border border-slate-200 bg-white p-4">
      <dt className="text-sm text-slate-600">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">
        {value}
        {unit && value !== "—" ? (
          <span className="ml-1 text-sm font-normal text-slate-500">{unit}</span>
        ) : null}
      </dd>
    </div>
  );
}
