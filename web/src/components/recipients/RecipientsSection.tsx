import { ChannelPreferencesEditor } from "./ChannelPreferencesEditor";
import { useConfigLists } from "./useConfigLists";

/** Channel preferences of the picked team's recipients. */
export function RecipientsSection({ team }: { readonly team: string }) {
  const { config, error, isLoading, reload } = useConfigLists();
  const recipients = (config?.recipients ?? []).filter((r) => (r.teams ?? []).includes(team));
  const channelIds = (config?.channels ?? []).map((c) => c.id);
  const sourceIds = (config?.sources ?? []).map((s) => s.id);

  return (
    <section aria-labelledby="recipients-title" className="mt-8 space-y-3">
      <h2 id="recipients-title" className="text-xl font-semibold">
        Recipients
      </h2>
      {isLoading ? <p className="text-sm text-slate-500">Loading recipients...</p> : null}
      {error ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          Cannot load recipients ({error}).
        </p>
      ) : null}
      {config && recipients.length === 0 ? (
        <p className="text-sm text-slate-500">No recipients in this team.</p>
      ) : null}
      {recipients.map((recipient) => (
        <ChannelPreferencesEditor
          key={`${recipient.id}:${JSON.stringify(recipient.channel_preferences)}`}
          recipient={recipient}
          team={team}
          channelIds={channelIds}
          sourceIds={sourceIds}
          onSaved={reload}
        />
      ))}
    </section>
  );
}
