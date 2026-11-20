import { EmptyState } from "../ui/EmptyState";
import { Skeleton } from "../ui/Skeleton";
import { PersonCard } from "./PersonCard";
import { useConfigLists } from "./useConfigLists";

/** The picked team's people, each with their channel preferences. */
export function RecipientsSection({ team }: { readonly team: string }) {
  const { config, error, isLoading, reload } = useConfigLists();
  const recipients = (config?.recipients ?? []).filter((r) => (r.teams ?? []).includes(team));
  const channelIds = (config?.channels ?? []).map((c) => c.id);
  const sourceIds = (config?.sources ?? []).map((s) => s.id);

  if (isLoading) return <Skeleton className="h-40 w-full" />;
  if (error) {
    return (
      <p role="alert" className="rounded-tile bg-critical/12 px-4 py-3 text-critical-ink">
        Cannot load people ({error}). Check that the API is running, then reload.
      </p>
    );
  }
  if (recipients.length === 0) {
    return (
      <EmptyState icon="people">No one is on this team yet. Add a person in the config.</EmptyState>
    );
  }
  return (
    <ul className="space-y-4">
      {recipients.map((recipient) => (
        <PersonCard
          key={recipient.id}
          recipient={recipient}
          team={team}
          channelIds={channelIds}
          sourceIds={sourceIds}
          onSaved={reload}
        />
      ))}
    </ul>
  );
}
