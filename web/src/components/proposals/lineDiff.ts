export type DiffKind = "same" | "add" | "remove";

export interface DiffLine {
  readonly kind: DiffKind;
  readonly text: string;
}

/** Line diff by longest common subsequence. */
export function diffLines(before: readonly string[], after: readonly string[]): DiffLine[] {
  const n = before.length;
  const m = after.length;
  const table: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  const at = (i: number, j: number): number => table[i]?.[j] ?? 0;
  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      const row = table[i];
      if (!row) continue;
      row[j] = before[i] === after[j] ? at(i + 1, j + 1) + 1 : Math.max(at(i + 1, j), at(i, j + 1));
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    const a = before[i] ?? "";
    const b = after[j] ?? "";
    if (a === b) {
      out.push({ kind: "same", text: a });
      i += 1;
      j += 1;
    } else if (at(i + 1, j) >= at(i, j + 1)) {
      out.push({ kind: "remove", text: a });
      i += 1;
    } else {
      out.push({ kind: "add", text: b });
      j += 1;
    }
  }
  for (; i < n; i += 1) out.push({ kind: "remove", text: before[i] ?? "" });
  for (; j < m; j += 1) out.push({ kind: "add", text: after[j] ?? "" });
  return out;
}
