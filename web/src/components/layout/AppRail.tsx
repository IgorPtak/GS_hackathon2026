import type { Team } from "../../api/types";
import { PRODUCT_NAME } from "../../lib/brand";
import { EXTRA_PAGES, GROUP_STARTS, TABS, type TabDefinition, type TabId } from "../../lib/tabs";
import { TeamSwitcher } from "../team/TeamSwitcher";
import { BeaconLogo } from "../ui/BeaconLogo";
import type { IconName } from "../ui/icons";
import { Rail, RailDivider } from "../ui/Rail";
import { RailItem } from "../ui/RailItem";
import { ApprovalsRailItem } from "./ApprovalsRailItem";

const [HOME, SETTINGS] = EXTRA_PAGES as readonly [TabDefinition, TabDefinition];

const TAB_ICONS: Record<TabId, IconName> = {
  home: "home",
  settings: "settings",
  inbox: "inbox",
  approvals: "approval",
  phone: "phone",
  rules: "rules",
  connect: "connect",
  runbooks: "runbook",
  people: "people",
  insights: "insights",
};

interface AppRailProps {
  readonly activeTabId: TabId;
  readonly teams: readonly Team[];
  readonly teamId: string;
  readonly onNavigate: (tab: TabDefinition) => void;
  readonly onSelectTeam: (teamId: string) => void;
}

/** The shell rail: logo tile, page links, then appearance toggle and team switcher. */
export function AppRail({ activeTabId, teams, teamId, onNavigate, onSelectTeam }: AppRailProps) {
  return (
    <Rail
      logo={
        <a
          href="/home"
          aria-label={`${PRODUCT_NAME} home`}
          aria-current={activeTabId === "home" ? "page" : undefined}
          onClick={(event) => {
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
            event.preventDefault();
            onNavigate(HOME);
          }}
          className="flex size-11 shrink-0 items-center justify-center rounded-tile bg-ink text-window transition-transform hover:scale-[1.04]"
        >
          <BeaconLogo size={24} />
        </a>
      }
      footer={
        <>
          <RailItem
            label="Settings"
            icon="settings"
            href={SETTINGS.path}
            isActive={activeTabId === "settings"}
            onSelect={() => {
              onNavigate(SETTINGS);
            }}
          />
          <TeamSwitcher teams={teams} selectedTeamId={teamId} onSelect={onSelectTeam} />
        </>
      }
    >
      {TABS.map((tab) => {
        const select = () => {
          onNavigate(tab);
        };
        return (
          <div key={tab.id} className="flex flex-col items-center gap-1">
            {GROUP_STARTS.includes(tab.id) ? <RailDivider /> : null}
            {tab.id === "approvals" ? (
              <ApprovalsRailItem
                team={teamId}
                href={tab.path}
                isActive={tab.id === activeTabId}
                onSelect={select}
              />
            ) : (
              <RailItem
                label={tab.label}
                icon={TAB_ICONS[tab.id]}
                href={tab.path}
                isActive={tab.id === activeTabId}
                onSelect={select}
              />
            )}
          </div>
        );
      })}
    </Rail>
  );
}
