import { useEffect, useMemo, useRef, useState } from "react";

import { cx } from "../../lib/cx";
import { buildSky, type SkyOptions } from "./skyLayout";

const CELL_WIDTH = 9;
const CELL_HEIGHT = 18;

const PANEL_SKY: SkyOptions = { x: 0.8, y: 0.7, scale: 0.55, dust: 0.03 };

/**
 * Full-bleed ASCII night sky with gently twinkling stars, sized to its container. The `panel`
 * tone is the faint backdrop behind every page; `login` is the bright sign-in sky.
 */
export function AsciiSky({ tone = "login" }: { readonly tone?: "login" | "panel" }) {
  const box = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ cols: 160, rows: 50 });

  useEffect(() => {
    const element = box.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => {
      if (!entry) return;
      const { width, height } = entry.contentRect;
      setSize({
        cols: Math.max(40, Math.ceil(width / CELL_WIDTH)),
        rows: Math.max(20, Math.ceil(height / CELL_HEIGHT)),
      });
    });
    observer.observe(element);
    return () => {
      observer.disconnect();
    };
  }, []);

  const sky = useMemo(
    () => buildSky(size.cols, size.rows, 7, tone === "panel" ? PANEL_SKY : {}),
    [size, tone],
  );

  return (
    <div
      ref={box}
      aria-hidden="true"
      className="absolute inset-0 -z-10 overflow-hidden select-none"
    >
      <pre
        className={cx(
          "m-0 font-mono text-[15px] leading-[18px] tracking-[0.06em]",
          tone === "panel" ? "ascii-sky ascii-sky-panel" : "ascii-sky",
        )}
      >
        {sky.map((line, row) => (
          <div key={row}>
            {line.map((cell, col) =>
              cell.char === " " ? (
                " "
              ) : (
                <span
                  key={col}
                  data-level={cell.level}
                  className={cell.delay === null ? undefined : "ascii-twinkle"}
                  style={
                    cell.delay === null
                      ? undefined
                      : { animationDelay: `${cell.delay.toFixed(2)}s` }
                  }
                >
                  {cell.char}
                </span>
              ),
            )}
          </div>
        ))}
      </pre>
      {tone === "login" ? <div className="ascii-glow absolute inset-0" /> : null}
    </div>
  );
}
