/** Turns the raw channel text ("[CRITICAL] Workflow x failed — UPSTREAM_TIMEOUT http://…") into
 * what a phone banner should show: a short title, a plain detail line and the severity apart. */
export interface BannerText {
  readonly severity: string | null;
  readonly title: string;
  readonly detail: string;
}

const URL_PATTERN = /\s*https?:\/\/\S+/g;
const SEVERITY_PATTERN = /^\[(\w+)\]\s*/;
const CODE_PATTERN = /\b[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+\b/g;

/** LIMIT_BREACH → "Limit breach"; leaves normal words alone. */
function humanizeCodes(text: string): string {
  return text.replace(CODE_PATTERN, (code) => {
    const words = code.toLowerCase().split("_").join(" ");
    return words.charAt(0).toUpperCase() + words.slice(1);
  });
}

export function toBannerText(raw: string): BannerText {
  let text = raw
    .replace(URL_PATTERN, "")
    .replace(/^Call:\s*/i, "")
    .trim();
  const severityMatch = SEVERITY_PATTERN.exec(text);
  const severity = severityMatch?.[1]?.toLowerCase() ?? null;
  if (severityMatch) text = text.slice(severityMatch[0].length);
  const [title = "", ...rest] = text.split(/\s+[—–]\s+/);
  return {
    severity,
    title: humanizeCodes(title).trim(),
    detail: humanizeCodes(rest.join(". ")).trim(),
  };
}
