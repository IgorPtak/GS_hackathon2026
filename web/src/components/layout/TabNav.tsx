import type { TabDefinition, TabId } from "../../lib/tabs";

interface TabNavProps {
  tabs: readonly TabDefinition[];
  activeTabId: TabId;
  onSelect: (tabId: TabId) => void;
}

/** Horizontal tab bar; the active tab is exposed through aria-current. */
export function TabNav({ tabs, activeTabId, onSelect }: TabNavProps) {
  return (
    <nav aria-label="Sections" className="border-b border-slate-200 bg-white px-6">
      <ul className="flex gap-1 overflow-x-auto">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <li key={tab.id}>
              <button
                type="button"
                aria-current={isActive ? "page" : undefined}
                onClick={() => {
                  onSelect(tab.id);
                }}
                className={
                  isActive
                    ? "border-b-2 border-slate-900 px-3 py-2 text-sm font-semibold text-slate-900"
                    : "border-b-2 border-transparent px-3 py-2 text-sm text-slate-600 hover:text-slate-900"
                }
              >
                {tab.label}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
