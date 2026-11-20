import { useState } from "react";

import { Button } from "../ui/Button";
import { Field } from "../ui/Field";
import { parseSampleJson, type SampleEvent } from "./schemaDraft";

const PLACEHOLDER =
  '{\n  "evt": "payment.declined",\n  "lvl": "WARN",\n  "data": { "paymentId": "p-1042" }\n}';

/** Paste a JSON event; validates as you type and explains what is wrong in plain words. */
export function PasteSampleForm({ onPick }: { readonly onPick: (sample: SampleEvent) => void }) {
  const [text, setText] = useState("");
  const parsed = text.trim() === "" ? null : parseSampleJson(text);
  const error = parsed && "error" in parsed ? friendlyError(parsed.error) : null;

  return (
    <div className="space-y-4">
      <Field
        label="Paste a sample event"
        help="One JSON object, exactly as your system sends it. Use synthetic data only."
        error={error}
      >
        {(control) => (
          <textarea
            {...control}
            value={text}
            onChange={(e) => {
              setText(e.target.value);
            }}
            rows={8}
            spellCheck={false}
            placeholder={PLACEHOLDER}
            className="w-full rounded-input border border-transparent bg-fill p-3.5 font-mono text-meta text-ink placeholder:text-ink-3 aria-[invalid=true]:border-critical"
          />
        )}
      </Field>
      <Button
        variant="primary"
        icon="sparkle"
        disabled={!parsed || "error" in parsed}
        onClick={() => {
          if (parsed && "sample" in parsed) onPick(parsed.sample);
        }}
      >
        Suggest a mapping
      </Button>
    </div>
  );
}

function friendlyError(message: string): string {
  if (message.startsWith("The sample")) return "The sample must be one JSON object, like { ... }.";
  return `This is not valid JSON yet. ${message.replace(/^JSON\.parse: /, "")}`;
}
