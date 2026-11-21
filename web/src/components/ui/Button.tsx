import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cx } from "../../lib/cx";
import { Icon, type IconName } from "./icons";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "raised" | "ghost" | "danger";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  readonly variant?: ButtonVariant;
  /** md is 36 px high, lg is 44 px. */
  readonly size?: "md" | "lg";
  readonly isLoading?: boolean;
  readonly icon?: IconName;
  readonly children: ReactNode;
}

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-ink text-window shadow-tile hover:bg-ink/85",
  secondary: "bg-fill text-ink hover:bg-hairline",
  raised: "border border-hairline bg-card text-ink shadow-tile hover:bg-fill",
  ghost: "bg-transparent text-ink-2 hover:bg-fill hover:text-ink",
  danger: "bg-critical/12 text-critical-ink hover:bg-critical/20",
};

/** Pill button. One primary per toolbar; loading disables it and shows a spinner. */
export function Button({
  variant = "secondary",
  size = "md",
  isLoading = false,
  icon,
  children,
  className,
  disabled,
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      disabled={disabled === true || isLoading}
      aria-busy={isLoading || undefined}
      className={cx(
        "inline-flex shrink-0 items-center justify-center gap-2 rounded-full px-4 text-body font-medium whitespace-nowrap transition-[background-color,color,opacity,scale,box-shadow] select-none active:scale-[0.97] disabled:cursor-not-allowed disabled:opacity-45 disabled:active:scale-100",
        size === "md" ? "h-9" : "h-11 px-5",
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {isLoading ? <Spinner size={16} /> : icon ? <Icon name={icon} size={18} /> : null}
      {children}
    </button>
  );
}
