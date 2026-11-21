import { useState } from "react";

import type { ConditionLeaf } from "../../api/types";
import { Select } from "../ui/Select";
import { TextInput } from "../ui/TextInput";

interface FieldControl {
  readonly id: string;
  readonly "aria-describedby": string | undefined;
  readonly "aria-invalid": boolean;
}

export type ValueKind = "string" | "number" | "boolean";

interface ConditionValueInputProps {
  readonly op: ConditionLeaf["op"];
  readonly value: unknown;
  readonly label: string;
  /** id and aria attributes from the surrounding Field; they go on the main control. */
  readonly control: FieldControl;
  readonly onChange: (value: unknown) => void;
}

function kindOf(value: unknown): ValueKind {
  if (typeof value === "number") return "number";
  if (typeof value === "boolean") return "boolean";
  return "string";
}

function toText(value: unknown): string {
  if (Array.isArray(value)) return value.map(toText).join(", ");
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

/** Text to typed value; null means "not committable yet" (e.g. a half-typed number). */
function fromText(op: ConditionLeaf["op"], text: string, kind: ValueKind): unknown {
  if (op === "in") {
    return text
      .split(",")
      .map((item) => item.trim())
      .filter((item) => item !== "")
      .map((item) => (/^-?\d+(\.\d+)?$/.test(item) ? Number(item) : item));
  }
  if (kind === "number") return /^-?\d+(\.\d+)?([eE][+-]?\d+)?$/.test(text) ? Number(text) : null;
  return text;
}

const SEVERITIES = [
  { value: "debug", label: "Debug" },
  { value: "info", label: "Info" },
  { value: "warning", label: "Warning" },
  { value: "error", label: "Error" },
  { value: "critical", label: "Critical" },
];

const TIME_WINDOW = /^(\d{2}:\d{2})-(\d{2}:\d{2})$/;

/** "HH:MM-HH:MM" in UTC as two time pickers; a window that wraps midnight is allowed. */
function TimeWindowInput({
  value,
  control,
  label,
  onChange,
}: {
  readonly value: unknown;
  readonly control: FieldControl;
  readonly label: string;
  readonly onChange: (value: unknown) => void;
}) {
  const match = typeof value === "string" ? TIME_WINDOW.exec(value) : null;
  const from = match?.[1] ?? "08:00";
  const to = match?.[2] ?? "20:00";
  const timeClass =
    "h-10 rounded-input border border-transparent bg-fill px-3 text-body text-ink num transition-colors hover:bg-hairline/60";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        {...control}
        type="time"
        value={from}
        aria-label={`${label} from`}
        onChange={(event) => {
          onChange(`${event.target.value}-${to}`);
        }}
        className={timeClass}
      />
      <span className="text-meta text-ink-2">to</span>
      <input
        type="time"
        value={to}
        aria-label={`${label} to`}
        onChange={(event) => {
          onChange(`${from}-${event.target.value}`);
        }}
        className={timeClass}
      />
      <span className="text-meta text-ink-3">UTC</span>
    </div>
  );
}

/** Value editor whose widget follows the operator: list, true/false, or typed scalar. */
export function ConditionValueInput({
  op,
  value,
  label,
  control,
  onChange,
}: ConditionValueInputProps) {
  const [kind, setKind] = useState<ValueKind>(kindOf(value));
  const [text, setText] = useState(toText(value));
  const [committed, setCommitted] = useState(value);
  // Resync the draft when the YAML changed the value underneath us; half-typed text never does.
  if (JSON.stringify(committed) !== JSON.stringify(value)) {
    setCommitted(value);
    setText(toText(value));
    setKind(kindOf(value));
  }

  if (op === "severity_gte") {
    return (
      <Select
        {...control}
        options={SEVERITIES}
        value={typeof value === "string" && value !== "" ? value.toLowerCase() : "warning"}
        onChange={onChange}
      />
    );
  }

  if (op === "time_between") {
    return <TimeWindowInput value={value} control={control} label={label} onChange={onChange} />;
  }

  if (op === "exists") {
    return (
      <Select
        {...control}
        options={[
          { value: "true", label: "present in the event" },
          { value: "false", label: "missing from the event" },
        ]}
        value={value === false ? "false" : "true"}
        onChange={(next) => {
          onChange(next === "true");
        }}
      />
    );
  }

  function commit(nextText: string, nextKind: ValueKind) {
    setText(nextText);
    setKind(nextKind);
    const next = nextKind === "boolean" ? nextText === "true" : fromText(op, nextText, nextKind);
    if (next === null) return;
    setCommitted(next);
    onChange(next);
  }

  const isList = op === "in";
  return (
    <div className="flex flex-col gap-2 sm:flex-row">
      {isList ? null : (
        <div className="shrink-0 sm:w-32">
          <Select
            aria-label={`${label} value type`}
            options={[
              { value: "string", label: "Text" },
              { value: "number", label: "Number" },
              { value: "boolean", label: "Yes / no" },
            ]}
            value={kind}
            onChange={(next) => {
              const nextKind = next as ValueKind;
              commit(nextKind === "boolean" ? "true" : text, nextKind);
            }}
          />
        </div>
      )}
      {kind === "boolean" && !isList ? (
        <Select
          {...control}
          options={[
            { value: "true", label: "Yes" },
            { value: "false", label: "No" },
          ]}
          value={text === "false" ? "false" : "true"}
          onChange={(next) => {
            commit(next, "boolean");
          }}
        />
      ) : (
        <TextInput
          {...control}
          placeholder={isList ? "a, b, c" : "10000000"}
          value={text}
          onChange={(event) => {
            commit(event.target.value, kind);
          }}
        />
      )}
    </div>
  );
}
