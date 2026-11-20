import { PageFrame } from "../components/ui/PageFrame";
import { PhonePage } from "../pages/PhonePage";
import type { ScreenProps } from "./types";

/** Phone screen: simulated on-call device with SMS banners, incoming calls, and keypad approvals. */
export function PhoneScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="Phone" context={teamLabel}>
      <PhonePage teamId={teamId} />
    </PageFrame>
  );
}
