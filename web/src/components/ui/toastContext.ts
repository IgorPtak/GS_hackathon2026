import { createContext, useContext } from "react";

export type ToastTone = "success" | "error" | "info";

export interface ToastApi {
  /** Shows a short message; errors stay longer. */
  readonly show: (message: string, tone?: ToastTone) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast needs a <ToastProvider> above it");
  return api;
}
