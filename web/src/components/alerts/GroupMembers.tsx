import type { GroupMember } from "../../api/types";
import { formatRelativeTime } from "./alertFormat";

/** Drill-down rows of a group summary alert. */
export function GroupMembers({ members, now }: { members: readonly GroupMember[]; now: number }) {
  if (members.length === 0) {
    return <p className="px-3 py-2 text-xs text-slate-500">No members in this group yet</p>;
  }
  return (
    <ul className="divide-y divide-slate-100 bg-slate-50">
      {members.map((member) => (
        <li
          key={member.fingerprint}
          className="flex flex-wrap items-baseline gap-x-3 gap-y-1 py-2 pr-3 pl-10 text-xs"
        >
          <span className="min-w-0 flex-1 basis-40 font-medium break-words">{member.title}</span>
          {member.count > 1 ? (
            <span className="rounded bg-slate-200 px-1.5 leading-5">×{member.count}</span>
          ) : null}
          <span className="font-mono text-slate-500" title={member.fingerprint}>
            {member.fingerprint.slice(0, 12)}
          </span>
          <span className="text-slate-500">{formatRelativeTime(member.last_seen, now)}</span>
        </li>
      ))}
    </ul>
  );
}
