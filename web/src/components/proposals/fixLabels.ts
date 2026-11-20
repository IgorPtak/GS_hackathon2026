import type { FixKind, ProposalStatus, StepKind } from "../../api/types";
import type { ChipTone } from "../ui/StatusChip";

export const FIX_KIND_LABELS: Record<FixKind, string> = {
  threshold: "Rule threshold",
  fields: "Rule fields",
  dedup_window: "Deduplication window",
  runbook_step: "Runbook step",
  other: "Other change",
};

export const FIX_KIND_OPTIONS: readonly { readonly value: FixKind; readonly label: string }[] = [
  { value: "threshold", label: FIX_KIND_LABELS.threshold },
  { value: "fields", label: FIX_KIND_LABELS.fields },
  { value: "dedup_window", label: FIX_KIND_LABELS.dedup_window },
  { value: "runbook_step", label: FIX_KIND_LABELS.runbook_step },
  { value: "other", label: FIX_KIND_LABELS.other },
];

export const PROPOSAL_STATUS_META: Record<
  ProposalStatus,
  { readonly label: string; readonly tone: ChipTone }
> = {
  pending: { label: "Waiting for review", tone: "warning" },
  accepted: { label: "Accepted", tone: "success" },
  rejected: { label: "Rejected", tone: "neutral" },
};

export const STEP_KIND_LABELS: Record<StepKind, string> = {
  text: "Manual step",
  check: "Health check",
  action: "Automated action",
};

export const STEP_KIND_OPTIONS: readonly { readonly value: StepKind; readonly label: string }[] = [
  { value: "text", label: STEP_KIND_LABELS.text },
  { value: "check", label: STEP_KIND_LABELS.check },
  { value: "action", label: STEP_KIND_LABELS.action },
];
