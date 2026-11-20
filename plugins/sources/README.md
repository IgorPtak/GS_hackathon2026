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
