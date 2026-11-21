import { flushSync } from "react-dom";
import { useCallback, useEffect, useState } from "react";

import { ALL_PAGES, type TabId } from "./tabs";

export type Route =
  | {
      readonly kind: "shell";
      readonly tabId: TabId;
      /** Set when a link inside a page jumped here, so the header can offer a way back. */
      readonly from: string | null;
    }
  | { readonly kind: "phone" }
  | { readonly kind: "demo" };

const DEFAULT_TAB: TabId = "home";

interface HistoryState {
  readonly from?: string;
}

function readFrom(): string | null {
  const state = window.history.state as HistoryState | null;
  return typeof state?.from === "string" ? state.from : null;
}

export function parseRoute(pathname: string, from: string | null = null): Route {
  const path = pathname.replace(/\/+$/, "") || "/";
  if (path === "/phone") return { kind: "phone" };
  if (path === "/demo") return { kind: "demo" };
  const page = ALL_PAGES.find((candidate) => candidate.path === path);
  return { kind: "shell", tabId: page?.id ?? DEFAULT_TAB, from };
}

export function pathForTab(tabId: TabId): string {
  return ALL_PAGES.find((page) => page.id === tabId)?.path ?? "/home";
}

export interface NavigateOptions {
  /** A jump from inside a page (not the rail): remember where we came from. */
  readonly isDeepLink?: boolean;
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
export function useRoute(): {
  route: Route;
  navigate: (path: string, options?: NavigateOptions) => void;
} {
  const [route, setRoute] = useState<Route>(() => parseRoute(window.location.pathname, readFrom()));

  useEffect(() => {
    // "/" and unknown paths are rewritten to the default page without adding a history entry.
    const known = ALL_PAGES.some((page) => page.path === window.location.pathname);
    if (!known && !["/phone", "/demo"].includes(window.location.pathname)) {
      window.history.replaceState(null, "", pathForTab(DEFAULT_TAB) + window.location.search);
    }
    const handlePopState = () => {
      withViewTransition(() => {
        setRoute(parseRoute(window.location.pathname, readFrom()));
      });
    };
    window.addEventListener("popstate", handlePopState);
    return () => {
      window.removeEventListener("popstate", handlePopState);
    };
  }, []);

  const navigate = useCallback((path: string, options: NavigateOptions = {}) => {
    if (path === window.location.pathname) return;
    const from = options.isDeepLink === true ? window.location.pathname : null;
    const state: HistoryState | null = from === null ? null : { from };
    window.history.pushState(state, "", path + window.location.search);
    withViewTransition(() => {
      setRoute(parseRoute(path, from));
    });
  }, []);

  return { route, navigate };
}
