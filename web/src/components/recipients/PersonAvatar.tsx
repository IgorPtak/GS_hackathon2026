import { teamColor } from "../../lib/teams";

/** Round avatar with up to two initials of a person, tinted with their team colour. */
export function PersonAvatar({ name, team }: { readonly name: string; readonly team: string }) {
  const initials = name
    .split(/\s+/)
    .filter((part) => part !== "")
    .slice(0, 2)
    .map((part) => part.charAt(0).toUpperCase())
    .join("");
  return (
    <span
      aria-hidden="true"
      style={{ color: teamColor(team) }}
      className="inline-flex size-11 shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,currentColor_16%,transparent)] text-body font-semibold"
    >
      {initials}
    </span>
  );
}
