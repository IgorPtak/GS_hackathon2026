import { useState } from "react";

import type { ConditionLeaf } from "../../api/types";

export type ValueKind = "string" | "number" | "boolean";

interface ConditionValueInputProps {
  readonly op: ConditionLeaf["op"];
  readonly value: unknown;
  readonly label: string;
  readonly onChange: (value: unknown) => void;
}

const INPUT = "min-w-0 rounded border border-slate-300 px-2 py-1 text-sm";

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

/** Value editor whose widget follows the operator: list, true/false, or typed scalar. */
export function ConditionValueInput({ op, value, label, onChange }: ConditionValueInputProps) {
  const [kind, setKind] = useState<ValueKind>(kindOf(value));
  const [text, setText] = useState(toText(value));
  const [committed, setCommitted] = useState(value);
  // Resync the draft when the YAML changed the value underneath us; half-typed text never does.
  if (JSON.stringify(committed) !== JSON.stringify(value)) {
    setCommitted(value);
    setText(toText(value));
    setKind(kindOf(value));
  }

  if (op === "exists") {
    return (
      <select
        aria-label={`${label} value`}
        className={INPUT}
        value={value === false ? "false" : "true"}
        onChange={(event) => {
          onChange(event.target.value === "true");
        }}
      >
        <option value="true">present</option>
        <option value="false">missing</option>
      </select>
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

  return (
    <>
      {op === "in" ? null : (
        <select
          aria-label={`${label} value type`}
          className={INPUT}
          value={kind}
          onChange={(event) => {
            const nextKind = event.target.value as ValueKind;
            commit(nextKind === "boolean" ? "true" : text, nextKind);
          }}
        >
          <option value="string">text</option>
          <option value="number">number</option>
          <option value="boolean">boolean</option>
        </select>
      )}
      {kind === "boolean" && op !== "in" ? (
        <select
          aria-label={`${label} value`}
          className={INPUT}
          value={text === "false" ? "false" : "true"}
          onChange={(event) => {
            commit(event.target.value, "boolean");
          }}
        >
          <option value="true">true</option>
          <option value="false">false</option>
        </select>
      ) : (
        <input
          aria-label={`${label} value`}
          className={`${INPUT} flex-1`}
          placeholder={op === "in" ? "a, b, c" : "value"}
          value={text}
          onChange={(event) => {
            commit(event.target.value, kind);
          }}
        />
      )}
    </>
  );
}
