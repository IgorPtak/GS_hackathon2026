# plugins/runbook_formats

Runbook format normalizer plugins (`yaml`, `markdown`, `text`) that convert a runbook's original source text into normalized `list[RunbookStep]`.

## Add a new runbook format in under ten lines

Create `plugins/runbook_formats/csv_format.py` (8 lines for the plugin class):

```python
from collections.abc import Mapping

from alerting_contracts.config import ActionConfig
from alerting_contracts.runbooks import RunbookFormat, RunbookStep, StepKind

from plugins.runbook_formats.base import RunbookFormatPlugin
from plugins.runbook_formats.registry import register_runbook_format

@register_runbook_format
class CsvRunbookFormat(RunbookFormatPlugin):
    format = RunbookFormat.csv

    def normalize(self, source: str, actions: Mapping[str, ActionConfig]) -> list[RunbookStep]:
        rows = [r.strip() for r in source.splitlines() if r.strip()]
        if not rows:
            raise ValueError("runbook has no steps")
        return [RunbookStep(index=i, kind=StepKind.text, text=r) for i, r in enumerate(rows)]
```

Then wire the new format in three places:

1. **Contracts enum** (`contracts/alerting_contracts/runbooks.py`): add `csv = "csv"` to `RunbookFormat`. Because `RunbookFormat` is a `StrEnum`, both contract models (`Runbook`, `RunbookWrite`, `RunbookNormalizeRequest`) and `get_runbook_format()` reject any format name not defined on `RunbookFormat`.
2. **Package import** (`plugins/runbook_formats/__init__.py`): import `csv_format` alongside `markdown_format`, `text_format`, `yaml_format` so importing `plugins.runbook_formats` runs `@register_runbook_format`. Import `RunbookFormatPlugin` from `plugins.runbook_formats.base` and `register_runbook_format` from `plugins.runbook_formats.registry` (not from `plugins.runbook_formats`) to avoid a circular import.
3. **File suffix registration** (`packages/alerting_core/alerting_core/runbooks/store.py`): add `".csv": RunbookFormat.csv` to `_FORMAT_BY_SUFFIX` so `load_runbook_file()` and `register_runbook_kind()` load `config/runbooks/<id>.csv` files automatically.

### Config snippet: using the runbook format

Place a runbook file in `config/runbooks/` where the file stem is the runbook `id` (for example, `config/runbooks/stale-cache.csv`):

```text
Verify cache status for {{service}}
Flush stale entries on {{service}}
Confirm fresh reads before resolving the alert
```

Attach the runbook to a rule in `config/rules/<rule_id>.yaml` using its `id`:

```yaml
id: cache-stale
team: platform
when:
  all:
    - { field: eventType, op: eq, value: CACHE_STALE }
route: { channels: [ui, email] }
present:
  title: "Cache stale on {{service}}"
runbook: stale-cache
```

You can also normalize or save the same format through the API (`POST /api/v1/runbooks/normalize` or `PUT /api/v1/runbooks/{runbook_id}`) with `"format": "csv"`.

## Plugin contract and registry

Base class (`plugins/runbook_formats/base.py`):

```python
class RunbookFormatPlugin(abc.ABC):
    format: RunbookFormat

    @abc.abstractmethod
    def normalize(self, source: str, actions: Mapping[str, ActionConfig]) -> list[RunbookStep]:
        """Return the normalized steps for ``source``."""
```

Registry (`plugins/runbook_formats/registry.py`):

- `@register_runbook_format`: class decorator registering a `RunbookFormatPlugin` subclass under `cls.format`.
- `get_runbook_format(format: RunbookFormat | str) -> RunbookFormatPlugin`: instantiates the registered plugin for `format`, or raises `UnknownRunbookFormatError` (`KeyError` subclass) if the format is invalid or unregistered.
- `registered_formats() -> list[str]`: returns the sorted list of registered runbook format names.

Implementation rules enforced by the contract:

- `normalize` must be pure: no network calls and no file access.
- Raise `pydantic.ValidationError` (with a field path) for structurally invalid input, and `ValueError` when `source` produces no steps.
- `actions` maps action `id` to `ActionConfig`; plugins may only reference action ids present in `actions`.
- Leave `RunbookStep.approval` as `None` unless the source explicitly specifies it, so the runbook step inherits the action's default approval policy.
- Keep `{{placeholders}}` untouched in `text` and `params`; templates are rendered per alert later into a `RenderedRunbook`.

## Built-in formats

| Format | Module | Plugin class | File extensions | `normalized_by` | Example in `config/runbooks/` |
|---|---|---|---|---|---|
| `yaml` | `yaml_format.py` | `YamlRunbookFormat` | `.yaml`, `.yml` | `parser` | `workflow-failed.yaml` |
| `markdown` | `markdown_format.py` | `MarkdownRunbookFormat` | `.md` | `parser` | `trade-limit-breach.md` |
| `text` | `text_format.py` | `TextRunbookFormat` | `.txt` | `fallback` (or `llm` on save) | `pricing-stale-feed.txt` |

- **`yaml`** (`yaml_format.py`): parses and validates `RunbookYamlDocument` (`contracts/schemas/config.RunbookYamlDocument.schema.json`) via `parse_yaml_document(source)`. Step indexes must be `0..n-1` in order (`ValidationError` on mismatch). When loaded from `config/runbooks/<id>.yaml`, the document `id` must match the file stem.
- **`markdown`** (`markdown_format.py`): headings (`#`–`######`) become `StepKind.text` steps and numbered/bulleted list items become steps (indented continuation lines are joined onto the preceding item). The first heading becomes the runbook title via `heading_text(source)`. Non-heading items are matched against `KEYWORD_ACTIONS` (first match wins, only when the target action id exists in `actions`). A trailing inline code span names an action explicitly, e.g. `` `retry-workflow workflow_id={{workflowId}}` `` or `` `escalate workflow_id=1 reason="two words" approval=required` ``: underscores in the action id and camelCase keys map to the configured names, `approval=required|none` sets the policy, and prose "needs approval" also sets `required`. Params keep their `{{templates}}`. A detected action with missing required params becomes a manual `text` step. Markdown steps are never `is_automatic`.
- **`text`** (`text_format.py`): the pure plugin returns one `StepKind.text` step holding the stripped source (`normalized_by: "fallback"`), or delegates to an optional `llm_normalizer: LlmNormalizer | None` passed to `TextRunbookFormat.__init__`. In production, LLM normalization runs only when saving via `PUT /api/v1/runbooks/{runbook_id}` (calling `alerting_core.runbooks.normalize.normalize_runbook_with_llm`). The LLM output is post-validated by `validate_llm_steps(steps, actions)` — blank steps are dropped, unknown action ids become `StepKind.text` steps, actions with `ApprovalPolicy.required` have `approval` forced to `required` and `is_automatic` set to `False`, and indexes are renumbered `0..n-1` — then stored with `normalized_by: "llm"` and `llm_model`. File loaders, `POST /api/v1/runbooks/normalize`, a missing LLM client, or any `LlmError` fall back to one text step (`normalized_by: "fallback"`).

## Config loading and normalization entry points

- **Normalization**: `alerting_core.runbooks.normalize_runbook(id, title, team, format, source, actions)` calls `get_runbook_format(format).normalize(source, actions)` and returns a `Runbook` (`contracts/schemas/Runbook.schema.json`).
- **Config kind**: runbooks are the `runbook` config kind (`config/runbooks/<id>.yaml|.yml|.md|.txt`, `id` = file stem), registered by `alerting_core.runbooks.register_runbook_kind()`.
- **Actions lookup**: `load_runbook_file()` reads available actions from the sibling `config/actions/` directory; the API routes read them from `ConfigLists.actions`.
