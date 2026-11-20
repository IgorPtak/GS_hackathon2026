import type { Team } from "../../api/types";
import { PRODUCT_NAME } from "../../lib/brand";
import { teamBlurb, teamShortName } from "../../lib/teams";
import { Avatar } from "../ui/Avatar";
import { BeaconLogo } from "../ui/BeaconLogo";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { Skeleton } from "../ui/Skeleton";

interface FirstRunScreenProps {
  readonly teams: readonly Team[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly onRetry: () => void;
  readonly onSelect: (teamId: string) => void;
}

/** Full-window team choice shown until a team is stored. */
export function FirstRunScreen({
  teams,
  isLoading,
  error,
  onRetry,
  onSelect,
}: FirstRunScreenProps) {
  return (
    <main className="flex min-w-0 flex-1 flex-col items-center overflow-y-auto bg-panel px-6 py-12 max-sm:py-8">
      <div className="my-auto flex w-full max-w-3xl flex-col items-center gap-10">
        <div className="flex flex-col items-center gap-4 text-center">
          <span className="flex size-12 items-center justify-center rounded-tile bg-ink text-window">
            <BeaconLogo size={26} />
          </span>
          <h1 className="text-page font-semibold tracking-tight">Which team are you on?</h1>
          <p className="max-w-md text-body text-ink-2">
            {PRODUCT_NAME} shows the alerts, approvals and runbooks of your team. You can switch
            teams at any time from the bottom of the sidebar.
          </p>
        </div>
        {error ? (
          <EmptyState
            icon="alert"
            action={
              <Button variant="primary" onClick={onRetry}>
                Try again
              </Button>
            }
          >
            {error}. Check that the API is running, then try again.
          </EmptyState>
        ) : (
          <ul className="grid w-full grid-cols-2 gap-4 max-sm:grid-cols-1">
            {isLoading
              ? [0, 1, 2, 3].map((index) => (
                  <li key={index}>
                    <Skeleton className="h-[148px] rounded-card" />
                  </li>
                ))
              : teams.map((team) => (
                  <li key={team.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelect(team.id);
                      }}
                      className="flex h-full w-full flex-col items-start gap-4 rounded-card border border-hairline bg-card p-6 text-left shadow-card transition-shadow hover:shadow-tile"
                    >
                      <Avatar name={team.display_name} team={team.id} size="xl" />
                      <span className="flex flex-col gap-1">
                        <span className="text-card-title font-semibold">
                          {teamShortName(team.display_name)}
                        </span>
                        <span className="text-body text-ink-2">{teamBlurb(team.id)}</span>
                      </span>
                    </button>
                  </li>
                ))}
          </ul>
        )}
      </div>
    </main>
  );
}
