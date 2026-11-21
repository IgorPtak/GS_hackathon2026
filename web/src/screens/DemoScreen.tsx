import { DemoPanelContent } from "../components/demo/DemoPanelContent";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageFrame } from "../components/ui/PageFrame";

function navigateToInbox(): void {
  const params = new URLSearchParams(window.location.search);
  params.delete("demo");
  const query = params.toString();
  window.history.pushState(null, "", query ? `/inbox?${query}` : "/inbox");
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/** Standalone `/demo` route for driving live scenarios without leaving the app window. */
export function DemoScreen() {
  return (
    <PageFrame
      title="Demo panel"
      context="Live scenario triggers"
      actions={
        <Button variant="secondary" icon="inbox" onClick={navigateToInbox}>
          Open Inbox
        </Button>
      }
    >
      <div className="mx-auto max-w-2xl space-y-5">
        <Card className="space-y-4">
          <div>
            <h2 className="text-card-title font-semibold text-ink">Run a scenario</h2>
            <p className="mt-1 text-body text-ink-2">
              Each button sends live events through ingest or toggles the mock SMS gateway. You can
              also open this sheet from any screen with{" "}
              <kbd className="rounded-md border border-hairline bg-fill px-1.5 py-0.5 text-meta font-medium text-ink">
                Shift+D
              </kbd>
              .
            </p>
          </div>
          <DemoPanelContent />
        </Card>
      </div>
    </PageFrame>
  );
}
