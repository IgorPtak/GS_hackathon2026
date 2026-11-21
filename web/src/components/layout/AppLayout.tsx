import { useState } from "react";

import { PhonePage } from "../../pages/PhonePage";
import {
  readStoredPersonId,
  readStoredTeamId,
  writeStoredPersonId,
  writeStoredTeamId,
} from "../../lib/teamStorage";
import { teamShortName } from "../../lib/teams";
import { PageBackContext } from "../../lib/backContext";
import { ALL_PAGES } from "../../lib/tabs";
import { pathForTab, useRoute } from "../../lib/useRoute";
import { AsciiSky } from "../login/AsciiSky";
import { LoginScreen } from "../login/LoginScreen";
import { useTeams } from "../team/useTeams";
import { ToastProvider } from "../ui/ToastProvider";
import { AppRail } from "./AppRail";
import { AppWindow } from "./AppWindow";
import { TestConsole } from "../console/TestConsole";
import { DemoPlaceholder, ShellPage } from "./ShellPage";

/** Routes between the shell (rail + page), the full-screen phone and the reserved demo panel. */
export function AppLayout() {
  const { route, navigate } = useRoute();
  const { teams, people, isLoading, error, reload } = useTeams();
  const [teamId, setTeamId] = useState<string | null>(() => readStoredTeamId());
  const [personId, setPersonId] = useState<string | null>(() => readStoredPersonId());

  function selectTeam(next: string) {
    setTeamId(next);
    writeStoredTeamId(next);
  }
  function signIn(nextPerson: string, nextTeam: string) {
    setPersonId(nextPerson);
    writeStoredPersonId(nextPerson);
    selectTeam(nextTeam);
    navigate("/home");
  }
  function signOut() {
    setPersonId(null);
    setTeamId(null);
    writeStoredPersonId(null);
  }
  const person = people.find((candidate) => candidate.id === personId) ?? null;

  const pageBack =
    route.kind === "shell" && route.from !== null
      ? {
          onBack: () => {
            window.history.back();
          },
          label: `Back to ${labelForPath(route.from)}`,
        }
      : null;

  if (route.kind === "phone") {
    return <PhoneFullScreen teamId={teamId} />;
  }

  return (
    <ToastProvider>
      <AppWindow>
        {route.kind === "demo" ? (
          <DemoPlaceholder />
        ) : teamId === null || personId === null ? (
          <LoginScreen
            teams={teams}
            people={people}
            isLoading={isLoading}
            error={error}
            onRetry={reload}
            onSignIn={signIn}
          />
        ) : (
          <>
            <AppRail
              activeTabId={route.tabId}
              teams={teams}
              teamId={teamId}
              onNavigate={(tab) => {
                navigate(tab.path);
              }}
              onSelectTeam={selectTeam}
            />
            <PageBackContext.Provider value={pageBack}>
              <div className="relative isolate my-3 mr-3 flex min-w-0 flex-1 overflow-hidden rounded-[24px] border border-hairline bg-panel max-sm:m-0 max-sm:rounded-none max-sm:border-0">
                <AsciiSky tone="panel" />
                <div className="main-panel flex min-w-0 flex-1 flex-col">
                  <ShellPage
                    tabId={route.tabId}
                    teamId={teamId}
                    teamLabel={teamLabel(teams, teamId)}
                    onNavigate={(tab) => {
                      navigate(pathForTab(tab), { isDeepLink: true });
                    }}
                    person={person}
                    teams={teams}
                    onSelectTeam={selectTeam}
                    onSignOut={signOut}
                  />
                </div>
              </div>
            </PageBackContext.Provider>
            <TestConsole
              teamId={teamId}
              teamLabel={teamLabel(teams, teamId)}
              onNavigate={(tab) => {
                navigate(pathForTab(tab));
              }}
            />
          </>
        )}
      </AppWindow>
    </ToastProvider>
  );
}

function teamLabel(teams: readonly { id: string; display_name: string }[], teamId: string): string {
  const team = teams.find((candidate) => candidate.id === teamId);
  return team ? teamShortName(team.display_name) : teamId.charAt(0).toUpperCase() + teamId.slice(1);
}

/** `/phone`: only the simulator, full screen, for a real phone. */
function PhoneFullScreen({ teamId }: { teamId: string | null }) {
  return (
    <main className="min-h-dvh bg-canvas max-sm:bg-[#0e1424]">
      <PhonePage teamId={teamId} isFullScreen />
    </main>
  );
}

function labelForPath(path: string): string {
  return ALL_PAGES.find((page) => page.path === path)?.label.toLowerCase() ?? "the previous page";
}
