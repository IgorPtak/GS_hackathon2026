import { cx } from "../../lib/cx";
import { teamColor } from "../../lib/teams";

const SIZES = {
  sm: "size-7 text-caption",
  md: "size-9 text-body",
  lg: "size-11 text-row",
  xl: "size-16 text-card-title",
} as const;

interface AvatarProps {
  /** The text the monogram comes from, e.g. a team or person name. */
  readonly name: string;
  /** Team id picks the team colour; omit for a neutral avatar. */
  readonly team?: string | null;
  readonly size?: keyof typeof SIZES;
  readonly className?: string;
}

/** Round monogram: team colour at 16% fill, initial in full colour. Decorative (aria-hidden). */
export function Avatar({ name, team, size = "md", className }: AvatarProps) {
  const initial = name
    .replace(/^Team\s+/i, "")
    .trim()
    .charAt(0)
    .toUpperCase();
  return (
    <span
      aria-hidden="true"
      style={{ color: teamColor(team) }}
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full bg-[color-mix(in_srgb,currentColor_16%,transparent)] font-semibold",
        SIZES[size],
        className,
      )}
    >
      {initial}
    </span>
  );
}
