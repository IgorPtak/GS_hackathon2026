import type { ReactNode, SVGProps } from "react";

/** Own icon set: 24 viewBox, 1.75 stroke, round caps and joins, currentColor. No icon library. */
const ICON_PATHS = {
  inbox: (
    <>
      <path d="M4 13l2.2-6.6A2 2 0 0 1 8.1 5h7.8a2 2 0 0 1 1.9 1.4L20 13" />
      <path d="M4 13v5a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-5" />
      <path d="M4 13h4.2l1 2h5.6l1-2H20" />
    </>
  ),
  approval: (
    <>
      <path d="M12 3l2.1 1.5 2.6-.1.9 2.5 2.1 1.6-.8 2.5.8 2.5-2.1 1.6-.9 2.5-2.6-.1L12 21l-2.1-1.5-2.6.1-.9-2.5-2.1-1.6.8-2.5-.8-2.5 2.1-1.6.9-2.5 2.6.1z" />
      <path d="m8.8 12.2 2.2 2.2 4.2-4.4" />
    </>
  ),
  phone: (
    <path d="M5 4h3.5l1.5 4-2 1.3a11 11 0 0 0 5.7 5.7L15 13l4 1.5V18a2 2 0 0 1-2 2A13 13 0 0 1 3 6a2 2 0 0 1 2-2z" />
  ),
  rules: (
    <>
      <path d="M4 7h9M17 7h3M4 17h3M11 17h9" />
      <circle cx="15" cy="7" r="2" />
      <circle cx="9" cy="17" r="2" />
    </>
  ),
  connect: (
    <>
      <path d="M9 3v4M15 3v4" />
      <path d="M6 7h12v3a6 6 0 0 1-12 0z" />
      <path d="M12 16v5" />
    </>
  ),
  runbook: (
    <>
      <path d="M10 6h10M10 12h10M10 18h10" />
      <path d="m3.5 6 1.3 1.3L7 5M3.5 12l1.3 1.3L7 11M3.5 18l1.3 1.3L7 17" />
    </>
  ),
  people: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3 19c.6-3.2 3-5 6-5s5.4 1.8 6 5" />
      <circle cx="17" cy="9" r="2.4" />
      <path d="M17.5 14c2 .2 3.2 1.7 3.5 4" />
    </>
  ),
  insights: <path d="M5 20v-6M12 20V5M19 20v-9" />,
  send: (
    <>
      <path d="M21 3 10.5 13.5" />
      <path d="M21 3l-6.5 18-4-7.5L3 9.5z" />
    </>
  ),
  bell: (
    <>
      <path d="M6 16v-5a6 6 0 0 1 12 0v5l1.5 2h-15z" />
      <path d="M10 21h4" />
    </>
  ),
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  cross: <path d="M6 6l12 12M18 6 6 18" />,
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </>
  ),
  retry: (
    <>
      <path d="M20 12a8 8 0 1 1-2.6-5.9" />
      <path d="M20 4v4h-4" />
    </>
  ),
  escalate: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12.5 3.5-3.5 3.5 3.5M12 9v7" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" />
    </>
  ),
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />,
  auto: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6" />
      <path d="m20 20-4.2-4.2" />
    </>
  ),
  filter: <path d="M4 6h16M7 12h10M10 18h4" />,
  chevron: <path d="m6 9 6 6 6-6" />,
  plus: <path d="M12 5v14M5 12h14" />,
  more: (
    <>
      <circle cx="5.5" cy="12" r="1.2" fill="currentColor" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
      <circle cx="18.5" cy="12" r="1.2" fill="currentColor" />
    </>
  ),
  alert: (
    <>
      <path d="M12 4 3 19.5h18z" />
      <path d="M12 10v4.5M12 17v.01" />
    </>
  ),
  sparkle: (
    <>
      <path d="M12 3.5 13.9 9l5.6 1.9-5.6 1.9L12 18.5l-1.9-5.7L4.5 10.9 10.1 9z" />
      <path d="M19 3.5v3M17.5 5h3" />
    </>
  ),
  file: (
    <>
      <path d="M7 3.5h6.5L18 8v12.5H7z" />
      <path d="M13 3.5V8.5h5M9.5 13h6M9.5 16.5h6" />
    </>
  ),
  arrowRight: <path d="M5 12h14m-5-5 5 5-5 5" />,
  phoneOff: (
    <>
      <path d="M3.5 14.5c2.2-2.2 5.2-3.5 8.5-3.5s6.3 1.3 8.5 3.5l-2 2.4a1.5 1.5 0 0 1-2 .2l-2.1-1.5a1.5 1.5 0 0 1-.6-1.2v-1a8.5 8.5 0 0 0-3.6 0v1c0 .5-.2.9-.6 1.2L7.5 17a1.5 1.5 0 0 1-2-.2z" />
    </>
  ),
  volume: (
    <>
      <path d="M11 6 6.5 9.5H3.5v5h3L11 18z" />
      <path d="M15.2 9.2a4.2 4.2 0 0 1 0 5.6M18 6.8a7.8 7.8 0 0 1 0 10.4" />
    </>
  ),
  volumeOff: (
    <>
      <path d="M11 6 6.5 9.5H3.5v5h3L11 18z" />
      <path d="m15.5 9.5 5 5M20.5 9.5l-5 5" />
    </>
  ),
  backspace: (
    <>
      <path d="M9 6h10a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H9l-5.5-6z" />
      <path d="m12.5 9.5 4 5M16.5 9.5l-4 5" />
    </>
  ),
  external: (
    <>
      <path d="M14 5h5v5M19 5l-8.5 8.5" />
      <path d="M18 13v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h5" />
    </>
  ),
  sparkles: (
    <>
      <path d="M12 3l1.6 4.8L18.4 9.4l-4.8 1.6L12 15.8l-1.6-4.8-4.8-1.6 4.8-1.6z" />
      <path d="M19 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z" />
    </>
  ),
  layers: (
    <>
      <path d="m12 4 8 4.5-8 4.5-8-4.5z" />
      <path d="m4 13 8 4.5 8-4.5" />
      <path d="m4 17.5 8 4.5 8-4.5" />
    </>
  ),
  signalOff: (
    <>
      <path d="M4 4l16 16" />
      <path d="M9.5 14.5a3.5 3.5 0 0 1 4.6-.3" />
      <path d="M6.3 11.3a8 8 0 0 1 5.7-2.3c2.1 0 4 .8 5.5 2.1" />
      <circle cx="12" cy="18" r="1" fill="currentColor" />
    </>
  ),
} satisfies Record<string, ReactNode>;

export type IconName = keyof typeof ICON_PATHS;

interface IconProps extends Omit<SVGProps<SVGSVGElement>, "name"> {
  readonly name: IconName;
  readonly size?: number;
}

/** Decorative by default; pass `aria-label` (and `role="img"`) when the icon stands alone. */
export function Icon({ name, size = 20, ...rest }: IconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={rest["aria-label"] ? undefined : true}
      focusable="false"
      {...rest}
    >
      {ICON_PATHS[name]}
    </svg>
  );
}
