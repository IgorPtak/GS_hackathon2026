import type { Runbook, RunbookStep } from "../../api/types";

export type RunbookFormatId = Runbook["format"];

const FORMAT_LABELS: Record<RunbookFormatId, string> = {
  text: "Plain text",
  markdown: "Markdown",
  yaml: "YAML",
};

export function formatLabel(format: RunbookFormatId): string {
  return FORMAT_LABELS[format];
}

/** Who turned the source into steps, in words. */
export function normalizedByLabel(by: Runbook["normalized_by"]): string {
  if (by === "llm") return "Read by AI";
  if (by === "parser") return "Read by parser";
  return "Kept as one step";
}

/** Guess the runbook format from a file name; plain text when unsure. */
export function formatFromFileName(name: string): RunbookFormatId {
  const lower = name.toLowerCase();
  if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "yaml";
  if (lower.endsWith(".md") || lower.endsWith(".markdown")) return "markdown";
  return "text";
}

/** Runbook id from a title: lowercase letters, digits and dashes, at most 64 characters. */
export function slugifyTitle(title: string): string {
  return title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64)
    .replace(/-+$/, "");
}

/** Title for a dropped file: the file name without its extension, spaces for separators. */
export function titleFromFileName(name: string): string {
  const base = name
    .replace(/\.[^.]+$/, "")
    .replace(/[-_]+/g, " ")
    .trim();
  return base === "" ? "" : base.charAt(0).toUpperCase() + base.slice(1);
}

export function stepCountLabel(count: number): string {
  return `${String(count)} ${count === 1 ? "step" : "steps"}`;
}

type StepIcon = "file" | "check" | "auto";

export function stepIconName(kind: RunbookStep["kind"]): StepIcon {
  if (kind === "check") return "check";
  if (kind === "action") return "auto";
  return "file";
}

export function stepKindLabel(kind: RunbookStep["kind"]): string {
  if (kind === "check") return "Check";
  if (kind === "action") return "Action";
  return "Note";
}

/** "settlements" becomes "Settlements"; team ids are single lowercase words. */
export function teamName(teamId: string): string {
  return teamId.charAt(0).toUpperCase() + teamId.slice(1);
}

/** Shows `{{workflowId}}` placeholders as ‹workflowId›; the original text keeps the real syntax. */
export function plainStepText(text: string): string {
  return text.replace(/\{\{\s*([^{}]+?)\s*\}\}/g, "‹$1›");
}
