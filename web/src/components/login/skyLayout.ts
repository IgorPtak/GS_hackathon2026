/**
 * A deterministic ASCII night sky: a sparse star field plus a large four-point star (the Beacon
 * mark) drawn with characters. Pure so the layout is stable between renders.
 */
export interface SkyCell {
  readonly char: string;
  /** 0 = background dust, 1 = star, 2 = part of the big mark. */
  readonly level: 0 | 1 | 2;
  /** Twinkle delay in seconds; null for cells that do not twinkle. */
  readonly delay: number | null;
}

const DUST = [".", "·", "˙"];
const STARS = ["+", "*", "✦", "⋆"];

/** Small seeded PRNG (mulberry32) so the sky is the same on every load. */
function random(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let value = Math.imul(state ^ (state >>> 15), 1 | state);
    value ^= value + Math.imul(value ^ (value >>> 7), 61 | value);
    return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
  };
}

/** Distance in a 4-point-star metric: small near the diagonals' axes, large elsewhere. */
function starShape(dx: number, dy: number): number {
  const x = Math.abs(dx);
  const y = Math.abs(dy) * 2.1; // characters are about twice as tall as they are wide
  return Math.sqrt(x) + Math.sqrt(y);
}

function markChar(value: number, edge: number): string | null {
  if (value > edge) return null;
  if (value > edge - 0.55) return "·";
  if (value > edge - 1.4) return "+";
  if (value > edge - 2.4) return "*";
  return "#";
}

export interface SkyOptions {
  /** Centre of the big mark as a fraction of the width and height. */
  readonly x?: number;
  readonly y?: number;
  /** Size of the big mark relative to the login sky. */
  readonly scale?: number;
  /** Fraction of cells that hold dust. */
  readonly dust?: number;
}

export function buildSky(
  cols: number,
  rows: number,
  seed = 7,
  options: SkyOptions = {},
): SkyCell[][] {
  const { x = 0.72, y = 0.48, scale = 1, dust = 0.07 } = options;
  const next = random(seed);
  const centerX = Math.round(cols * x);
  const centerY = Math.round(rows * y);
  const edge = Math.sqrt(Math.min(cols, rows * 2.1) * 0.42) * 1.5 * scale;
  const grid: SkyCell[][] = [];
  for (let row = 0; row < rows; row += 1) {
    const line: SkyCell[] = [];
    for (let col = 0; col < cols; col += 1) {
      const mark = markChar(starShape(col - centerX, row - centerY), edge);
      const roll = next();
      if (mark) {
        line.push({ char: mark, level: 2, delay: roll < 0.18 ? roll * 30 : null });
      } else if (roll < 0.012) {
        line.push({
          char: STARS[Math.floor(next() * STARS.length)] ?? "+",
          level: 1,
          delay: next() * 6,
        });
      } else if (roll < dust) {
        line.push({ char: DUST[Math.floor(next() * DUST.length)] ?? ".", level: 0, delay: null });
      } else {
        line.push({ char: " ", level: 0, delay: null });
      }
    }
    grid.push(line);
  }
  return grid;
}
