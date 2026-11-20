# plugins/channels

Channel plugins: base interface, registry, one file per channel type (`ui`, `email`; A-15 adds sms/phone/webhook).

Owner: track A. Tasks: A-12, A-15. See `docs/IMPLEMENTATION_PLAN.md`.

## Add a new channel in under ten lines

Create `plugins/channels/<type>.py`, add the type to `ChannelType` if new, and import the module in `__init__.py`:

```python
class SlackChannel(ChannelPlugin):
    channel_type = ChannelType.webhook

    async def send(self, job, recipient, config, context) -> None:
        response = await context.http.post(config.settings["url"], json={"text": job.content.title})
        if response.status_code >= 500:
            raise ChannelUnavailableError(f"http {response.status_code}")  # retryable
        if response.status_code >= 400:
            raise ChannelRejectedError(f"http {response.status_code}")  # permanent


register_channel_plugin(SlackChannel())
```

Plugins only format and send `job.content`; retries, status, fallback and circuit breaking belong to the delivery worker.
`ChannelContext` carries `redis`, `http`, `settings` and (optionally) the `database` pool.
