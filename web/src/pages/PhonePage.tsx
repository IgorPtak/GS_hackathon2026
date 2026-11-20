import { PhoneSimulator } from "../components/phone/PhoneSimulator";

export function PhonePage({
  teamId,
  isFullScreen = false,
}: {
  readonly teamId: string | null;
  readonly isFullScreen?: boolean;
}) {
  return <PhoneSimulator teamId={teamId} isFullScreen={isFullScreen} />;
}
