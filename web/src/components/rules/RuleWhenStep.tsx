import type { ConfigValidationError } from "../../api/types";
import { Field } from "../ui/Field";
import { TextInput } from "../ui/TextInput";
import { friendlyMessage } from "./ruleErrors";
import { RuleConditionForm } from "./RuleConditionForm";
import { readTopLevel, writeTopLevel } from "./topLevelYaml";

interface RuleWhenStepProps {
  readonly yaml: string;
  readonly isNew: boolean;
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (nextYaml: string) => void;
}

function messageAt(errors: readonly ConfigValidationError[], path: string): string | undefined {
  const found = errors.find((e) => e.path === path);
  return found ? friendlyMessage(path, found.message) : undefined;
}

/** Step 1: name (for a new rule), description, and the condition as friendly rows. */
export function RuleWhenStep({ yaml, isNew, errors, onChange }: RuleWhenStepProps) {
  return (
    <div className="space-y-8">
      <div className="grid gap-4 md:grid-cols-2">
        {isNew ? (
          <Field
            label="Rule id"
            help="Lowercase letters, digits and dashes, for example rates-large-rejections."
            error={messageAt(errors, "id")}
          >
            {(control) => (
              <TextInput
                {...control}
                value={readTopLevel(yaml, "id")}
                onChange={(event) => {
                  onChange(writeTopLevel(yaml, "id", event.target.value));
                }}
              />
            )}
          </Field>
        ) : null}
        <Field label="Description" error={messageAt(errors, "description")}>
          {(control) => (
            <TextInput
              {...control}
              placeholder="What does this rule watch for?"
              value={readTopLevel(yaml, "description")}
              onChange={(event) => {
                onChange(writeTopLevel(yaml, "description", event.target.value));
              }}
            />
          )}
        </Field>
      </div>
      <RuleConditionForm yaml={yaml} errors={errors} onChange={onChange} />
    </div>
  );
}
