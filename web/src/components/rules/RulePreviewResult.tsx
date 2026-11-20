import type { RulePreview } from "../../api/types";

function Stat({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="rounded bg-slate-50 px-3 py-2">
      <div className="text-lg font-semibold">{value}</div>
      <div className="text-xs text-slate-500">{label}</div>
    </div>
  );
}

/** Counters, deliveries table, sample alerts and warnings of one preview run. */
export function RulePreviewResult({ preview }: { readonly preview: RulePreview }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Stat label="Events scanned" value={String(preview.events_scanned)} />
        <Stat label="Events matched" value={String(preview.events_matched)} />
        <Stat label="Alerts created" value={String(preview.alerts_created)} />
        <Stat label="Duration" value={`${String(preview.duration_ms)} ms`} />
      </div>
      {(preview.warnings ?? []).map((warning) => (
        <p key={warning} className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {warning}
        </p>
      ))}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <caption className="mb-1 text-left text-xs font-semibold text-slate-600">
            Deliveries per recipient and channel
          </caption>
          <thead className="text-xs text-slate-500">
            <tr>
              <th className="py-1 pr-3">Recipient</th>
              <th className="py-1 pr-3">Channel</th>
              <th className="py-1">Count</th>
            </tr>
          </thead>
          <tbody>
            {preview.deliveries.map((d) => (
              <tr
                key={`${d.recipient_id ?? ""}/${d.channel_id}`}
                className="border-t border-slate-100"
              >
                <td className="py-1 pr-3">{d.recipient_id ?? "-"}</td>
                <td className="py-1 pr-3">{d.channel_id}</td>
                <td className="py-1">{d.count}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {preview.deliveries.length === 0 ? (
          <p className="text-sm text-slate-500">No deliveries in this window.</p>
        ) : null}
      </div>
      <div>
        <h5 className="mb-1 text-xs font-semibold text-slate-600">Sample alerts</h5>
        {preview.sample_alerts.length === 0 ? (
          <p className="text-sm text-slate-500">No alerts would have been created.</p>
        ) : (
          <ul className="space-y-1">
            {preview.sample_alerts.map((alert) => (
              <li
                key={alert.fingerprint}
                className="flex flex-wrap items-center gap-2 rounded border border-slate-200 px-2 py-1 text-sm"
              >
                <span className="rounded bg-slate-200 px-1.5 text-xs uppercase">
                  {alert.severity}
                </span>
                <span className="min-w-0 break-words">{alert.title}</span>
                <span className="text-xs text-slate-500">×{alert.count}</span>
                {alert.is_group_summary ? (
                  <span className="rounded bg-purple-100 px-1.5 text-xs text-purple-800">
                    Group · {alert.member_count} members
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
