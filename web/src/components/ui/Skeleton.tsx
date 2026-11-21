import { cx } from "../../lib/cx";

/** Placeholder block for loading lists; size it with className. */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div aria-hidden="true" className={cx("animate-pulse rounded-input bg-fill", className)} />
  );
}
