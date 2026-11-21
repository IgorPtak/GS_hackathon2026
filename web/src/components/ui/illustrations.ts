import approvalsDayAvif from "../../assets/illustrations/approvals-empty-day.avif";
import approvalsDayWebp from "../../assets/illustrations/approvals-empty-day.webp";
import approvalsNightAvif from "../../assets/illustrations/approvals-empty-night.avif";
import approvalsNightWebp from "../../assets/illustrations/approvals-empty-night.webp";
import connectDayAvif from "../../assets/illustrations/connect-day.avif";
import connectDayWebp from "../../assets/illustrations/connect-day.webp";
import connectNightAvif from "../../assets/illustrations/connect-night.avif";
import connectNightWebp from "../../assets/illustrations/connect-night.webp";
import heroDayAvif from "../../assets/illustrations/hero-day.avif";
import heroDayWebp from "../../assets/illustrations/hero-day.webp";
import heroNightAvif from "../../assets/illustrations/hero-night.avif";
import heroNightWebp from "../../assets/illustrations/hero-night.webp";
import inboxDayAvif from "../../assets/illustrations/inbox-empty-day.avif";
import inboxDayWebp from "../../assets/illustrations/inbox-empty-day.webp";
import inboxNightAvif from "../../assets/illustrations/inbox-empty-night.avif";
import inboxNightWebp from "../../assets/illustrations/inbox-empty-night.webp";
import insightsDayAvif from "../../assets/illustrations/insights-day.avif";
import insightsDayWebp from "../../assets/illustrations/insights-day.webp";
import insightsNightAvif from "../../assets/illustrations/insights-night.avif";
import insightsNightWebp from "../../assets/illustrations/insights-night.webp";
import runbooksDayAvif from "../../assets/illustrations/runbooks-day.avif";
import runbooksDayWebp from "../../assets/illustrations/runbooks-day.webp";
import runbooksNightAvif from "../../assets/illustrations/runbooks-night.avif";
import runbooksNightWebp from "../../assets/illustrations/runbooks-night.webp";

export type Scene = "hero" | "connect" | "runbooks" | "inbox" | "approvals" | "insights";

interface Sources {
  readonly avif: string;
  readonly webp: string;
}

/** Painted scenes, a day and a night version each (web/src/assets/illustrations/README.md). */
export const SCENES: Record<Scene, { readonly day: Sources; readonly night: Sources }> = {
  hero: {
    day: { avif: heroDayAvif, webp: heroDayWebp },
    night: { avif: heroNightAvif, webp: heroNightWebp },
  },
  connect: {
    day: { avif: connectDayAvif, webp: connectDayWebp },
    night: { avif: connectNightAvif, webp: connectNightWebp },
  },
  runbooks: {
    day: { avif: runbooksDayAvif, webp: runbooksDayWebp },
    night: { avif: runbooksNightAvif, webp: runbooksNightWebp },
  },
  inbox: {
    day: { avif: inboxDayAvif, webp: inboxDayWebp },
    night: { avif: inboxNightAvif, webp: inboxNightWebp },
  },
  approvals: {
    day: { avif: approvalsDayAvif, webp: approvalsDayWebp },
    night: { avif: approvalsNightAvif, webp: approvalsNightWebp },
  },
  insights: {
    day: { avif: insightsDayAvif, webp: insightsDayWebp },
    night: { avif: insightsNightAvif, webp: insightsNightWebp },
  },
};
