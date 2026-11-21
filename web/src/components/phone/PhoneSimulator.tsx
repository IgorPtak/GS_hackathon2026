import { useEffect, useState } from "react";

import type { PhoneMessage, Recipient } from "../../api/types";
import { useEventStream } from "../../hooks/useEventStream";
import { EmptyState } from "../ui/EmptyState";
import { Spinner } from "../ui/Spinner";
import { IncomingCallScreen } from "./IncomingCallScreen";
import { LockScreen } from "./LockScreen";
import { PhoneDeviceFrame } from "./PhoneDeviceFrame";
import { readDevPhoneState, readUrlRecipientId, resolveDevCallMessage } from "./phoneDevOverride";
import { PhoneInfoCard } from "./PhoneInfoCard";
import { useAudioUnlock } from "./useAudioUnlock";
import { usePhoneMessages } from "./usePhoneMessages";
import { useRecipients } from "./useRecipients";
import { useSpeech } from "./useSpeech";

function useIsNarrowViewport(): boolean {
  const [isNarrow, setIsNarrow] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia("(max-width: 639px)").matches : false,
  );

  useEffect(() => {
    const query = window.matchMedia("(max-width: 639px)");
    const update = () => {
      setIsNarrow(query.matches);
    };
    update();
    query.addEventListener("change", update);
    return () => {
      query.removeEventListener("change", update);
    };
  }, []);

  return isNarrow;
}

function pickDefaultRecipient(
  recipients: readonly Recipient[],
  teamId: string | null,
  urlRecipientId: string | null,
): Recipient | null {
  if (recipients.length === 0) return null;
  if (urlRecipientId) {
    const fromUrl = recipients.find((candidate) => candidate.id === urlRecipientId);
    if (fromUrl) return fromUrl;
  }
  if (teamId) {
    const teamMatch = recipients.find((candidate) => candidate.teams?.includes(teamId));
    if (teamMatch) return teamMatch;
  }
  return recipients.find((candidate) => candidate.id === "piotr") ?? recipients[0] ?? null;
}

interface PhoneSimulatorProps {
  readonly teamId: string | null;
  readonly isFullScreen?: boolean;
  /** Only the device, no side card (the test console). */
  readonly isDeviceOnly?: boolean;
}

/** iPhone-like phone simulator: live SMS lock screen, incoming calls, keypad approvals, and speech. */
export function PhoneSimulator({
  teamId,
  isFullScreen = false,
  isDeviceOnly = false,
}: PhoneSimulatorProps) {
  const { recipients, isLoading: isLoadingRecipients, error: recipientsError } = useRecipients();
  const [picked, setPicked] = useState<string | null>(readUrlRecipientId);
  const selectedRecipient =
    (picked ? recipients.find((candidate) => candidate.id === picked) : null) ??
    pickDefaultRecipient(recipients, teamId, picked);
  const recipientId = selectedRecipient?.id ?? null;

  const phone = usePhoneMessages(recipientId);
  const speech = useSpeech();
  const isAudioUnlocked = useAudioUnlock();
  const isNarrow = useIsNarrowViewport();

  const [devState, setDevState] = useState(readDevPhoneState);
  const [liveCall, setLiveCall] = useState<PhoneMessage | null>(null);
  const [isCallAnswered, setIsCallAnswered] = useState(false);
  const [answeredIds, setAnsweredIds] = useState<readonly string[]>([]);

  const { apply, reload } = phone;
  // phone.message is broadcast to every team stream, so standalone /phone can subscribe without a stored team.
  const streamTeam = teamId ?? selectedRecipient?.teams?.[0] ?? "settlements";
  const streamStatus = useEventStream(streamTeam, {
    "phone.message": (event) => {
      apply(event.message);
      if (event.message.channel_type === "phone" && event.message.recipient_id === recipientId) {
        setLiveCall(event.message);
        setIsCallAnswered(false);
      }
    },
    onReconnect: reload,
  });

  if (isLoadingRecipients) {
    return (
      <div className="flex min-h-[360px] items-center justify-center">
        <Spinner size={24} label="Loading phone simulator" />
      </div>
    );
  }

  if (recipientsError) {
    return (
      <EmptyState icon="phone">
        Could not load recipients ({recipientsError}). Check that the API is running.
      </EmptyState>
    );
  }

  if (recipientId === null) {
    return <EmptyState icon="phone">No recipients are configured yet.</EmptyState>;
  }

  const activeCall =
    liveCall ?? (devState ? resolveDevCallMessage(phone.messages, recipientId) : null);
  const isRinging = activeCall !== null && !isCallAnswered && devState !== "incall";
  const isInCall = activeCall !== null && (isCallAnswered || devState === "incall");

  function handleSelectRecipient(nextId: string) {
    setPicked(nextId);
    setLiveCall(null);
    setIsCallAnswered(false);
    setDevState(null);
  }

  const device = (
    <PhoneDeviceFrame
      isRinging={isRinging}
      isInCall={isInCall}
      isFrameless={isFullScreen && isNarrow}
      isFullScreenDesktop={isFullScreen && !isNarrow}
    >
      <LockScreen
        messages={phone.messages}
        isLoading={phone.isLoading}
        error={phone.error}
        onReload={phone.reload}
        answeredIds={answeredIds}
        activeCallId={activeCall?.id ?? null}
        recipientName={selectedRecipient?.display_name ?? null}
        isAudioUnlocked={isAudioUnlocked}
        onOpenCall={(message) => {
          setLiveCall(message);
          setIsCallAnswered(true);
        }}
        isFullScreen={isFullScreen}
        recipients={recipients}
        selectedRecipientId={recipientId}
        onSelectRecipient={handleSelectRecipient}
      />
      {activeCall ? (
        <IncomingCallScreen
          key={`${activeCall.id}-${devState ?? "live"}`}
          message={activeCall}
          recipientName={selectedRecipient?.display_name ?? null}
          isAudioUnlocked={isAudioUnlocked}
          initialAnswered={isCallAnswered || devState === "incall"}
          isSilent={devState === "incall"}
          speech={speech}
          onAnsweredChange={setIsCallAnswered}
          onClose={(answered) => {
            if (answered) setAnsweredIds((ids) => [...ids, activeCall.id]);
            setLiveCall(null);
            setIsCallAnswered(false);
            setDevState(null);
          }}
        />
      ) : null}
    </PhoneDeviceFrame>
  );

  if (isDeviceOnly) return device;

  if (isFullScreen) {
    if (isNarrow) return device;
    return <div className="flex min-h-dvh items-center justify-center p-6">{device}</div>;
  }

  return (
    <div className="mx-auto flex min-h-full max-w-4xl flex-wrap items-center justify-center gap-10 max-lg:gap-6">
      {device}
      <PhoneInfoCard
        recipients={recipients}
        selectedRecipient={selectedRecipient}
        onSelectRecipient={handleSelectRecipient}
        streamStatus={streamStatus}
        speech={speech}
      />
    </div>
  );
}
