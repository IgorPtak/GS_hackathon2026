import { useId, useRef } from "react";

import type { Team } from "../../api/types";
import { teamShortName } from "../../lib/teams";
import { Avatar } from "../ui/Avatar";
import { Icon } from "../ui/icons";
import { Tooltip } from "../ui/Tooltip";

interface TeamSwitcherProps {
  readonly teams: readonly Team[];
  readonly selectedTeamId: string;
  readonly onSelect: (teamId: string) => void;
}

/** Current-team avatar that opens a popover list of teams (native Popover API). */
export function TeamSwitcher({ teams, selectedTeamId, onSelect }: TeamSwitcherProps) {
  const popoverId = useId();
  const popoverRef = useRef<HTMLDivElement>(null);
  const selected = teams.find((team) => team.id === selectedTeamId);
  const name = selected ? teamShortName(selected.display_name) : selectedTeamId;

  return (
    <>
      <Tooltip label={`Team: ${name}`}>
        <button
          type="button"
          popoverTarget={popoverId}
          aria-label={`Team ${name}. Switch team`}
          className="rounded-full"
        >
          <Avatar name={name} team={selectedTeamId} size="lg" />
        </button>
      </Tooltip>
      <div
        ref={popoverRef}
        id={popoverId}
        popover="auto"
        style={{ inset: "auto auto 20px 80px", margin: 0 }}
        className="w-64 rounded-card border border-hairline bg-card p-2 text-ink shadow-window"
      >
        <p className="px-3 pt-2 pb-1 text-meta text-ink-2">Switch team</p>
        <ul>
          {teams.map((team) => (
            <li key={team.id}>
              <button
                type="button"
                onClick={() => {
                  onSelect(team.id);
                  popoverRef.current?.hidePopover();
                }}
                className="flex w-full items-center gap-3 rounded-tile px-3 py-2 text-left text-body font-medium hover:bg-fill"
              >
                <Avatar name={team.display_name} team={team.id} size="sm" />
                <span className="flex-1">{teamShortName(team.display_name)}</span>
                {team.id === selectedTeamId ? (
                  <Icon name="check" size={16} className="text-accent-ink" />
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </>
  );
}
