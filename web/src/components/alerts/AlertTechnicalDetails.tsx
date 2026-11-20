import type { AlertDetail } from "../../api/types";
import { Icon } from "../ui/icons";
import { RunbookSource } from "../runbooks/RunbookSource";
import { AlertFields } from "./AlertFields";
import { AuditTimeline } from "./AuditTimeline";
import { DeliveryList } from "./DeliveryList";

function Block({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-4">
      <h4 className="mb-2 text-meta font-semibold text-ink">{title}</h4>
      {children}
    </section>
  );
}

/** Raw event, fingerprint, deliveries and audit trail: everything technical, closed by default. */
export function AlertTechnicalDetails({ detail }: { detail: AlertDetail }) {
  const { alert } = detail;
  return (
    <details className="group rounded-tile border border-hairline px-4 py-3">
      <summary className="flex list-none items-center justify-between text-body font-medium [&::-webkit-details-marker]:hidden">
        Details
        <span className="text-ink-2 transition-transform group-open:rotate-180">
          <Icon name="chevron" size={18} />
        </span>
      </summary>
      <Block title="Alert fields">
        <AlertFields alert={alert} />
      </Block>
      <Block title="Deliveries">
        <DeliveryList deliveries={detail.deliveries} />
      </Block>
      <Block title="Audit trail">
        <AuditTimeline entries={detail.audit_entries} />
      </Block>
      {detail.rendered_runbook ? (
        <Block title="Runbook source">
          <RunbookSource
            source={detail.rendered_runbook.source}
            format={detail.rendered_runbook.format}
          />
        </Block>
      ) : null}
      <Block title="Last event (raw JSON)">
        <pre className="max-h-80 overflow-auto rounded-input bg-fill p-3 font-mono text-caption text-ink">
          {JSON.stringify(alert.last_event, null, 2)}
        </pre>
      </Block>
    </details>
  );
}
