import type { SchemaProfileRecord } from "../../api/types";

interface SchemaProfileListProps {
  readonly profiles: readonly SchemaProfileRecord[];
  readonly isLoading: boolean;
  readonly error: string | null;
}

/** Read-only list of saved schema profiles. */
export function SchemaProfileList({ profiles, isLoading, error }: SchemaProfileListProps) {
  return (
    <div>
      <h3 className="mb-2 text-lg font-semibold">Saved schema profiles</h3>
      {isLoading ? <p className="text-sm text-slate-500">Loading schema profiles...</p> : null}
      {error ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          Cannot load schema profiles ({error}).
        </p>
      ) : null}
      {!isLoading && !error && profiles.length === 0 ? (
        <p className="text-sm text-slate-500">No schema profiles yet</p>
      ) : null}
      <ul className="space-y-1">
        {profiles.map((p) => (
          <li key={p.id} className="rounded border border-slate-200 bg-white px-3 py-2 text-sm">
            <span className="font-medium break-all">{p.id}</span>
            <span className="text-xs text-slate-500">
              {" "}
              · v{p.version} · priority {p.schema_profile.priority} ·{" "}
              {new Date(p.updated_at).toLocaleString()}
            </span>
            {p.schema_profile.description ? (
              <span className="block text-xs break-words text-slate-600">
                {p.schema_profile.description}
              </span>
            ) : null}
          </li>
        ))}
      </ul>
    </div>
  );
}
