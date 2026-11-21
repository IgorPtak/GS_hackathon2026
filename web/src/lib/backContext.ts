import { createContext, useContext } from "react";

export interface PageBack {
  readonly onBack: () => void;
  readonly label: string;
}

/** Filled by the shell when a link inside a page jumped to the current page. */
export const PageBackContext = createContext<PageBack | null>(null);

export function usePageBack(): PageBack | null {
  return useContext(PageBackContext);
}
