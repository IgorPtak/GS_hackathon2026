import { useEffect, useState } from "react";

import { apiClient } from "../../api/client";
import type { Team } from "../../api/types";

interface TeamPickerProps {
  selectedTeamId: string | null;
  onSelect: (teamId: string) => void;
}

/** Lists the teams from GET /api/v1/config. The parent owns the selection and its storage. */
export function TeamPicker({ selectedTeamId, onSelect }: TeamPickerProps) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let isCancelled = false;

    async function loadTeams() {
      try {
        const { data } = await apiClient.GET("/api/v1/config");
        if (isCancelled) {
          return;
        }
        if (data) {
          setTeams(data.teams);
        } else {
          setLoadError("Could not load teams");
        }
      } catch {
        if (!isCancelled) {
          setLoadError("Could not load teams");
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadTeams();
    return () => {
      isCancelled = true;
    };
  }, []);

  const placeholderLabel = isLoading ? "Loading teams..." : (loadError ?? "Select a team");

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="font-medium text-slate-700">Team</span>
      <select
        className="rounded-md border border-slate-300 bg-white px-2 py-1"
        value={selectedTeamId ?? ""}
        disabled={isLoading || loadError !== null}
        onChange={(event) => {
          onSelect(event.target.value);
        }}
      >
        <option value="" disabled>
          {placeholderLabel}
        </option>
        {teams.map((team) => (
          <option key={team.id} value={team.id}>
            {`${team.display_name} (${team.id})`}
          </option>
        ))}
      </select>
    </label>
  );
}
