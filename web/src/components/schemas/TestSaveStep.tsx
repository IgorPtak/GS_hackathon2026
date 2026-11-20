import type {
  ConfigValidationError,
  SchemaProfileRecord,
  SchemaProfileTestResult,
} from "../../api/types";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Icon } from "../ui/icons";
import { Skeleton } from "../ui/Skeleton";
import { FieldErrors } from "./FieldErrors";
import { findSampleRow, isSampleRead, unmatchedErrors } from "./schemaDraft";

interface TestSaveStepProps {
  readonly result: SchemaProfileTestResult | null;
  readonly isStale: boolean;
  readonly isRunning: boolean;
  readonly testError: string | null;
  readonly saved: SchemaProfileRecord | null;
  readonly isSaving: boolean;
  readonly saveMessage: string | null;
  readonly saveErrors: readonly ConfigValidationError[];
  readonly canSave: boolean;
  readonly onRetest: () => void;
  readonly onBack: () => void;
  readonly onSave: () => void;
  readonly onCreateRule: () => void;
  readonly onDone: () => void;
}

/** Step 3: a big pass/fail verdict on the sample, then Save and the success state. */
export function TestSaveStep(props: TestSaveStepProps) {
  const { result, isRunning, testError, saved } = props;
  if (saved) return <SavedState {...props} saved={saved} />;
  const isRead = result !== null && isSampleRead(result);
  return (
    <div className="space-y-5">
      <h2 className="text-card-title font-semibold">Test and save</h2>
      {isRunning && !result ? <Skeleton className="h-40" /> : null}
      {testError ? (
        <Card>
          <p role="alert" className="text-body text-critical-ink">
            {testError}
          </p>
          <Button className="mt-4" onClick={props.onRetest}>
            Try the test again
          </Button>
        </Card>
      ) : null}
      {result ? <Verdict result={result} isRead={isRead} isStale={props.isStale} /> : null}
      <FieldErrors errors={unmatchedErrors([...props.saveErrors])} />
      {props.saveMessage ? (
        <p role="alert" className="text-body text-critical-ink">
          {props.saveMessage}
        </p>
      ) : null}
      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" onClick={props.onBack}>
          Change the mapping
        </Button>
        <div className="flex gap-2">
          {props.isStale ? (
            <Button isLoading={isRunning} onClick={props.onRetest}>
              Test again
            </Button>
          ) : null}
          <Button
            variant="primary"
            size="lg"
            isLoading={props.isSaving}
            disabled={!props.canSave || props.isStale || (result !== null && !isRead)}
            onClick={props.onSave}
          >
            Save mapping
          </Button>
        </div>
      </div>
    </div>
  );
}

function Verdict({
  result,
  isRead,
  isStale,
}: {
  result: SchemaProfileTestResult;
  isRead: boolean;
  isStale: boolean;
}) {
  const row = findSampleRow(result)?.normalized;
  const facts = row
    ? [
        ["Event type", row.type],
        ["Severity", row.severity],
        ["Entity", row.entity],
        ["Source", row.source],
      ]
    : [];
  return (
    <Card
      className={`${isRead ? "border-success/40 bg-success/10" : "border-critical/40 bg-critical/10"} ${isStale ? "opacity-60" : ""}`}
    >
      <div role="status" className="flex items-start gap-4">
        <span
          className={`flex size-14 shrink-0 items-center justify-center rounded-full ${isRead ? "bg-success/15 text-success-ink" : "bg-critical/12 text-critical-ink"}`}
        >
          <Icon name={isRead ? "check" : "cross"} size={28} strokeWidth={2.4} />
        </span>
        <div className="min-w-0">
          <p
            className={`text-page font-semibold ${isRead ? "text-success-ink" : "text-critical-ink"}`}
          >
            {isRead ? "Matches your sample" : "This mapping does not match your sample"}
          </p>
          <p className="mt-1 text-body text-ink-2">
            {isRead
              ? `Beacon read every field you mapped. ${matchedSentence(result)}`
              : "Beacon could not find an event type or an entity in your sample. Go back and pick the fields that hold them."}
          </p>
          {isStale ? (
            <p className="mt-1 text-meta text-ink-2">You changed the mapping. Test again.</p>
          ) : null}
        </div>
      </div>
      {isRead ? (
        <dl className="mt-5 grid grid-cols-2 gap-x-6 gap-y-3 border-t border-hairline pt-5 sm:grid-cols-4">
          {facts.map(([label, value]) => (
            <div key={label} className="min-w-0">
              <dt className="text-caption text-ink-2">{label}</dt>
              <dd className="truncate text-body font-medium">{value ?? "none"}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </Card>
  );
}

function matchedSentence(result: SchemaProfileTestResult): string {
  if (result.events_scanned === 0) return "No other events from the last hour to compare with.";
  return `Events from the last hour that fit it: ${String(result.events_matched)} of ${String(result.events_scanned)}.`;
}

function SavedState(props: TestSaveStepProps & { readonly saved: SchemaProfileRecord }) {
  return (
    <Card>
      <div role="status" className="flex flex-col items-center gap-4 py-8 text-center">
        <span className="flex size-16 items-center justify-center rounded-full bg-success/15 text-success-ink">
          <Icon name="check" size={32} strokeWidth={2.4} />
        </span>
        <h2 className="text-card-title font-semibold">Saved</h2>
        <p className="max-w-md text-body text-ink-2">
          Beacon now recognises events like this one (
          <span className="font-mono whitespace-nowrap">{props.saved.id}</span>, version{" "}
          {props.saved.version}). Next, tell Beacon who should hear about them.
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          <Button variant="primary" size="lg" icon="arrowRight" onClick={props.onCreateRule}>
            Create a rule for it
          </Button>
          <Button size="lg" onClick={props.onDone}>
            Connect another system
          </Button>
        </div>
      </div>
    </Card>
  );
}
