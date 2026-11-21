# plugins/sources

Source plugins: base interface, registry, one file per source type.

Owner: track A. Tasks: A-04, A-06. See `docs/IMPLEMENTATION_PLAN.md`.

## Add an HTTP source (one file + config)

Create `plugins/sources/my_source.py`, import it in `__init__.py`, add `config/sources/<id>.yaml`:

```python
class MySource(HttpSourcePlugin):
    def extract_payloads(self, body, source):
        return list(body.get("items", []))  # one payload per event


register_source_plugin(SourceType.alertmanager, MySource())
```

A new source of an existing type = YAML only: ingest reads sources from the config registry and
applies `config/sources/<id>.yaml` changes on `config.changed` (no restart). A deleted or disabled
source answers 404; `log_tail` tasks start, stop or (for an edited source only) restart on reload.

## Alertmanager

`alertmanager.py` splits `alerts[]` into one event per alert (item `status` wins, `receiver` and
`groupKey` copied in). Override `idempotency_key(payload, source)` to dedupe re-sends when the
request has no `Idempotency-Key` header and no `idempotency_key_path`.

## Log tail (not HTTP)

`log_tail.py` is a `LogTailRunner` that ingest starts as a background task for every enabled
`log_tail` source. Settings: `path`, `line_format` (`json` | `regex`), `line_pattern` (named
groups), `start_at` (`end` | `beginning`, only without a stored offset). Payload = named groups
(strings) + `raw_line`. Lines that fail to parse go to stream `events-dlq` with the raw line.
Only one ingest worker tails a file (Redis lock `log-tail-lock:<source_id>`); the offset lives in
`log-tail-offset:<source_id>` (`inode:offset`). Rotation and truncation are detected by inode change
or size shrink. The compose `ingest` service mounts `./data/logs` at `/var/log/pricing`.
