import { useEffect, useMemo, useRef, useState } from "react";

import { buildSky } from "./skyLayout";

const CELL_WIDTH = 9;
const CELL_HEIGHT = 18;

/** Full-bleed ASCII night sky with gently twinkling stars, sized to its container. */
export function AsciiSky() {
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

  const sky = useMemo(() => buildSky(size.cols, size.rows), [size]);

  return (
    <div
      ref={box}
      aria-hidden="true"
      className="absolute inset-0 -z-10 overflow-hidden select-none"
    >
      <pre className="ascii-sky m-0 font-mono text-[15px] leading-[18px] tracking-[0.06em]">
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
      <div className="ascii-glow absolute inset-0" />
    </div>
  );
}
