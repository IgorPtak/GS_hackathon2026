import type { ReactNode } from "react";

import { cx } from "../../lib/cx";
import { PRODUCT_NAME } from "../../lib/brand";
import "./phone.css";

interface PhoneDeviceFrameProps {
  readonly isRinging: boolean;
  readonly isInCall: boolean;
  readonly isFrameless?: boolean;
  readonly isFullScreenDesktop?: boolean;
  readonly children: ReactNode;
}

function StatusIcons() {
  return (
    <span className="flex items-center gap-1.5 text-white/90" aria-hidden="true">
      <svg width="15" height="10" viewBox="0 0 15 10" fill="currentColor">
        <rect x="0.5" y="6.5" width="2.5" height="3.5" rx="0.8" />
        <rect x="4.2" y="4.5" width="2.5" height="5.5" rx="0.8" />
        <rect x="7.9" y="2.5" width="2.5" height="7.5" rx="0.8" />
        <rect x="11.6" y="0.5" width="2.5" height="9.5" rx="0.8" />
      </svg>
      <svg
        width="14"
        height="10"
        viewBox="0 0 14 10"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      >
        <path d="M1.5 3.3a8.5 8.5 0 0 1 11 0" />
        <path d="M4 5.8a4.8 4.8 0 0 1 6 0" />
        <circle cx="7" cy="8.4" r="1" fill="currentColor" stroke="none" />
      </svg>
      <svg width="22" height="11" viewBox="0 0 22 11" fill="none">
        <rect
          x="0.75"
          y="1"
          width="18"
          height="9"
          rx="2.6"
          stroke="currentColor"
          strokeWidth="1.1"
          strokeOpacity="0.85"
        />
        <rect x="2.2" y="2.5" width="13.5" height="6" rx="1.4" fill="currentColor" />
        <path
          d="M20.2 3.8v3.4"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinecap="round"
          strokeOpacity="0.6"
        />
      </svg>
    </span>
  );
}

/** Pure CSS iPhone-like device frame with dynamic island, or frameless edge-to-edge on mobile. */
export function PhoneDeviceFrame({
  isRinging,
  isInCall,
  isFrameless = false,
  isFullScreenDesktop = false,
  children,
}: PhoneDeviceFrameProps) {
  if (isFrameless) {
    return (
      <div
        className={cx(
          "phone-screen-frameless flex flex-col text-white",
          isRinging && "phone-ringing",
        )}
      >
        <div className="relative flex min-h-0 flex-1 flex-col">{children}</div>
      </div>
    );
  }

  return (
    <div
      className={cx(
        "phone-chassis shrink-0 select-none",
        isFullScreenDesktop
          ? "h-[690px] max-h-[calc(100dvh-40px)] w-[340px]"
          : "h-[610px] w-[312px]",
        isRinging && "phone-ringing",
      )}
    >
      {/* Hardware side buttons */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-[92px] -left-[3px] h-6 w-[3px] rounded-l-sm bg-[#2c2e34]"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-[134px] -left-[3px] h-11 w-[3px] rounded-l-sm bg-[#2c2e34]"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-[188px] -left-[3px] h-11 w-[3px] rounded-l-sm bg-[#2c2e34]"
      />
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-[150px] -right-[3px] h-16 w-[3px] rounded-r-sm bg-[#2c2e34]"
      />

      <div className="phone-screen-glass flex h-full w-full flex-col text-white">
        <div className="relative z-20 flex h-11 shrink-0 items-center justify-between px-6 pt-2">
          <span className="text-[12px] font-semibold tracking-tight text-white/95">
            {PRODUCT_NAME}
          </span>
          <div
            aria-hidden="true"
            className={cx(
              "absolute top-2.5 left-1/2 flex h-[24px] -translate-x-1/2 items-center justify-between rounded-full bg-black px-2.5 transition-all",
              isInCall ? "w-[114px]" : "w-[88px]",
            )}
          >
            {isInCall ? (
              <span className="size-2 rounded-full bg-[#34c759]" />
            ) : (
              <span className="size-1.5 rounded-full bg-white/10" />
            )}
            <span className="size-2.5 rounded-full bg-[#131724] ring-1 ring-white/10" />
          </div>
          <StatusIcons />
        </div>

        <div className="relative flex min-h-0 flex-1 flex-col">{children}</div>

        <div className="relative z-20 flex shrink-0 justify-center pt-1 pb-2" aria-hidden="true">
          <span className="h-1 w-28 rounded-full bg-white/75" />
        </div>
      </div>
    </div>
  );
}
