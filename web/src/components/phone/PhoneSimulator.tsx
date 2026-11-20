import { useState } from "react";

import { useEventStream } from "../../hooks/useEventStream";
import { ConnectionIndicator } from "../alerts/ConnectionIndicator";
import { PhoneMessageBubble } from "./PhoneMessageBubble";
import { PhoneReplyBox } from "./PhoneReplyBox";
import { usePhoneMessages } from "./usePhoneMessages";
import { useRecipients } from "./useRecipients";

/** Mock phone per recipient: SMS and calls, live from phone.message, with a reply box. */
export function PhoneSimulator({ teamId }: { teamId: string | null }) {
  const { recipients, isLoading: isLoadingRecipients, error: recipientsError } = useRecipients();
  const [picked, setPicked] = useState<string | null>(null);
  const recipientId = picked ?? recipients[0]?.id ?? null;
  const phone = usePhoneMessages(recipientId);
  const { apply, reload } = phone;
  // The stream needs a team; phone.message is broadcast so any team receives every phone.
  const streamStatus = useEventStream(teamId, {
    "phone.message": (event) => {
      apply(event.message);
    },
    onReconnect: reload,
  });

  const newest = phone.messages.length > 0 ? phone.messages[phone.messages.length - 1] : undefined;
  return (
    <section aria-labelledby="phone-title" className="mx-auto max-w-md">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h2 id="phone-title" className="text-xl font-semibold">
          Phone
        </h2>
        <ConnectionIndicator status={streamStatus} />
      </div>
      {teamId === null ? (
        <p className="mb-2 text-xs text-slate-500">Select a team to get live messages.</p>
      ) : null}
      {recipientsError ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          Cannot load recipients ({recipientsError}).
        </p>
      ) : null}
      {isLoadingRecipients ? <p className="text-sm text-slate-500">Loading recipients...</p> : null}
      {recipientId !== null ? (
        <>
          <label className="mb-2 flex items-center gap-2 text-sm">
            <span className="font-medium text-slate-700">Recipient</span>
            <select
              value={recipientId}
              onChange={(event) => {
                setPicked(event.target.value);
              }}
              className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-2 py-1"
            >
              {recipients.map((recipient) => (
                <option key={recipient.id} value={recipient.id}>
                  {recipient.display_name}
                </option>
              ))}
            </select>
          </label>
          <div className="overflow-hidden rounded-3xl border-4 border-slate-800 bg-slate-100">
            <div className="h-96 overflow-y-auto p-3">
              {phone.isLoading ? (
                <p className="text-sm text-slate-500">Loading messages...</p>
              ) : null}
              {phone.error ? (
                <p role="alert" className="mb-2 rounded bg-red-50 px-3 py-2 text-sm text-red-800">
                  Cannot load messages ({phone.error}).{" "}
                  <button type="button" className="underline" onClick={phone.reload}>
                    Retry
                  </button>
                </p>
              ) : null}
              {!phone.isLoading && !phone.error && phone.messages.length === 0 ? (
                <p className="text-sm text-slate-500">No messages for this recipient yet</p>
              ) : null}
              <ul className="space-y-2">
                {phone.messages.map((message) => (
                  <PhoneMessageBubble key={message.id} message={message} />
                ))}
              </ul>
            </div>
            <PhoneReplyBox
              key={recipientId}
              recipientId={recipientId}
              approvalCode={newest?.approval_code ?? null}
            />
          </div>
        </>
      ) : null}
      {!isLoadingRecipients && !recipientsError && recipientId === null ? (
        <p className="text-sm text-slate-500">No recipients configured</p>
      ) : null}
    </section>
  );
}
