import { flushSync } from "react-dom";
import { useCallback, useEffect, useState } from "react";

import { TABS, type TabId } from "./tabs";

export type Route =
  | { readonly kind: "shell"; readonly tabId: TabId }
  | { readonly kind: "phone" }
  | { readonly kind: "demo" };

const DEFAULT_TAB: TabId = "inbox";

export function parseRoute(pathname: string): Route {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/phone") return { kind: "phone" };
  if (path === "/demo") return { kind: "demo" };
  const tab = TABS.find((candidate) => candidate.path === path);
  return { kind: "shell", tabId: tab?.id ?? DEFAULT_TAB };
}

export function pathForTab(tabId: TabId): string {
  return TABS.find((tab) => tab.id === tabId)?.path ?? "/inbox";
}

/** A calm cross-fade of the main panel between sections, when the browser supports it. */
function withViewTransition(change: () => void): void {
  const isReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (isReduced || !("startViewTransition" in document)) {
    change();
    return;
  }
  document.startViewTransition(() => {
    flushSync(change);
  });
}

/** History API routing: the rail item lives in the URL so a reload keeps the place. */
export function useRoute(): { route: Route; navigate: (path: string) => void } {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.pathname));

  useEffect(() => {
    // "/" and unknown paths are rewritten to the default page without adding a history entry.
    const known = TABS.some((tab) => tab.path === window.location.pathname);
    if (!known && !["/phone", "/demo"].includes(window.location.pathname)) {
      window.history.replaceState(null, "", pathForTab(DEFAULT_TAB) + window.location.search);
    }
    const handlePopState = () => {
      withViewTransition(() => {
        setRoute(parseRoute(window.location.pathname));
      });
    };
    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  const navigate = useCallback((path: string) => {
    if (path === window.location.pathname) return;
    window.history.pushState(null, "", path + window.location.search);
    withViewTransition(() => {
      setRoute(parseRoute(path));
    });
  }, []);

  return { route, navigate };
}
