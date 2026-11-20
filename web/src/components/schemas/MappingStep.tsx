import type { ConfigValidationError, SchemaProfile, SchemaProfileProposal } from "../../api/types";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Field } from "../ui/Field";
import { Icon } from "../ui/icons";
import { Skeleton } from "../ui/Skeleton";
import { StatusChip } from "../ui/StatusChip";
import { TextInput } from "../ui/TextInput";
import { FieldErrors } from "./FieldErrors";
import { FingerprintPicker } from "./FingerprintPicker";
import { MappingRow } from "./MappingRow";
import { MatchConditionsEditor } from "./MatchConditionsEditor";
import {
  errorsUnder,
  FIELD_NAMES,
  fromSpec,
  isValidProfileId,
  toSpec,
  type FieldName,
} from "./schemaDraft";

interface MappingStepProps {
  readonly profile: SchemaProfile | null;
  readonly proposal: SchemaProfileProposal | null;
  readonly proposeError: string | null;
  readonly paths: readonly string[];
  readonly errors: readonly ConfigValidationError[];
  readonly onChange: (profile: SchemaProfile) => void;
  readonly onBack: () => void;
  readonly onNext: () => void;
}

/** Step 2: the proposed mapping as editable rows, a fingerprint picker and the model's notes. */
export function MappingStep(props: MappingStepProps) {
  const { profile, proposal, proposeError, paths, errors, onChange, onBack, onNext } = props;
  if (proposeError) {
    return (
      <Card>
        <p role="alert" className="text-body text-critical-ink">
          {proposeError}
        </p>
        <Button className="mt-4" onClick={onBack}>
          Choose another event
        </Button>
      </Card>
    );
  }
  if (!profile || !proposal) return <ReadingEvent />;

  const isLlm = proposal.generated_by === "llm";
  const isIdValid = isValidProfileId(profile.id);
  function setField(name: FieldName, spec: Parameters<typeof fromSpec>[0]) {
    if (profile) onChange({ ...profile, fields: { ...profile.fields, [name]: fromSpec(spec) } });
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-card-title font-semibold">
          {isLlm ? "Beacon suggests this mapping" : "Suggested from the field names"}
        </h2>
        {isLlm ? (
          <StatusChip tone="info" icon="sparkle">
            AI{proposal.model ? ` · ${proposal.model}` : ""}
          </StatusChip>
        ) : null}
      </div>
      <p className="-mt-3 text-body text-ink-2">
        Check each line against your event. Change anything that looks wrong.
      </p>
      <Card isPadded={false} className="divide-y divide-hairline px-6">
        {FIELD_NAMES.map((name) => (
          <MappingRow
            key={name}
            name={name}
            spec={toSpec(profile.fields[name])}
            paths={paths}
            errors={errorsUnder(errors, `fields.${name}`)}
            onChange={(spec) => {
              setField(name, spec);
            }}
          />
        ))}
      </Card>
      <Card>
        <FingerprintPicker
          selected={profile.fingerprint}
          paths={paths}
          errors={errorsUnder(errors, "fingerprint")}
          onChange={(fingerprint) => {
            onChange({ ...profile, fingerprint });
          }}
        />
      </Card>
      {proposal.notes && proposal.notes.length > 0 ? (
        <ProposalNotes notes={proposal.notes} />
      ) : null}
      <details className="group rounded-card border border-hairline bg-card px-6 py-4">
        <summary className="flex cursor-pointer list-none items-center gap-2 text-body font-semibold">
          <Icon
            name="chevron"
            size={16}
            className="-rotate-90 transition-transform group-open:rotate-0"
          />
          Advanced
          <span className="text-meta font-normal text-ink-2">name, priority and recognition</span>
        </summary>
        <div className="mt-4 space-y-4">
          <div className="grid gap-4 sm:grid-cols-[1fr_8rem]">
            <Field
              label="Name"
              help="Lowercase letters, digits and dashes, like payments-declined."
              error={isIdValid ? null : "Use lowercase letters, digits and single dashes."}
            >
              {(control) => (
                <TextInput
                  {...control}
                  value={profile.id}
                  className="font-mono"
                  onChange={(e) => {
                    onChange({ ...profile, id: e.target.value });
                  }}
                />
              )}
            </Field>
            <Field label="Priority" help="Higher wins when two match.">
              {(control) => (
                <TextInput
                  {...control}
                  type="number"
                  value={profile.priority}
                  onChange={(e) => {
                    onChange({ ...profile, priority: Number(e.target.value) });
                  }}
                />
              )}
            </Field>
          </div>
          <FieldErrors
            errors={[...errorsUnder(errors, "id"), ...errorsUnder(errors, "priority")]}
          />
          <Field label="Description">
            {(control) => (
              <TextInput
                {...control}
                value={profile.description}
                onChange={(e) => {
                  onChange({ ...profile, description: e.target.value });
                }}
              />
            )}
          </Field>
          <MatchConditionsEditor
            match={profile.match}
            paths={paths}
            errors={errorsUnder(errors, "match")}
            onChange={(match) => {
              onChange({ ...profile, match });
            }}
          />
        </div>
      </details>
      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={onBack}>
          Back
        </Button>
        <Button variant="primary" size="lg" disabled={!isIdValid} onClick={onNext}>
          Test this mapping
        </Button>
      </div>
    </div>
  );
}

function ReadingEvent() {
  return (
    <div className="space-y-4" role="status">
      <h2 className="text-card-title font-semibold">Reading your event…</h2>
      <p className="text-body text-ink-2">Beacon is working out which field is which.</p>
      <Card>
        <div className="space-y-4">
          <Skeleton className="h-8" />
          <Skeleton className="h-8" />
          <Skeleton className="h-8" />
          <Skeleton className="h-8" />
        </div>
      </Card>
    </div>
  );
}

function ProposalNotes({ notes }: { readonly notes: readonly string[] }) {
  return (
    <div className="flex gap-3 rounded-card bg-fill px-5 py-4 text-meta text-ink-2">
      <Icon name="sparkle" size={18} className="mt-0.5 shrink-0" />
      <div>
        <p className="mb-1 font-medium text-ink">Why Beacon chose this</p>
        <ul className="space-y-1">
          {notes.map((note, i) => (
            <li key={i} className="break-words">
              {note}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
