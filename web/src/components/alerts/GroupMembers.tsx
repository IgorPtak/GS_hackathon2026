import { useState } from "react";

import type { GroupMember } from "../../api/types";
import { CountBadge } from "../ui/CountBadge";
import { formatRelativeTime } from "./alertFormat";

/** Members folded into a group summary alert. */
export function GroupMembers({ members }: { members: readonly GroupMember[] }) {
  const [now] = useState(() => Date.now());
  if (members.length === 0) {
    return <p className="text-meta text-ink-2">No members in this group yet.</p>;
  }
  return (
    <ul className="divide-y divide-hairline">
      {members.map((member) => (
        <li key={member.fingerprint} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2">
          <span className="min-w-0 flex-1 basis-40 text-body break-words text-ink">
            {member.title}
          </span>
          {member.count > 1 ? <CountBadge count={member.count} /> : null}
          <span className="num text-meta text-ink-2">
            {formatRelativeTime(member.last_seen, now)}
          </span>
        </li>
      ))}
    </ul>
  );
}
