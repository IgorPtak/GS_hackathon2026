import type { Team } from "../../api/types";
import { PRODUCT_NAME } from "../../lib/brand";
import { teamBlurb, teamShortName } from "../../lib/teams";
import { Avatar } from "../ui/Avatar";
import { BeaconLogo } from "../ui/BeaconLogo";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { Icon } from "../ui/icons";
import { Illustration } from "../ui/Illustration";
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
    <main className="relative isolate flex min-w-0 flex-1 items-center overflow-y-auto px-12 py-10 max-sm:px-4">
      <Illustration scene="hero" focus="70% 40%" isEager className="absolute inset-0 -z-10" />
      <div className="absolute inset-0 -z-10 bg-gradient-to-r from-window/55 via-window/10 to-transparent" />
      <section className="w-full max-w-[460px] rounded-[28px] border border-[light-dark(rgb(255_255_255/0.5),rgb(255_255_255/0.08))] bg-card/75 p-8 shadow-window backdrop-blur-2xl backdrop-saturate-150 max-sm:p-6">
        <div className="flex flex-col gap-3">
          <span className="flex size-11 items-center justify-center rounded-tile bg-ink text-window">
            <BeaconLogo size={24} />
          </span>
          <h1 className="mt-2 text-page font-semibold tracking-tight">Which team are you on?</h1>
          <p className="text-body text-ink-2">
            {PRODUCT_NAME} shows the alerts, approvals and runbooks of your team. You can switch any
            time from the sidebar.
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
          <ul className="mt-6 flex flex-col gap-2">
            {isLoading
              ? [0, 1, 2, 3].map((index) => (
                  <li key={index}>
                    <Skeleton className="h-[68px] rounded-tile" />
                  </li>
                ))
              : teams.map((team) => (
                  <li key={team.id}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelect(team.id);
                      }}
                      className="group flex w-full items-center gap-4 rounded-tile px-3 py-3 text-left transition-colors hover:bg-card"
                    >
                      <Avatar name={team.display_name} team={team.id} size="lg" />
                      <span className="flex min-w-0 flex-1 flex-col">
                        <span className="text-row font-semibold">
                          {teamShortName(team.display_name)}
                        </span>
                        <span className="truncate text-meta text-ink-2">{teamBlurb(team.id)}</span>
                      </span>
                      <span className="text-ink-3 transition-transform group-hover:translate-x-0.5">
                        <Icon name="chevronRight" size={18} />
                      </span>
                    </button>
                  </li>
                ))}
          </ul>
        )}
      </section>
    </main>
  );
}
