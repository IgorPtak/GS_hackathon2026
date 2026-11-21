import { useCallback, useEffect, useState } from "react";

export type BackHandler = (() => void) | null;
export type RegisterBack = (handler: BackHandler) => void;

/** Lets a page put its "go up one level" action into the screen header's back chevron. */
export function useBackSlot(): [(() => void) | undefined, RegisterBack] {
  const [handler, setHandler] = useState<BackHandler>(null);
  const register = useCallback((next: BackHandler) => {
    setHandler(() => next);
  }, []);
  return [handler ?? undefined, register];
}

/** Registers `handler` while `isActive`, and clears it on leave. */
export function useRegisterBack(
  register: RegisterBack | undefined,
  isActive: boolean,
  handler: () => void,
): void {
  useEffect(() => {
    if (!register) return;
    register(isActive ? handler : null);
    return () => {
      register(null);
    };
  }, [register, isActive, handler]);
}
