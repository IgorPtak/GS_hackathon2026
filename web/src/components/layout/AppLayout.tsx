import { useState } from "react";

import { RecentEventsPanel } from "../events/RecentEventsPanel";
import { PlaceholderPage } from "../../pages/PlaceholderPage";
import { readStoredTeamId, writeStoredTeamId } from "../../lib/teamStorage";
import { TABS, type TabId } from "../../lib/tabs";
import { TeamPicker } from "../team/TeamPicker";
import { TabNav } from "./TabNav";

export function AppLayout() {
  const [selectedTeamId, setSelectedTeamId] = useState<string | null>(() => readStoredTeamId());
  const [activeTabId, setActiveTabId] = useState<TabId>("alerts");
  const activeTab = TABS.find((tab) => tab.id === activeTabId);

  function handleTeamSelect(teamId: string) {
    setSelectedTeamId(teamId);
    writeStoredTeamId(teamId);
  }

  return (
    <div className="flex min-h-screen flex-col bg-slate-50 text-slate-900">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-3">
        <h1 className="text-lg font-semibold">Alerting console</h1>
        <TeamPicker selectedTeamId={selectedTeamId} onSelect={handleTeamSelect} />
      </header>
      <TabNav tabs={TABS} activeTabId={activeTabId} onSelect={setActiveTabId} />
      <main className="flex-1 p-6">
        {activeTab && activeTabId !== "schemas" ? (
          <PlaceholderPage title={activeTab.label} teamId={selectedTeamId} />
        ) : null}
        {activeTabId === "alerts" || activeTabId === "schemas" ? (
          <div className="mt-6">
            <RecentEventsPanel />
          </div>
        ) : null}
      </main>
    </div>
  );
}
