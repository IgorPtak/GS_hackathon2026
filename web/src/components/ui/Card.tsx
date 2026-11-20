import type { ReactNode } from "react";

import { cx } from "../../lib/cx";

interface CardProps {
  readonly as?: "div" | "section" | "article" | "li";
  /** Default padding is 24 px; pass false for lists that bring their own row padding. */
  readonly isPadded?: boolean;
  readonly className?: string;
  readonly children: ReactNode;
}

/** White rounded surface with a hairline border (radius 20). */
export function Card({ as: Tag = "div", isPadded = true, className, children }: CardProps) {
  return (
    <Tag
      className={cx(
        "rounded-card border border-hairline bg-card shadow-card",
        isPadded && "p-6",
        className,
      )}
    >
      {children}
    </Tag>
  );
}
