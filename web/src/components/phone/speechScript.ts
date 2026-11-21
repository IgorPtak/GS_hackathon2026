import type { PhoneMessage } from "../../api/types";

const DIGIT_WORDS: Record<string, string> = {
  "0": "zero",
  "1": "one",
  "2": "two",
  "3": "three",
  "4": "four",
  "5": "five",
  "6": "six",
  "7": "seven",
  "8": "eight",
  "9": "nine",
};

const UUID_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const REPLY_INSTRUCTION_RE = /reply\s+approve\s+\d{4}\s+or\s+reject\s+\d{4}\.?/gi;
const WORKFLOW_ID_RE = /\b(?:wf|workflow)[-_][a-z0-9][a-z0-9_-]*\b/gi;
const LONG_CODE_TOKEN_RE = /\b[a-z]{1,6}(?:[-_][a-z0-9]{2,}){2,}\b/gi;
const SHORT_TOKEN_RE = /\b([A-Za-z]{1,3})-(\d{1,4})\b/g;

/** Converts a digit string (e.g. "4602") into spoken word tokens ("four", "six", ...). */
export function digitsToWords(code: string): readonly string[] {
  return code
    .split("")
    .map((ch) => DIGIT_WORDS[ch] ?? ch)
    .filter((word) => word !== "");
}

function speakShortToken(prefix: string, digits: string): string {
  const letters = prefix.toUpperCase().split("").join(" ");
  const spokenDigits = digitsToWords(digits).join(" ");
  return `${letters} dash ${spokenDigits}`;
}

function humanizeWorkflowId(token: string): string {
  const shortMatch = /^wf[-_](\d{1,4})$/i.exec(token);
  if (shortMatch?.[1]) return speakShortToken("WF", shortMatch[1]);
  if (token.length <= 10) return token.replace(/[-_]/g, " dash ");
  return "the workflow";
}

function cleanSentence(part: string): string {
  return part
    .replace(UUID_RE, "this item")
    .replace(WORKFLOW_ID_RE, humanizeWorkflowId)
    .replace(LONG_CODE_TOKEN_RE, (token) =>
      token.toLowerCase().startsWith("t-") ? "this trade" : "the workflow",
    )
    .replace(SHORT_TOKEN_RE, (_match, prefix: string, digits: string) =>
      speakShortToken(prefix, digits),
    )
    .replace(/\bworkflow\s+the\s+workflow\b/gi, "the workflow")
    .replace(/\bthe\s+the\b/gi, "the")
    .replace(/\s+/g, " ")
    .trim();
}

/** Turns raw alert text into short, speakable sentences without reading long UUIDs or IDs. */
export function humanizeForSpeech(rawText: string): readonly string[] {
  return rawText
    .replace(REPLY_INSTRUCTION_RE, "")
    .split(/\n+/)
    .flatMap((line) => line.split(/(?<=[.!?])\s+/))
    .map(cleanSentence)
    .filter((sentence) => sentence.length > 0)
    .map((sentence) => (/[.!?]$/.test(sentence) ? sentence : `${sentence}.`));
}

/** Builds short spoken utterances with pauses for an incoming Beacon escalation call. */
export function buildCallScript(
  message: PhoneMessage,
  recipientName: string | null,
): readonly string[] {
  const firstName = recipientName?.trim().split(/\s+/)[0] ?? "";
  const greeting = firstName ? `Hi ${firstName}.` : "Hello.";
  const sentences: string[] = [greeting, "This is Beacon.", ...humanizeForSpeech(message.text)];

  if (message.approval_code) {
    sentences.push("To approve, enter code:");
    for (const word of digitsToWords(message.approval_code)) {
      sentences.push(`${word}.`);
    }
    sentences.push("Press star to reject, or hash to hear this again.");
  }

  return sentences;
}
