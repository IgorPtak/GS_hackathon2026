import { Field } from "../ui/Field";
import { TextInput } from "../ui/TextInput";
import { parsePresentFromRuleYaml, writePresentToRuleYaml } from "./presentYaml";

interface RulePresentFieldsProps {
  readonly yaml: string;
  readonly onChange: (nextYaml: string) => void;
}

/** How this rule's alerts read: a title and a line of text, filled with values from the event. */
export function RulePresentFields({ yaml, onChange }: RulePresentFieldsProps) {
  const present = parsePresentFromRuleYaml(yaml);
  if (present === null) {
    return (
      <p className="rounded-tile bg-fill px-4 py-3 text-body text-ink-2">
        This rule's look is written in a way the form cannot edit safely. Open Advanced (YAML) below
        to change it.
      </p>
    );
  }
  return (
    <div className="space-y-3">
      <div>
        <h4 className="text-body font-semibold">How the alert looks</h4>
        <p className="text-meta text-ink-2">
          Put a field in double braces to fill in its value from the event, for example{" "}
          <code className="font-mono text-ink">{"{{data.paymentId}}"}</code>. Preview shows the
          result.
        </p>
      </div>
      <Field label="Title">
        {(control) => (
          <TextInput
            {...control}
            className="font-mono text-meta"
            placeholder="Payment {{data.paymentId}} declined"
            value={present.title}
            onChange={(event) => {
              onChange(writePresentToRuleYaml(yaml, "title", event.target.value));
            }}
          />
        )}
      </Field>
      <Field label="Text">
        {(control) => (
          <TextInput
            {...control}
            className="font-mono text-meta"
            placeholder="{{data.amount}} {{data.currency}}: {{data.declineCode}}"
            value={present.body}
            onChange={(event) => {
              onChange(writePresentToRuleYaml(yaml, "body", event.target.value));
            }}
          />
        )}
      </Field>
    </div>
  );
}
