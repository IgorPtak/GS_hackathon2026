# Delegation brief template

Fill every field from the task in `docs/IMPLEMENTATION_PLAN.md`. Keep "Context to read" minimal:
exact files and sections, never "read the docs".

```
Task: <ID> <title>
Goal: <one sentence, observable outcome>
Context to read: <exact files/sections, keep it minimal>
Contracts: <contract files this must conform to>
Files you may change: <list>
Do not: <explicit exclusions, e.g. change contracts, add dependencies>
Acceptance criteria: <copied from the plan>
Verify with: <commands>
Return: task ID, files changed, commands + results, open issues, DONE | BLOCKED: <reason>
```

## Example

```
Task: A-08 Evaluate conditions, resolve field paths, render templates
Goal: alerting_core can decide whether a rule's condition matches an event and render its title.
Context to read: contracts/alerting_contracts/config.py (Condition*, Presentation),
  contracts/alerting_contracts/events.py (NormalizedFields), contracts/README.md "Conventions",
  docs/glossary.md rows "condition", "operator", "field path", "template".
Contracts: contracts/alerting_contracts/config.py, events.py
Files you may change: packages/alerting_core/alerting_core/rules/{__init__,conditions,field_paths}.py,
  packages/alerting_core/alerting_core/templating.py, packages/alerting_core/tests/rules/**,
  packages/alerting_core/tests/test_templating.py, docs/CHANGELOG.md (one line)
Do not: change contracts, add dependencies, touch services/ or plugins/.
Acceptance criteria: <copy the A-08 bullet from the plan>
Verify with: uv run pytest packages/alerting_core/tests/rules packages/alerting_core/tests/test_templating.py -q
  && uv run ruff check packages/alerting_core && uv run ruff format --check packages/alerting_core
Return: task ID, files changed, commands + results, open issues, DONE | BLOCKED: <reason>
```
