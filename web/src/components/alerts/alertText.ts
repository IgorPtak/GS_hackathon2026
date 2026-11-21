/**
 * Alert titles come from rule templates written for engineers ("Rejected EUR 25000000 —
 * LIMIT_BREACH"). For the inbox we split off the reason code and make numbers readable.
 */
export interface AlertText {
  readonly title: string;
  readonly reason: string | null;
}

const CODE = /\b[A-Z][A-Z0-9]*(?:_[A-Za-z0-9]+)+\b/g;
// Standalone integers only: ids such as wf-1795215992 or T-1234567 keep their digits.
const BIG_NUMBER = /(?<![\w.-])\d{4,}(?![\w.])/g;

function humanizeCode(code: string): string {
  const words = code.toLowerCase().split("_").join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** 25000000 → "25M", 1250000 → "1.25M", 45000 → "45K". */
export function compactNumber(raw: string): string {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 10_000) return raw;
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 2 }).format(
    value,
  );
}

export function readableText(text: string): string {
  return text.replace(BIG_NUMBER, compactNumber).replace(CODE, humanizeCode);
}

export function splitAlertTitle(raw: string): AlertText {
  const [head = raw, ...rest] = raw.split(/\s+[—–]\s+/);
  const reason = rest.join(", ").trim();
  return { title: readableText(head.trim()), reason: reason ? readableText(reason) : null };
}
