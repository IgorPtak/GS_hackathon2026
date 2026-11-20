import { PhoneSimulator } from "../components/phone/PhoneSimulator";

export function PhonePage({ teamId }: { teamId: string | null }) {
  return <PhoneSimulator teamId={teamId} />;
}
