import { RecipientsSection } from "../components/recipients/RecipientsSection";
import { PageFrame } from "../components/ui/PageFrame";
import type { ScreenProps } from "./types";

/** People & channels screen: one card per person with their channel preferences as sentences. */
export function PeopleScreen({ teamId, teamLabel }: ScreenProps) {
  return (
    <PageFrame title="People & channels" context={teamLabel}>
      <RecipientsSection key={teamId} team={teamId} />
    </PageFrame>
  );
}
