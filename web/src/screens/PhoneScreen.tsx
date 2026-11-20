import { PhonePage } from "../pages/PhonePage";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** Phone screen (not restyled yet: renders the existing page in the legacy frame). */
export function PhoneScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Phone" context={teamLabel} isLegacy>
      <PhonePage teamId={teamId} />
    </PageFrame>
  );
}
