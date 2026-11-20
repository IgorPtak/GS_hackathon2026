import type { Delivery } from "../../api/types";

const STATUS_CLASSES: Record<Delivery["status"], string> = {
  pending: "bg-slate-100 text-slate-700",
  sent: "bg-blue-100 text-blue-800",
  delivered: "bg-green-100 text-green-800",
  failed: "bg-amber-100 text-amber-800",
  dead_lettered: "bg-red-100 text-red-800",
  suppressed: "bg-slate-100 text-slate-500",
};

/** Deliveries of one alert with channel, status and attempt number. */
export function DeliveryList({ deliveries }: { deliveries: readonly Delivery[] }) {
  if (deliveries.length === 0) return <p className="text-sm text-slate-500">No deliveries yet</p>;
  return (
    <ul className="divide-y divide-slate-100">
      {deliveries.map((delivery) => (
        <li key={delivery.id} className="py-2 text-sm">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="font-medium">{delivery.channel_type}</span>
            <span className="text-slate-600">{delivery.recipient_id ?? delivery.channel_id}</span>
            <span className={`rounded px-1.5 text-xs leading-5 ${STATUS_CLASSES[delivery.status]}`}>
              {delivery.status.replaceAll("_", " ")}
            </span>
            <span className="text-xs text-slate-500">attempt {delivery.attempt}</span>
            {delivery.is_fallback ? <span className="text-xs text-slate-500">fallback</span> : null}
          </div>
          {delivery.last_error ? (
            <p className="mt-1 text-xs break-words text-red-700">{delivery.last_error}</p>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
