import type { ConfigValidationError, Recipient, Severity } from "../../api/types";

/** One entry of Recipient.channel_preferences (taken from the generated schema). */
export type ChannelPreference = NonNullable<Recipient["channel_preferences"]>[number];

/** Severities in contract order (components["schemas"]["Severity"]). */
export const SEVERITIES: readonly Severity[] = ["debug", "info", "warning", "error", "critical"];

/** A preference with every optional contract field filled in, so the form is fully controlled. */
export interface PreferenceDraft {
  readonly severities: readonly Severity[];
  readonly sources: readonly string[];
  readonly channels: readonly string[];
  readonly startTime: string;
  readonly endTime: string;
  readonly timezone: string;
  readonly otherwise: readonly string[];
}

export function emptyDraft(defaultChannel: string | undefined): PreferenceDraft {
  return {
    severities: [],
    sources: [],
    channels: defaultChannel === undefined ? [] : [defaultChannel],
    startTime: "",
    endTime: "",
    timezone: "Europe/Warsaw",
    otherwise: [],
  };
}

export function toDraft(preference: ChannelPreference): PreferenceDraft {
  const [startTime = "", endTime = ""] = (preference.working_hours ?? "").split("-");
  return {
    severities: preference.when?.severities ?? [],
    sources: preference.when?.sources ?? [],
    channels: preference.channels,
    startTime,
    endTime,
    timezone: preference.timezone,
    otherwise: preference.otherwise ?? [],
  };
}

/** Back to the contract shape; half-filled hours are sent as typed so the API names the field. */
export function fromDraft(draft: PreferenceDraft): ChannelPreference {
  const hasHours = draft.startTime !== "" || draft.endTime !== "";
  return {
    when: { severities: [...draft.severities], sources: [...draft.sources] },
    channels: [...draft.channels],
    working_hours: hasHours ? `${draft.startTime}-${draft.endTime}` : null,
    timezone: draft.timezone,
    otherwise: [...draft.otherwise],
  };
}

/** Errors under `channel_preferences.<index>.<field>` (the whole row when field is omitted). */
export function errorsAt(
  errors: readonly ConfigValidationError[],
  index: number,
  field?: string,
): ConfigValidationError[] {
  const prefix = `channel_preferences.${String(index)}`;
  const wanted = field === undefined ? prefix : `${prefix}.${field}`;
  return errors.filter((e) => e.path === wanted || e.path.startsWith(`${wanted}.`));
}

export function toggled<T>(values: readonly T[], value: T): T[] {
  return values.includes(value) ? values.filter((v) => v !== value) : [...values, value];
}
