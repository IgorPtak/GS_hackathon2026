# plugins/runbook_formats

Runbook format normalizers: yaml, markdown, text.

Owner: track B. Tasks: B-06, B-09. See `docs/IMPLEMENTATION_PLAN.md`.

Normalizing: `alerting_core.runbooks.normalize_runbook(id, title, team, format, source, actions)`.
Runbooks are the `runbook` config kind (`config/runbooks/<id>.yaml|.md|.txt`, id = file stem),
registered by `register_runbook_kind()`; actions are read from the sibling `config/actions/`.
Markdown keyword table (phrase -> action id): `KEYWORD_ACTIONS` in `markdown_format.py`.
Text runbooks are normalized by the LLM only when saved (`PUT /api/v1/runbooks/{id}`, via
`alerting_core.runbooks.normalize_runbook_with_llm`): the output is validated by
`validate_llm_steps` (unknown actions become text steps, approval-required actions always need
approval) and stored with `normalized_by: llm` and `llm_model`. Loaders, the `/normalize` preview and
an unavailable LLM give the fallback: one text step with the whole source (`normalized_by: fallback`).

## Add a runbook format in one file

`plugins/runbook_formats/csv_format.py`, plus one import line in `__init__.py`
(and a value in `RunbookFormat` in the contracts):

```python
@register_runbook_format
class CsvRunbookFormat(RunbookFormatPlugin):
    format = RunbookFormat.csv

    def normalize(self, source, actions):
        rows = [r for r in source.splitlines() if r.strip()]
        return [RunbookStep(index=i, kind=StepKind.text, text=r) for i, r in enumerate(rows)]
```

Raise `ValueError` for input with no steps and `ValidationError` for invalid structure.
