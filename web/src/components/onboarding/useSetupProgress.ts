import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";

export type SetupStepId = "connect" | "rule" | "people" | "alert";

export interface SetupProgress {
  /** null while the first load is in flight. */
  readonly done: ReadonlySet<SetupStepId> | null;
  readonly profileCount: number;
  readonly ruleCount: number;
  readonly notifiedCount: number;
}

const REFRESH_MS = 4_000;

async function load(team: string): Promise<SetupProgress> {
  const [profiles, rules, config, alerts] = await Promise.all([
    apiClient.GET("/api/v1/schema-profiles"),
    apiClient.GET("/api/v1/rules", { params: { query: { team } } }),
    apiClient.GET("/api/v1/config"),
    apiClient.GET("/api/v1/alerts", { params: { query: { team, limit: 1 } } }),
  ]);
  const profileCount = profiles.data?.length ?? 0;
  const ruleCount = rules.data?.length ?? 0;
  const notifiedCount =
    config.data?.recipients.filter(
      (person) =>
        (person.teams ?? []).includes(team) && (person.channel_preferences ?? []).length > 0,
    ).length ?? 0;
  const hasAlert = (alerts.data?.items.length ?? 0) > 0;
  const done = new Set<SetupStepId>();
  if (profileCount > 0) done.add("connect");
  if (ruleCount > 0) done.add("rule");
  if (notifiedCount > 0) done.add("people");
  if (hasAlert) done.add("alert");
  return { done, profileCount, ruleCount, notifiedCount };
}

/**
 * What a new team still has to do before alerts reach it, read from the live config and alerts
 * (never from clicks), so the checklist ticks itself the moment a step really works.
 */
export function useSetupProgress(team: string, isEnabled: boolean): SetupProgress {
  const [progress, setProgress] = useState<SetupProgress>({
    done: null,
    profileCount: 0,
    ruleCount: 0,
    notifiedCount: 0,
  });
  useEffect(() => {
    if (!isEnabled) return;
    let isCancelled = false;
    const refresh = () => {
      load(team)
        .then((next) => {
          if (!isCancelled) setProgress(next);
        })
        .catch(() => undefined);
    };
    refresh();
    const timer = window.setInterval(refresh, REFRESH_MS);
    return () => {
      isCancelled = true;
      window.clearInterval(timer);
    };
  }, [team, isEnabled]);
  return progress;
}
