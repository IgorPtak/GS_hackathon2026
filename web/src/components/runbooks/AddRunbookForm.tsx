import { useRef } from "react";

import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Field } from "../ui/Field";
import { Icon } from "../ui/icons";
import { Segmented } from "../ui/Segmented";
import { TextInput } from "../ui/TextInput";
import { formatFromFileName, titleFromFileName, type RunbookFormatId } from "./runbookFormat";

export interface RunbookDraft {
  readonly title: string;
  readonly source: string;
  readonly format: RunbookFormatId;
  readonly fileName: string | null;
}

interface AddRunbookFormProps {
  readonly draft: RunbookDraft;
  readonly isReading: boolean;
  readonly error: string | null;
  readonly onChange: (draft: RunbookDraft) => void;
  readonly onRead: () => void;
}

const FORMAT_OPTIONS = [
  { value: "text", label: "Plain text" },
  { value: "markdown", label: "Markdown" },
  { value: "yaml", label: "YAML" },
];

/** Paste a runbook or pick a file; YAML and the format choice live under "Advanced". */
export function AddRunbookForm({ draft, isReading, error, onChange, onRead }: AddRunbookFormProps) {
  const fileInput = useRef<HTMLInputElement>(null);

  async function readFile(file: File) {
    const source = await file.text();
    onChange({
      title: draft.title || titleFromFileName(file.name),
      source,
      format: formatFromFileName(file.name),
      fileName: file.name,
    });
  }

  return (
    <Card className="space-y-5">
      <Field
        label="Name"
        help="Shown in the runbook list, for example “Settlement workflow failed”."
      >
        {(control) => (
          <TextInput
            {...control}
            value={draft.title}
            placeholder="What is this runbook for?"
            onChange={(e) => {
              onChange({ ...draft, title: e.target.value });
            }}
          />
        )}
      </Field>
      <Field
        label="Paste your runbook"
        help="Write it the way you would tell a colleague. Beacon finds the steps."
        error={error}
      >
        {(control) => (
          <textarea
            {...control}
            value={draft.source}
            rows={10}
            spellCheck={false}
            placeholder={
              "When the pricing feed goes stale, first check the feed health.\nIf it is down, restart the adapter (the lead must approve).\nThen tell the desk in chat."
            }
            onChange={(e) => {
              onChange({ ...draft, source: e.target.value, fileName: null });
            }}
            className="w-full rounded-input border border-transparent bg-fill p-3.5 text-body text-ink placeholder:text-ink-3 aria-[invalid=true]:border-critical"
          />
        )}
      </Field>
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={fileInput}
          type="file"
          accept=".md,.markdown,.txt,.yaml,.yml,text/plain,text/markdown"
          className="sr-only"
          tabIndex={-1}
          aria-label="Runbook file"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) void readFile(file);
            e.target.value = "";
          }}
        />
        <Button
          icon="file"
          onClick={() => {
            fileInput.current?.click();
          }}
        >
          Pick a .md, .txt or .yaml file
        </Button>
        {draft.fileName ? (
          <span className="text-meta text-ink-2">Loaded {draft.fileName}</span>
        ) : null}
      </div>
      <details className="group border-t border-hairline pt-4">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-body font-semibold">
          <Icon
            name="chevron"
            size={16}
            className="-rotate-90 transition-transform group-open:rotate-0"
          />
          Advanced
          <span className="text-meta font-normal text-ink-2">format and YAML</span>
        </summary>
        <div className="mt-4 space-y-2">
          <Segmented
            label="Runbook format"
            options={FORMAT_OPTIONS}
            value={draft.format}
            onChange={(value) => {
              if (value === "yaml" || value === "markdown" || value === "text") {
                onChange({ ...draft, format: value });
              }
            }}
          />
          <p className="text-meta text-ink-2">
            Pasting YAML? Choose YAML so Beacon reads it exactly as written instead of asking the
            AI.
          </p>
        </div>
      </details>
      <div className="flex justify-end">
        <Button
          variant="primary"
          size="lg"
          icon="sparkle"
          isLoading={isReading}
          disabled={draft.source.trim() === ""}
          onClick={onRead}
        >
          Turn into steps
        </Button>
      </div>
    </Card>
  );
}
