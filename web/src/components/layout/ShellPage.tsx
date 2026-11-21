import { ApprovalsScreen } from "../../screens/ApprovalsScreen";
import { ConnectScreen } from "../../screens/ConnectScreen";
import { InboxScreen } from "../../screens/InboxScreen";
import { InsightsScreen } from "../../screens/InsightsScreen";
import { PeopleScreen } from "../../screens/PeopleScreen";
import { PhoneScreen } from "../../screens/PhoneScreen";
import { RulesScreen } from "../../screens/RulesScreen";
import { RunbooksScreen } from "../../screens/RunbooksScreen";
import type { ScreenProps } from "../../screens/types";
import type { TabId } from "../../lib/tabs";
import { DemoScreen } from "../../screens/DemoScreen";
import { HomeScreen } from "../../screens/HomeScreen";
import { SettingsScreen } from "../../screens/SettingsScreen";

/** Picks the screen for the active rail item. Each screen owns its header and body. */
export function ShellPage({ tabId, ...props }: ScreenProps & { readonly tabId: TabId }) {
  switch (tabId) {
    case "home":
      return <HomeScreen {...props} />;
    case "settings":
      return <SettingsScreen {...props} />;
    case "inbox":
      return <InboxScreen {...props} />;
    case "approvals":
      return <ApprovalsScreen {...props} />;
    case "phone":
      return <PhoneScreen {...props} />;
    case "rules":
      return <RulesScreen {...props} />;
    case "connect":
      return <ConnectScreen {...props} />;
    case "runbooks":
      return <RunbooksScreen {...props} />;
    case "people":
      return <PeopleScreen {...props} />;
    case "insights":
      return <InsightsScreen {...props} />;
  }
}

/** Renders the `/demo` route inside the shell window. */
export function DemoPlaceholder() {
  return <DemoScreen />;
}
