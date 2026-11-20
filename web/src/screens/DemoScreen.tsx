import { useEffect, useState, useSyncExternalStore } from "react";

import { DemoPanelContent } from "../components/demo/DemoPanelContent";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Dialog } from "../components/ui/Dialog";
import { PageFrame } from "../components/ui/PageFrame";
import type { TabId } from "../lib/tabs";

const mountedSheetOwners = new Set<symbol>();
const ownerListeners = new Set<() => void>();

function notifyOwners(): void {
  ownerListeners.forEach((listener) => {
    listener();
  });
}

function subscribeOwners(listener: () => void): () => void {
  ownerListeners.add(listener);
  return () => {
    ownerListeners.delete(listener);
  };
}

function isFirstOwner(owner: symbol): boolean {
  return mountedSheetOwners.values().next().value === owner;
}

function isEditableElement(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  const tag = target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
  return target.isContentEditable || target.closest("[contenteditable='true']") !== null;
}

function readDemoOpenOverride(): boolean {
  return new URLSearchParams(window.location.search).get("demo") === "open";
}

function navigateToInbox(): void {
  const params = new URLSearchParams(window.location.search);
  params.delete("demo");
  const query = params.toString();
  window.history.pushState(null, "", query ? `/inbox?${query}` : "/inbox");
  window.dispatchEvent(new PopStateEvent("popstate"));
}

/**
 * Keyboard listener + floating Dialog for the demo controls (`Shift+D` or `?demo=open`).
 * Deduplicates automatically so the shell only needs `<DemoSheet />` once inside `ToastProvider`.
 */
export function DemoSheet({ onNavigate }: { readonly onNavigate?: (tab: TabId) => void }) {
  const [owner] = useState(() => Symbol("demo-sheet"));
  const [isOpen, setIsOpen] = useState(readDemoOpenOverride);
  const isPrimary = useSyncExternalStore(subscribeOwners, () => isFirstOwner(owner));

  useEffect(() => {
    mountedSheetOwners.add(owner);
    notifyOwners();
    return () => {
      mountedSheetOwners.delete(owner);
      notifyOwners();
    };
  }, [owner]);

  useEffect(() => {
    if (!isPrimary) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.key === "D" &&
        event.shiftKey &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey &&
        !isEditableElement(event.target)
      ) {
        event.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [isPrimary]);

  if (!isPrimary) return null;

  return (
    <Dialog
      isOpen={isOpen}
      onClose={() => {
        setIsOpen(false);
      }}
      title="Demo panel"
      footer={
        <div className="flex w-full items-center justify-between gap-4">
          <p className="text-meta text-ink-3">Press Shift+D anywhere to toggle</p>
          <Button
            variant="secondary"
            onClick={() => {
              setIsOpen(false);
            }}
          >
            Done
          </Button>
        </div>
      }
    >
      <p className="mb-4 text-body text-ink-2">
        Trigger realistic incidents, deduplication bursts, and gateway outages against the live
        stack.
      </p>
      <DemoPanelContent
        onNavigate={onNavigate}
        onAfterNavigate={() => {
          setIsOpen(false);
        }}
      />
    </Dialog>
  );
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
