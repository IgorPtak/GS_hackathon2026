import { FieldErrors } from "./FieldErrors";
import { MappingForm } from "./MappingForm";
import { SchemaTestPanel } from "./SchemaTestPanel";
import {
  flattenKeyPaths,
  isValidProfileId,
  unmatchedErrors,
  type SampleEvent,
} from "./schemaDraft";
import { useSchemaDraft } from "./useSchemaDraft";

interface SchemaDraftEditorProps {
  readonly sample: SampleEvent;
  readonly label: string;
  readonly team: string | null;
  readonly onClose: () => void;
  readonly onSaved: () => void;
  readonly onCreateRule: () => void;
}

/** Mapping form for one sample: prefilled proposal, live test and save. */
export function SchemaDraftEditor({
  sample,
  label,
  team,
  onClose,
  onSaved,
  onCreateRule,
}: SchemaDraftEditorProps) {
  const draft = useSchemaDraft(sample, team);
  const paths = flattenKeyPaths(sample);
  const { profile, proposal } = draft;
  const canSave = profile !== null && isValidProfileId(profile.id) && team !== null;

  return (
    <section
      aria-label="Mapping"
      className="space-y-3 rounded border border-slate-300 bg-slate-100 p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-lg font-semibold break-all">Mapping for {label}</h3>
        <button
          type="button"
          onClick={onClose}
          className="rounded border border-slate-300 bg-white px-3 py-1 text-sm"
        >
          Close
        </button>
      </div>
      {!proposal && !draft.proposeError ? (
        <p className="text-sm text-slate-500">Proposing a mapping...</p>
      ) : null}
      {draft.proposeError ? (
        <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
          {draft.proposeError}
        </p>
      ) : null}
      {profile && proposal ? (
        <>
          <MappingForm
            profile={profile}
            paths={paths}
            origin={proposal}
            errors={draft.saveErrors}
            onChange={draft.updateProfile}
          />
          <SchemaTestPanel
            result={draft.test.result}
            isStale={draft.isStale}
            isRunning={draft.test.isRunning}
            error={draft.test.error}
            onRun={draft.runTest}
          />
          <FieldErrors errors={unmatchedErrors(draft.saveErrors)} />
          {draft.saveMessage ? (
            <p role="alert" className="rounded bg-red-50 px-3 py-2 text-sm text-red-800">
              {draft.saveMessage}
            </p>
          ) : null}
          {team === null ? (
            <p className="text-sm text-slate-600">Pick a team to save this profile.</p>
          ) : null}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              disabled={!canSave || draft.isSaving}
              onClick={() => {
                draft.save();
              }}
              className="rounded bg-slate-800 px-3 py-1.5 text-sm text-white disabled:opacity-40"
            >
              {draft.isSaving ? "Saving..." : "Save schema profile"}
            </button>
          </div>
          {draft.saved ? (
            <SavedNotice
              id={draft.saved.id}
              version={draft.saved.version}
              onCreateRule={onCreateRule}
              onDone={onSaved}
            />
          ) : null}
        </>
      ) : null}
    </section>
  );
}

function SavedNotice(props: {
  readonly id: string;
  readonly version: number;
  readonly onCreateRule: () => void;
  readonly onDone: () => void;
}) {
  return (
    <div role="status" className="space-y-2 rounded bg-green-50 px-3 py-2 text-sm text-green-900">
      <p>
        Saved <code className="font-mono">{props.id}</code> as version v{props.version}. New events
        of this shape are now recognised.
      </p>
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={props.onCreateRule}
          className="rounded bg-green-800 px-3 py-1 text-white"
        >
          Create a rule for this schema
        </button>
        <button
          type="button"
          onClick={props.onDone}
          className="rounded border border-green-800 bg-white px-3 py-1"
        >
          Done
        </button>
      </div>
    </div>
  );
}
