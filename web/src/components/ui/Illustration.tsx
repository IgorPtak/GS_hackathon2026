import type { CSSProperties } from "react";

import { cx } from "../../lib/cx";
import { useIsDarkTheme } from "../../lib/useIsDarkTheme";
import { SCENES, type Scene } from "./illustrations";

interface IllustrationProps {
  readonly scene: Scene;
  readonly className?: string;
  /** CSS object-position: which part of the painting stays in view when cropped. */
  readonly focus?: string;
  /** Soft fade of the edges into the surrounding surface. */
  readonly fade?: "bottom" | "edges" | "none";
  readonly isEager?: boolean;
}

const FADES: Record<NonNullable<IllustrationProps["fade"]>, string | undefined> = {
  bottom: "linear-gradient(to bottom, #000 55%, transparent)",
  edges: "radial-gradient(ellipse 75% 70% at 50% 45%, #000 55%, transparent 100%)",
  none: undefined,
};

/** A painted scene in the day or night version that matches the current appearance. */
export function Illustration({
  scene,
  className,
  focus = "center",
  fade = "none",
  isEager = false,
}: IllustrationProps) {
  const isDark = useIsDarkTheme();
  const sources = SCENES[scene][isDark ? "night" : "day"];
  const mask = FADES[fade];
  const style: CSSProperties = {
    objectPosition: focus,
    ...(mask ? { maskImage: mask, WebkitMaskImage: mask } : {}),
  };
  return (
    <picture className={cx("block overflow-hidden", className)}>
      <source srcSet={sources.avif} type="image/avif" />
      <img
        src={sources.webp}
        alt=""
        aria-hidden="true"
        loading={isEager ? "eager" : "lazy"}
        decoding="async"
        className="size-full object-cover"
        style={style}
      />
    </picture>
  );
}
