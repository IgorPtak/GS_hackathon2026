import { useState } from "react";

import { PhonePage } from "../../pages/PhonePage";
import { readStoredTeamId, writeStoredTeamId } from "../../lib/teamStorage";
import { teamShortName } from "../../lib/teams";
import { pathForTab, useRoute } from "../../lib/useRoute";
import { useTheme } from "../../lib/useTheme";
import { FirstRunScreen } from "../team/FirstRunScreen";
import { useTeams } from "../team/useTeams";
import { ToastProvider } from "../ui/ToastProvider";
import { AppRail } from "./AppRail";
import { AppWindow } from "./AppWindow";
import { DemoSheet } from "../../screens/DemoScreen";
import { DemoPlaceholder, ShellPage } from "./ShellPage";

/** Routes between the shell (rail + page), the full-screen phone and the reserved demo panel. */
export function AppLayout() {
  const { route, navigate } = useRoute();
  const { theme, cycleTheme } = useTheme();
  const { teams, isLoading, error, reload } = useTeams();
  const [teamId, setTeamId] = useState<string | null>(() => readStoredTeamId());

  function selectTeam(next: string) {
    setTeamId(next);
    writeStoredTeamId(next);
  }

  if (route.kind === "phone") {
    return <PhoneFullScreen teamId={teamId} />;
  }

  return (
    <ToastProvider>
      <AppWindow>
        {route.kind === "demo" ? (
          <DemoPlaceholder />
        ) : teamId === null ? (
          <FirstRunScreen
            teams={teams}
            isLoading={isLoading}
            error={error}
            onRetry={reload}
            onSelect={selectTeam}
          />
        ) : (
          <>
            <AppRail
              activeTabId={route.tabId}
              teams={teams}
              teamId={teamId}
              theme={theme}
              onNavigate={(tab) => {
                navigate(tab.path);
              }}
              onCycleTheme={cycleTheme}
              onSelectTeam={selectTeam}
            />
            <div className="flex min-w-0 flex-1 flex-col">
              <ShellPage
                tabId={route.tabId}
                teamId={teamId}
                teamLabel={teamLabel(teams, teamId)}
                onNavigate={(tab) => {
                  navigate(pathForTab(tab));
                }}
              />
            </div>
            <DemoSheet
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
