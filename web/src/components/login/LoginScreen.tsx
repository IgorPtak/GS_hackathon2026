import type { Recipient, Team } from "../../api/types";
import { PRODUCT_NAME } from "../../lib/brand";
import { teamShortName } from "../../lib/teams";
import { Avatar } from "../ui/Avatar";
import { BeaconLogo } from "../ui/BeaconLogo";
import { Button } from "../ui/Button";
import { EmptyState } from "../ui/EmptyState";
import { Icon } from "../ui/icons";
import { Skeleton } from "../ui/Skeleton";
import { AsciiSky } from "./AsciiSky";

interface LoginScreenProps {
  readonly teams: readonly Team[];
  readonly people: readonly Recipient[];
  readonly isLoading: boolean;
  readonly error: string | null;
  readonly onRetry: () => void;
  readonly onSignIn: (personId: string, teamId: string) => void;
}

function teamName(teams: readonly Team[], teamId: string | undefined): string {
  const team = teams.find((candidate) => candidate.id === teamId);
  return team ? teamShortName(team.display_name) : (teamId ?? "No team");
}

/**
 * Sign-in for the demo: pick who you are, and Beacon opens your team. There is no password on
 * purpose (CLAUDE.md decision 10); in production this is where single sign-on would go.
 */
export function LoginScreen({
  teams,
  people,
  isLoading,
  error,
  onRetry,
  onSignIn,
}: LoginScreenProps) {
  const members = people.filter((person) => (person.teams ?? []).length > 0);
  return (
    <main className="relative isolate flex min-w-0 flex-1 items-center overflow-y-auto bg-window px-16 py-10 max-sm:px-4">
      <AsciiSky />
      <section className="w-full max-w-[440px] rounded-[28px] border border-[light-dark(rgb(0_0_0/0.06),rgb(255_255_255/0.08))] bg-card/70 p-8 shadow-window backdrop-blur-2xl backdrop-saturate-150 max-sm:p-6">
        <span className="flex size-11 items-center justify-center rounded-tile bg-ink text-window">
          <BeaconLogo size={24} />
        </span>
        <h1 className="mt-5 text-page font-semibold tracking-tight">Sign in to {PRODUCT_NAME}</h1>
        <p className="mt-2 text-body text-ink-2">
          Choose who you are. You will see your team&apos;s alerts, approvals and runbooks.
        </p>
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
          <ul className="mt-6 flex flex-col gap-1">
            {isLoading
              ? [0, 1, 2, 3].map((index) => (
                  <li key={index}>
                    <Skeleton className="h-[60px] rounded-tile" />
                  </li>
                ))
              : members.map((person) => {
                  const teamId = person.teams?.[0];
                  return (
                    <li key={person.id}>
                      <button
                        type="button"
                        onClick={() => {
                          if (teamId) onSignIn(person.id, teamId);
                        }}
                        className="group flex w-full items-center gap-4 rounded-tile px-3 py-2.5 text-left transition-colors hover:bg-fill"
                      >
                        <Avatar name={person.display_name} team={teamId} size="lg" />
                        <span className="flex min-w-0 flex-1 flex-col">
                          <span className="text-row font-semibold">{person.display_name}</span>
                          <span className="truncate text-meta text-ink-2">
                            {teamName(teams, teamId)}
                          </span>
                        </span>
                        <span className="text-ink-3 transition-transform group-hover:translate-x-0.5">
                          <Icon name="chevronRight" size={18} />
                        </span>
                      </button>
                    </li>
                  );
                })}
          </ul>
        )}
        <p className="mt-6 text-caption text-ink-3">
          Demo sign-in without a password. Production would use your company single sign-on.
        </p>
      </section>
    </main>
  );
}
