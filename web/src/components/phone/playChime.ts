/** Plays a short, pleasant two-note sine chime before spoken call scripts begin. */
export function playSpeechChime(): Promise<void> {
  const Ctor: typeof AudioContext | undefined =
    typeof window !== "undefined" ? window.AudioContext : undefined;
  if (typeof Ctor !== "function") return Promise.resolve();

  let ctx: AudioContext;
  try {
    ctx = new Ctor();
  } catch {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    void ctx.resume().catch(() => undefined);
    const now = ctx.currentTime + 0.02;
    const notes: readonly (readonly [number, number, number])[] = [
      [523.25, 0, 0.16],
      [659.25, 0.13, 0.24],
    ];

    for (const [freq, offset, duration] of notes) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now + offset);
      gain.gain.setValueAtTime(0.0001, now + offset);
      gain.gain.linearRampToValueAtTime(0.07, now + offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + duration);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + offset);
      osc.stop(now + offset + duration + 0.02);
    }

    window.setTimeout(() => {
      void ctx.close().catch(() => undefined);
      resolve();
    }, 420);
  });
}

const DTMF_FREQS: Record<string, readonly [number, number]> = {
  "1": [697, 1209],
  "2": [697, 1336],
  "3": [697, 1477],
  "4": [770, 1209],
  "5": [770, 1336],
  "6": [770, 1477],
  "7": [852, 1209],
  "8": [852, 1336],
  "9": [852, 1477],
  "*": [941, 1209],
  "0": [941, 1336],
  "#": [941, 1477],
};

/** Plays a soft, brief DTMF keypad tone for tactile feedback. */
export function playKeypadTone(key: string): void {
  const pair = DTMF_FREQS[key];
  const Ctor: typeof AudioContext | undefined =
    typeof window !== "undefined" ? window.AudioContext : undefined;
  if (!pair || typeof Ctor !== "function") return;
  try {
    const ctx = new Ctor();
    void ctx.resume().catch(() => undefined);
    const now = ctx.currentTime;
    for (const freq of pair) {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(freq, now);
      gain.gain.setValueAtTime(0.035, now);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.09);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now);
      osc.stop(now + 0.1);
    }
    window.setTimeout(() => {
      void ctx.close().catch(() => undefined);
    }, 150);
  } catch {
    // Audio feedback is best effort.
  }
}
