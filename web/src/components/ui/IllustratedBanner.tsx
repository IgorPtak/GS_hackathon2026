import type { ReactNode } from "react";

import { Illustration } from "./Illustration";
import type { Scene } from "./illustrations";

interface IllustratedBannerProps {
  readonly scene: Scene;
  readonly title: string;
  readonly children?: ReactNode;
  readonly action?: ReactNode;
  /** Which part of the painting to keep in view (CSS object-position). */
  readonly focus?: string;
}

/**
 * A wide painted banner with copy on its calm left side, like the reference "Upgrade with AI"
 * card. The painting fades into the card so the text never fights with it.
 */
export function IllustratedBanner({
  scene,
  title,
  children,
  action,
  focus = "70% 40%",
}: IllustratedBannerProps) {
  return (
    <section className="relative isolate overflow-hidden rounded-card border border-hairline bg-card">
      <Illustration scene={scene} focus={focus} fade="bottom" className="absolute inset-0 -z-10" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-r from-card via-card/70 to-transparent" />
      <div className="flex min-h-[188px] max-w-[460px] flex-col justify-center gap-2 px-8 py-8">
        <h2 className="text-card-title font-semibold tracking-tight">{title}</h2>
        {children ? <div className="text-body text-ink-2">{children}</div> : null}
        {action ? <div className="mt-3">{action}</div> : null}
      </div>
    </section>
  );
}
