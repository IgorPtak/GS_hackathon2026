import { useCallback, useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type {
  ConfigValidationError,
  SchemaProfile,
  SchemaProfileProposal,
  SchemaProfileRecord,
  SchemaProfileTestResult,
} from "../../api/types";
import { detailsFromBody, messageFromBody } from "../rules/ruleErrors";
import type { SampleEvent } from "./schemaDraft";

interface TestState {
  readonly result: SchemaProfileTestResult | null;
  /** JSON of the profile that was tested; differs from the current profile when stale. */
  readonly testedKey: string | null;
  readonly isRunning: boolean;
  readonly error: string | null;
}

const IDLE_TEST: TestState = { result: null, testedKey: null, isRunning: false, error: null };

function errorText(e: unknown): string {
  return e instanceof Error ? e.message : "API unreachable";
}

/** Propose -> edit -> test -> save flow for one sample event. */
export function useSchemaDraft(sample: SampleEvent, team: string | null) {
  const [proposal, setProposal] = useState<SchemaProfileProposal | null>(null);
  const [proposeError, setProposeError] = useState<string | null>(null);
  const [profile, setProfile] = useState<SchemaProfile | null>(null);
  const [test, setTest] = useState<TestState>(IDLE_TEST);
  const [saved, setSaved] = useState<SchemaProfileRecord | null>(null);
  const [saveErrors, setSaveErrors] = useState<ConfigValidationError[]>([]);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  const runTest = useCallback(
    async (target: SchemaProfile) => {
      const key = JSON.stringify(target);
      setTest((t) => ({ ...t, isRunning: true, error: null }));
      try {
        const { data, error } = await apiClient.POST("/api/v1/schema-profiles/test", {
          body: { schema_profile: target, window: "1h", sample_event: sample },
        });
        setTest(
          data
            ? { result: data, testedKey: key, isRunning: false, error: null }
            : { ...IDLE_TEST, error: messageFromBody(error, "Test failed") },
        );
      } catch (e) {
        setTest({ ...IDLE_TEST, error: errorText(e) });
      }
    },
    [sample],
  );

  useEffect(() => {
    let isCancelled = false;
    apiClient
      .POST("/api/v1/schema-profiles/propose", { body: { sample_event: sample, profile_id: null } })
      .then(({ data, error }) => {
        if (isCancelled) return;
        if (!data) {
          setProposeError(messageFromBody(error, "Could not propose a schema"));
          return;
        }
        setProposal(data);
        setProfile(data.profile);
        void runTest(data.profile);
      })
      .catch((e: unknown) => {
        if (!isCancelled) setProposeError(errorText(e));
      });
    return () => {
      isCancelled = true;
    };
  }, [sample, runTest]);

  function updateProfile(next: SchemaProfile) {
    setProfile(next);
    setSaveErrors([]);
    setSaveMessage(null);
    setSaved(null);
  }

  async function save() {
    if (!profile || team === null) return;
    setIsSaving(true);
    setSaveMessage(null);
    try {
      const { data, error } = await apiClient.PUT("/api/v1/schema-profiles/{profile_id}", {
        params: { path: { profile_id: profile.id } },
        body: { schema_profile: profile, actor: { id: `${team}-operator`, display_name: null } },
      });
      if (data) {
        setSaved(data);
        setSaveErrors([]);
      } else {
        setSaveErrors(detailsFromBody(error));
        setSaveMessage(messageFromBody(error, "Save failed"));
      }
    } catch (e) {
      setSaveMessage(errorText(e));
    } finally {
      setIsSaving(false);
    }
  }

  const isStale = profile !== null && test.testedKey !== JSON.stringify(profile);
  return {
    proposal,
    proposeError,
    profile,
    updateProfile,
    test,
    isStale,
    runTest: () => {
      if (profile) void runTest(profile);
    },
    saved,
    saveErrors,
    saveMessage,
    isSaving,
    save: () => {
      void save();
    },
  };
}
