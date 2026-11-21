import type { Delivery } from "../../api/types";
import { StatusChip, type ChipTone } from "../ui/StatusChip";

const STATUS: Record<Delivery["status"], { label: string; tone: ChipTone }> = {
  pending: { label: "Pending", tone: "neutral" },
  sent: { label: "Sent", tone: "info" },
  delivered: { label: "Delivered", tone: "success" },
  failed: { label: "Failed, retrying", tone: "warning" },
  dead_lettered: { label: "Kept for retry", tone: "critical" },
  suppressed: { label: "Skipped", tone: "neutral" },
};

/** Deliveries of one alert as a table: channel, recipient, status and attempt. */
export function DeliveryList({ deliveries }: { deliveries: readonly Delivery[] }) {
  if (deliveries.length === 0) return <p className="text-meta text-ink-2">No deliveries yet.</p>;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-meta">
        <thead className="text-ink-2">
          <tr>
            <th className="py-1 pr-3 font-medium">Channel</th>
            <th className="py-1 pr-3 font-medium">To</th>
            <th className="py-1 pr-3 font-medium">Status</th>
            <th className="num py-1 font-medium">Attempt</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-hairline">
          {deliveries.map((delivery) => (
            <tr key={delivery.id} className="align-top">
              <td className="py-2 pr-3 font-medium text-ink">{delivery.channel_type}</td>
              <td className="py-2 pr-3 text-ink-2">
                {delivery.recipient_id ?? delivery.channel_id}
                {delivery.is_fallback ? " (fallback)" : ""}
              </td>
              <td className="py-2 pr-3">
                <StatusChip tone={STATUS[delivery.status].tone}>
                  {STATUS[delivery.status].label}
                </StatusChip>
                {delivery.last_error ? (
                  <p className="mt-1 break-words text-critical-ink">{delivery.last_error}</p>
                ) : null}
              </td>
              <td className="num py-2 text-ink-2">{delivery.attempt}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
