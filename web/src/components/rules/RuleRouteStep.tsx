import type { ConfigLists } from "../../api/types";
import { teamShortName } from "../../lib/teams";
import { channelWord } from "../recipients/preferenceSentence";
import { MultiSelect } from "../ui/MultiSelect";
import { RulePresentFields } from "./RulePresentFields";
import { RuleRunbookPicker } from "./RuleRunbookPicker";
import { parseRouteFromRuleYaml, replaceRouteInRuleYaml, type RouteDraft } from "./routeYaml";

interface RuleRouteStepProps {
  readonly yaml: string;
  readonly ownerTeam: string;
  readonly config: ConfigLists | null;
  readonly onChange: (nextYaml: string) => void;
}

const list = new Intl.ListFormat("en", { style: "long", type: "conjunction" });

function withCurrent(options: { value: string; label: string }[], current: readonly string[]) {
  const missing = current.filter((id) => !options.some((o) => o.value === id));
  return [...options, ...missing.map((id) => ({ value: id, label: id }))];
}

/** One sentence that says who is told and how, read from the route. */
function routeSentence(route: RouteDraft, ownerTeam: string, names: Map<string, string>): string {
  const teams = route.teams.length > 0 ? route.teams : [ownerTeam];
  const who = [
    `the on-call people of ${list.format(teams.map((t) => names.get(t) ?? t))}`,
    ...route.recipients.map((id) => names.get(id) ?? id),
  ];
  const how =
    route.channels.length > 0 ? list.format(route.channels.map(channelWord)) : "no channel";
  return `Alerts go to ${list.format(who)}. Each person is reached the way their own channel preferences say. If none match, by ${how}.`;
}

/** Step 2: people and channels (`route:`), how the alert reads (`present:`) and its runbook. */
export function RuleRouteStep({ yaml, ownerTeam, config, onChange }: RuleRouteStepProps) {
  const route = parseRouteFromRuleYaml(yaml);
  if (route === null) {
    return (
      <p className="rounded-tile bg-fill px-4 py-3 text-body text-ink-2">
        This rule's route has a layout the form cannot edit safely. Open Advanced (YAML) below to
        change it.
      </p>
    );
  }
  const names = new Map<string, string>([
    ...(config?.teams ?? []).map((t) => [t.id, teamShortName(t.display_name)] as const),
    ...(config?.recipients ?? []).map((r) => [r.id, r.display_name] as const),
  ]);
  const write = (patch: Partial<RouteDraft>) => {
    onChange(replaceRouteInRuleYaml(yaml, { ...route, ...patch }));
  };
  const teamOptions = (config?.teams ?? []).map((t) => ({
    value: t.id,
    label: teamShortName(t.display_name),
  }));
  const personOptions = (config?.recipients ?? []).map((r) => ({
    value: r.id,
    label: r.display_name,
  }));
  const channelOptions = (config?.channels ?? []).map((c) => ({
    value: c.id,
    label: channelWord(c.id),
  }));

  return (
    <div className="space-y-6">
      <p className="text-body text-ink-2">{routeSentence(route, ownerTeam, names)}</p>
      <div className="space-y-2">
        <h4 className="text-body font-semibold">Teams on call</h4>
        <p className="text-meta text-ink-2">Leave empty to alert this rule's own team.</p>
        <MultiSelect
          label="Teams on call"
          options={withCurrent(teamOptions, route.teams)}
          values={route.teams}
          onChange={(teams) => {
            write({ teams });
          }}
        />
      </div>
      <div className="space-y-2">
        <h4 className="text-body font-semibold">Also tell these people</h4>
        <MultiSelect
          label="People"
          options={withCurrent(personOptions, route.recipients)}
          values={route.recipients}
          onChange={(recipients) => {
            write({ recipients });
          }}
        />
      </div>
      <div className="space-y-2">
        <h4 className="text-body font-semibold">Default channels</h4>
        <p className="text-meta text-ink-2">
          Used for a person whose own preferences do not match. Edit those under People &amp;
          channels.
        </p>
        <MultiSelect
          label="Default channels"
          options={withCurrent(channelOptions, route.channels)}
          values={route.channels}
          onChange={(channels) => {
            write({ channels });
          }}
        />
      </div>
      <RulePresentFields yaml={yaml} onChange={onChange} />
      <RuleRunbookPicker yaml={yaml} ownerTeam={ownerTeam} onChange={onChange} />
    </div>
  );
}
