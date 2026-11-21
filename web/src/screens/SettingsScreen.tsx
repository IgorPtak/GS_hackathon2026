import { AiAssistantCard } from "../components/settings/AiAssistantCard";
import { Avatar } from "../components/ui/Avatar";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { PageFrame } from "../components/ui/PageFrame";
import { Segmented } from "../components/ui/Segmented";
import { PRODUCT_NAME } from "../lib/brand";
import { isThemeValue } from "../lib/theme";
import { teamShortName } from "../lib/teams";
import { useTheme } from "../lib/useTheme";
import type { ScreenProps } from "./types";

const THEMES = [
  { value: "system", label: "Automatic" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

const LINKS = [
  { label: "API reference", href: "http://localhost:8000/docs" },
  { label: "Grafana dashboards", href: "http://localhost:3000" },
  { label: "Demo mailbox (Mailpit)", href: "http://localhost:8025" },
];

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-4">
      <div>
        <h2 className="text-row font-semibold">{title}</h2>
        <p className="text-meta text-ink-2">{hint}</p>
      </div>
      {children}
    </Card>
  );
}

/** Settings: AI assistant, appearance, account and where to look deeper. */
export function SettingsScreen({
  teamId,
  teamLabel,
  person,
  teams,
  onSelectTeam,
  onSignOut,
}: ScreenProps) {
  const { theme, chooseTheme } = useTheme();
  const myTeams = teams.filter((team) => person?.teams?.includes(team.id) ?? true);
  return (
    <PageFrame title="Settings" context={teamLabel} isNarrow>
      <div className="flex flex-col gap-6">
        <AiAssistantCard />
        <Section title="Appearance" hint="Automatic follows your system setting.">
          <div>
            <Segmented
              label="Appearance"
              options={THEMES}
              value={theme}
              onChange={(value) => {
                if (isThemeValue(value)) chooseTheme(value);
              }}
            />
          </div>
        </Section>
        <Section title="Account" hint="Who you are and which team you are looking at.">
          <div className="flex items-center gap-4">
            <Avatar name={person?.display_name ?? teamLabel} team={teamId} size="lg" />
            <div className="min-w-0 flex-1">
              <p className="text-row font-semibold">{person?.display_name ?? "Guest"}</p>
              <p className="text-meta text-ink-2">{teamLabel}</p>
            </div>
            <Button onClick={onSignOut}>Sign out</Button>
          </div>
          {myTeams.length > 1 ? (
            <div>
              <Segmented
                label="Team"
                options={myTeams.map((team) => ({
                  value: team.id,
                  label: teamShortName(team.display_name),
                }))}
                value={teamId}
                onChange={onSelectTeam}
              />
            </div>
          ) : null}
        </Section>
        <Section
          title={`About ${PRODUCT_NAME}`}
          hint="For engineers who want to look under the hood."
        >
          <ul className="flex flex-col divide-y divide-hairline">
            {LINKS.map((link) => (
              <li key={link.href}>
                <a
                  href={link.href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-between py-3 text-body hover:text-accent-ink"
                >
                  {link.label}
                  <span className="text-meta text-ink-3">{new URL(link.href).host}</span>
                </a>
              </li>
            ))}
          </ul>
        </Section>
      </div>
    </PageFrame>
  );
}
