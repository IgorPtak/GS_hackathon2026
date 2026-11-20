import type { ConfigValidationError } from "../../api/types";
import { Button } from "../ui/Button";
import { Icon } from "../ui/icons";
import { Select } from "../ui/Select";
import { FieldErrors } from "./FieldErrors";
import { existsPaths, matchFromPaths, type Match } from "./schemaDraft";

interface MatchConditionsEditorProps {
  readonly match: Match;
  readonly paths: readonly string[];
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (match: Match) => void;
}

/** "Recognise events that have all of these fields" (advanced). */
export function MatchConditionsEditor({
  match,
  paths,
  errors,
  onChange,
}: MatchConditionsEditorProps) {
  const selected = existsPaths(match);
  return (
    <fieldset className="space-y-2">
      <legend className="text-meta font-medium">
        Recognise events that have all of these fields
      </legend>
      {selected === null ? (
        <p className="text-meta text-ink-2">
          This mapping uses a custom condition; it is kept as suggested.
        </p>
      ) : (
        <>
          {selected.map((path, index) => (
            <div key={index} className="flex items-center gap-2">
              <Select
                aria-label={`Required field ${String(index + 1)}`}
                value={path}
                className="font-mono"
                options={[...new Set([path, ...paths])].map((p) => ({ value: p, label: p }))}
                onChange={(next) => {
                  onChange(matchFromPaths(selected.map((p, i) => (i === index ? next : p))));
                }}
              />
              <button
                type="button"
                aria-label={`Remove required field ${path}`}
                disabled={selected.length <= 1}
                onClick={() => {
                  onChange(matchFromPaths(selected.filter((_, i) => i !== index)));
                }}
                className="flex size-8 shrink-0 items-center justify-center rounded-full text-ink-2 hover:bg-fill hover:text-ink disabled:opacity-30"
              >
                <Icon name="cross" size={14} />
              </button>
            </div>
          ))}
          <Button
            variant="ghost"
            icon="plus"
            disabled={paths.length === 0}
            onClick={() => {
              const next = paths.find((p) => !selected.includes(p)) ?? paths[0];
              if (next !== undefined) onChange(matchFromPaths([...selected, next]));
            }}
          >
            Require another field
          </Button>
        </>
      )}
      <FieldErrors errors={errors} />
    </fieldset>
  );
}
