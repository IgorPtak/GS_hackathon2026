import type { ChannelPreference } from "./preferenceDraft";

const CHANNEL_WORDS: Record<string, string> = {
  ui: "the app",
  email: "email",
  sms: "SMS",
  phone: "phone",
};

const list = new Intl.ListFormat("en", { style: "long", type: "conjunction" });

/** "sms" becomes "SMS"; unknown channels keep their id. */
export function channelWord(channelId: string): string {
  return CHANNEL_WORDS[channelId] ?? channelId;
}

function channelList(channelIds: readonly string[]): string {
  return list.format(channelIds.map(channelWord));
}

/** "08:00-20:00" becomes "08:00–20:00" (en dash). */
function hoursWord(workingHours: string): string {
  return workingHours.replace("-", "–");
}

/** One preference as a plain sentence, e.g. "During 08:00–20:00 Europe/Warsaw, send …". */
export function describePreference(preference: ChannelPreference): string {
  const severities = preference.when?.severities ?? [];
  const sources = preference.when?.sources ?? [];
  const what = severities.length > 0 ? `${list.format(severities)} alerts` : "all alerts";
  const from = sources.length > 0 ? ` from ${list.format(sources)}` : "";
  const hours = preference.working_hours
    ? `During ${hoursWord(preference.working_hours)} ${preference.timezone}, s`
    : "S";
  const main = `${hours}end ${what}${from} by ${channelList(preference.channels)}.`;
  const otherwise = preference.otherwise ?? [];
  if (!preference.working_hours || otherwise.length === 0) return main;
  return `${main} Otherwise by ${channelList(otherwise)}.`;
}
