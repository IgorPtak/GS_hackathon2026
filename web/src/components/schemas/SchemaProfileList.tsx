import type { SchemaProfileRecord } from "../../api/types";
import { formatRelativeTime } from "../alerts/alertFormat";
import { Skeleton } from "../ui/Skeleton";

interface SchemaProfileListProps {
  readonly profiles: readonly SchemaProfileRecord[];
  readonly isLoading: boolean;
  readonly error: string | null;
}

/** Read-only list of saved schema profiles. */
export function SchemaProfileList({ profiles, isLoading, error }: SchemaProfileListProps) {
  if (isLoading) return <Skeleton className="h-10" />;
  if (error) {
    return (
      <p role="alert" className="text-meta text-critical-ink">
        Beacon could not load saved mappings ({error}).
      </p>
    );
  }
  if (profiles.length === 0) return <p className="text-meta text-ink-2">No saved mappings yet.</p>;
  return (
    <ul className="divide-y divide-hairline">
      {profiles.map((p) => (
        <li key={p.id} className="flex flex-wrap items-baseline gap-x-3 py-2.5">
          <span className="font-mono text-body font-medium break-all">{p.id}</span>
          <span className="text-meta text-ink-2">
            version {p.version} · updated {formatRelativeTime(p.updated_at)}
          </span>
          {p.schema_profile.description ? (
            <span className="basis-full text-meta break-words text-ink-2">
              {p.schema_profile.description}
            </span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
