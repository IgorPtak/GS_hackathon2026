import { RecipientsSection } from "../components/recipients/RecipientsSection";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** People & channels screen (not restyled yet: renders the existing page in the legacy frame). */
export function PeopleScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="People & channels" context={teamLabel} isLegacy>
      <RecipientsSection team={teamId} />
    </PageFrame>
  );
}
