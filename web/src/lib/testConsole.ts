/** The shortcut that opens the test console from anywhere (not while typing). */
export const TEST_CONSOLE_SHORTCUT = "Shift D";

const OPEN_EVENT = "beacon:open-test-console";

/** Opens the test console from anywhere in the app (it listens on window). */
export function openTestConsole(): void {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

export function onOpenTestConsole(listener: () => void): () => void {
  window.addEventListener(OPEN_EVENT, listener);
  return () => {
    window.removeEventListener(OPEN_EVENT, listener);
  };
}
