# 5-minute demo video: script, shot list and editing notes

The video is the main thing the judges score, across every category. This file says what to show,
what to say and how to cut it. Every click below is a label the current UI really shows. Terminal
equivalents for each step are in the appendix, for retakes and for live judging.

## What the video has to prove

| Judging criterion | Where it is proven | The one thing the viewer must remember |
|---|---|---|
| UX: fresh clone to working demo | Scene 1 | 3 commands, healthy in 18 s, first alert about 1 s after the event |
| UX: usable by someone new, rule editor | Scenes 1 and 2 | A welcome, a setup checklist, and a rule written as a form with a preview |
| Flexibility: new source, schema or rule | Scene 2 | An unseen event becomes alerts with no code and no restart |
| Runbooks, actions and human approval | Scene 3 | The runbook retries on its own, then the phone rings and reads a code |
| Channels, preferences and presentation | Scene 4 | Each rule shapes its alert; each person picks channels and hours |
| Propose a fix | Scene 4 | Anyone can suggest a change; the owning team approves it |
| Don't flood people; survive failure | Scene 5 | 500 events become 1 alert; SMS down means *Paused*, none lost |
| Scalability, throughput and latency | Scene 6 | 800 msg/s sustained, p99 about 1 s, 0 lost; scale out with one command |
| Innovation and AI safety | Scene 7 | Free text becomes steps; the AI only proposes; approvals cannot be removed |

## Before recording

1. **Stack on `main`, rebuilt and rehearsed, then reset.** The rehearsal creates alerts, so the reset
   comes last:

   ```bash
   git pull && docker compose up -d --build
   uv run python scripts/demo_rehearsal.py      # expect "9/9 scenes passed"
   uv run python scripts/reset_demo.py --seed   # clean slate + 1 alert per team + 1 approval
   ```

2. **Browser:** Chrome, a fresh profile or a guest window (no extensions, no bookmarks bar),
   window 1440×900 or larger, zoom 100%. Recording at 2560×1600 and exporting at 1080p keeps text
   sharp after zoom-ins.
3. **Theme:** record everything in one theme. Light reads best on projectors and in compressed
   video; dark looks more premium. Do not switch between scenes.
4. **Tabs, in this order:** Beacon http://localhost:5173 · Mailpit http://localhost:8025 · Grafana
   http://localhost:3000 (dashboard **Alerting**, last 15 minutes) · the architecture diagram
   `docs/diagrams/architecture.svg`.
5. **Sound:** turn the Mac volume up. Before Scene 3, click once anywhere on the page, because
   browsers only play audio after a click. In **Settings → Phone voice**, pick an English voice
   (Samantha or Daniel) and press **Test voice**.
6. **Quiet machine:** Do Not Disturb on, Docker Desktop notifications off, hide the Dock and the
   desktop icons.
7. **Who to sign in as:** Scene 3 needs **Piotr Nowak** (Settlements), because the test console
   shows the phone of the person signed in. Piotr gets calls and SMS at any hour. Anna's SMS only
   fire 08:00 to 20:00 Warsaw time, and no scene depends on it.
8. **Welcome:** a fresh window shows the welcome after sign-in, which is exactly what Scene 1
   needs. To see it again, use **Settings → Getting started → Show the welcome again**.

## Shot list and voiceover (5:00)

The voiceover is about 590 words: roughly 4:10 at a calm pace, which leaves room for pauses. Record the screen silently,
scene by scene, then record the voice over the edit. That is much easier than talking while
clicking. Text in *[brackets]* is an on-screen caption for the edit.

### Scene 0 · 0:00–0:20 · The problem

- **Screen:** the sign-in screen with the ASCII star. Slow push-in.
- **Voice:** "Every system throws errors, warnings and business events. Today they land in logs,
  dashboards and mailboxes. The right person finds out late, or gets so many alerts they stop
  reading. Beacon gets the right alert to the right person, on the channel they prefer, and helps
  them fix it."
- *[Beacon · flexible alerting and notification service]*

### Scene 1 · 0:20–0:50 · From a fresh clone to the first alert

- **Screen:**
  1. A terminal with the three commands (README Quickstart). Pre-record it and cut the wait.
     *[3 commands · healthy in 18 s]*
  2. Sign-in: click **Anna Kowalska**.
  3. Welcome: **Next** to "How an alert reaches you", hold one beat, **Next**, then **Send a test alert**.
  4. The Inbox opens and the alert appears. *[about 1 second]*
- **Voice:** "From a fresh clone it is three commands, and the whole stack is healthy in eighteen
  seconds. There is no password: you pick who you are. A short welcome shows how an alert reaches
  you: an event, a rule, one alert, the right person. One click sends a test alert, and here it is,
  about a second later."

### Scene 2 · 0:50–1:50 · A system we have never seen, and a rule, with no code

- **Screen:**
  1. Press **Shift + D** to open the test console, then click **Event from a new system**. Beacon
     opens **Connect a system**.
  2. **Pick a sample**: the payment event (`evt`, `lvl`, `svc`, `data.*`). **Check the mapping**:
     "Beacon suggests this mapping" (severity ← `lvl`, time ← `at`, repeats grouped by `evt` and
     `svc`). **Test and save**: "Matches your sample", then **Save mapping**.
  3. **Create a rule for it**, which opens Rules. Click **New rule**.
     - **When:** field `evt` · *matches the pattern* · `payment.declined*`. Add a condition: field
       `lvl` · *at least severity* · Warning.
     - **Who & how:** channels the app and email.
     - **Preview**, window *1 hour*: the sentence "In the last hour this rule would have created …
       alerts and sent … messages", plus who would have been messaged. *[nothing sent yet]*
     - Open **Advanced** for one second to show the same rule as YAML, then **Save rule**.
  4. In the console, click **Event from a new system** again. The alert lands in Anna's Inbox.
- **Voice:** "The judges will bring an event we have never seen, so let us do exactly that. This
  payment event comes from a system Beacon does not know. It lands in Connect a system. Beacon
  suggests which field is the severity, which is the time, and what makes two events the same, and
  checks the mapping against the sample. Now a rule. It is a form, not code: the event type matches
  'payment declined', at warning or above. It goes to the app and email. Before anything is live,
  Preview replays the last hour: how many alerts, and who would have been messaged. Under Advanced
  it is plain YAML, so it can live in Git. Save, and every worker reloads live. Nothing restarts.
  The next event is already an alert."

### Scene 3 · 1:50–2:50 · A runbook that acts, and a phone that asks first

- **Screen:**
  1. Sign out (avatar → **Settings → Sign out**), then sign in as **Piotr Nowak**. Click once on
     the page so sound can play.
  2. **Shift + D** → **Settlement workflow fails**. Keep the console open: the phone is on its
     right.
  3. The phone rings. **Answer**. It reads the alert, then "To approve, enter code: two, four…".
     Type the four digits on the keypad. Speed up the ringing in the edit, but keep the voice at 1×.
  4. Close the console, go to the **Inbox**, and open the workflow alert. Scroll slowly through
     **What happened** (the timeline from the event to the approval and the escalation), then
     through the **Runbook** steps with their outcomes.
- **Voice:** "Now something breaks for real: a settlement workflow fails. The team's runbook runs on
  its own. It checks the service health and retries the workflow twice. The retries fail, and the
  next step, escalation, is risky, so Beacon asks a human first. It calls Piotr, reads him the
  problem and a four-digit approval code, and he approves on the keypad. He could also reply to the
  SMS or click Approve in the app. Everything is recorded: what ran, what failed, who approved and
  how."

### Scene 4 · 2:50–3:35 · Every rule shapes its alert; every person picks their channels

- **Screen:**
  1. Sign out and sign in as **Anna** again. Console → **Rejected EUR 25M trade**. Open the alert: the title template "Rejected EUR 25M", the runbook filled with
     the trade id and counterparty, **Acknowledge** and **Resolve**.
  2. Switch to the Mailpit tab: the same alert as an email with the numbered runbook steps filled
     in. *[email: full steps · SMS: short link]*
  3. **People & channels**: Anna sends critical alerts by SMS and phone 08:00 to 20:00 Warsaw time,
     and email otherwise.
  4. Back on the alert: **Propose a fix** → **Draft with AI** fills a threshold change → **Send
     proposal**. Rehearse this step: Draft with AI needs the LLM endpoint from `.env`. Without it,
     pick the change by hand in the same dialog. Open **Approvals**: the change appears as a diff. **Accept**. The card shows
     "Accepted. The change is saved and live now", then folds away.
- **Voice:** "Each rule decides how its alert looks: the title, the fields, the colour. Its runbook
  arrives already filled in, in the app and by email. An SMS only carries a short link. Each person
  picks their own channels and hours. Anna gets an SMS and a call during working hours, and email
  after that. And when an alert is noisy, anyone can propose a fix. The AI can draft it, but it is
  only a proposal: the owning team sees the diff and accepts it, and it goes live without a
  restart."

### Scene 5 · 3:35–4:05 · Don't flood people, and never lose an alert

- **Screen:**
  1. Console → **500 identical events**. The Inbox shows one alert with **×500**.
     *[500 events → 1 alert]*
  2. Console → **Take SMS down**, then click **Settlement workflow fails** two or three times. Go
     to **Insights → Channels**. Within about 5 s, SMS shows **Paused** with "N waiting, none lost".
     After a single click it takes about 12 s.
  3. Console → **Bring SMS back**. Within about 10 s SMS is back to **Sending** with nothing waiting.
     *[0 lost]*
- **Voice:** "Five hundred identical errors in a minute are one alert with a counter, not five
  hundred messages. And when a channel goes down, here the SMS gateway, Beacon pauses it, keeps the
  messages, and keeps every other channel working. When SMS comes back, the queue drains. Nothing is
  lost."

### Scene 6 · 4:05–4:35 · Built to scale, measured

- **Screen:**
  1. The architecture diagram (`docs/diagrams/architecture.svg`), with a slow pan from ingest to
     channels.
  2. Grafana **Alerting** during a short run (`uv run python loadtest/scenarios.py steady
     --duration 60`), then the README load-test table.
     *[800 msg/s sustained · p99 ≈ 1.0 s · 0 lost]* *[steady 200 msg/s · p99 84 ms]*
  3. The scale command in a terminal:
     `docker compose up -d --scale processor=4 --scale delivery=4 --scale ingest=3 --scale api=2`.
     In Grafana, "msg/s processed by replica" gets one line per replica.
- **Voice:** "Under the hood, every worker is stateless. Events go through Redis Streams. Alerts and
  their deliveries are written in one Postgres transaction, so a crash cannot lose them. Dedup
  windows and delivery state live in Redis and Postgres, not in memory. We measured, not estimated:
  eight hundred messages a second sustained, p99 around one second, and zero lost in every test,
  including a gateway outage and killing workers mid-load. Scaling out is one command."

### Scene 7 · 4:35–5:00 · AI that helps, humans that decide

- **Screen:**
  1. **Runbooks** → *Stale price feed*: the original plain text next to the steps, the "Read by AI"
     chip, and the restart step marked as needing approval.
  2. Closing card: the repo link and the tagline.
     *[github.com/IgorPtak/GS_hackathon2026]*
- **Voice:** "Runbooks come as YAML, Markdown or plain sentences. The AI turns free text into steps
  once, when it is saved, never on the alert path. It cannot remove an approval, secrets are
  redacted before every call, and all demo data is synthetic. Beacon: teams change alerts without
  fear and without code, and the AI only proposes."

## Editing notes

- **Cut every wait.** Show the click, cut, then show the result. Speed up ringing, loading and the
  load test 4–8×, with a small "4×" badge. Keep speech and the phone's voice at 1×.
- **Zoom on what matters,** with a smooth 1.5–2× zoom: the ×500 badge, "Paused · 3 waiting, none
  lost", the preview sentence, the approval code on the phone, the Grafana p99 tile. Let the eye
  rest for about 1.5 s on each.
- **Captions carry the numbers** (18 s, about 1 s, ×500, 0 lost, 800 msg/s, p99). Judges may watch
  muted, so every claim in the voiceover also needs a caption.
- **Cursor:** use a larger cursor with a click highlight (Screen Studio, or the cursor size setting
  in macOS Accessibility). Move slowly and never hunt for a button on camera.
- **Chapters:** show a small chapter label in a corner for each scene (Setup · New system ·
  Runbook & phone · Channels & fixes · No flood, no loss · Scale · AI). This also helps judges
  score each category.
- **Audio:** record the voice with a headset or a lavalier mic in a quiet room. Music only under
  Scene 0 and the closing, at -25 dB. Duck the music under the phone's voice.
- **Length:** at most 5:00, including the title card. If a scene runs long, trim Scene 6 first; the
  README carries the numbers.
- **Export:** 1080p, H.264, 30 fps. Check that text is readable on a laptop at 100%.
- **Suggested tools:** Screen Studio or OBS for capture (OBS at 60 fps for smooth zooms); DaVinci
  Resolve, CapCut or iMovie for the cut.

## Retakes

- Test console scenarios make fresh ids on every click, including **500 identical events**, so
  retakes never merge into old alerts.
- Between full takes, run `uv run python scripts/reset_demo.py --seed`. It resolves open alerts,
  rejects pending approvals and fix proposals, clears Mailpit, makes the gateway healthy and seeds
  one alert per team.
- If SMS was left down, click **Bring SMS back** (or see the appendix).
- To see the welcome again, open a new window (sign-in is per tab session) or use **Settings →
  Show the welcome again**.

## Appendix: terminal equivalents

Use these for retakes, or to show the API in the live Q&A. Every fixture is in
`contracts/fixtures/events/`.

```bash
# Rates alert with runbook and email (change payload.reason for a fresh alert)
curl -s -X POST localhost:8001/api/v1/ingest/rates-oms -H 'content-type: application/json' \
  -d @contracts/fixtures/events/rates_trade_rejected.json

# Settlements failure: runbook, retries, phone approval (use a fresh workflowId)
curl -s -X POST localhost:8001/api/v1/ingest/settlements-engine -H 'content-type: application/json' \
  -d @contracts/fixtures/events/settlements_workflow_failed.json

# An unknown system (lands in Connect a system)
curl -s -X POST localhost:8001/api/v1/ingest/generic-webhook -H 'content-type: application/json' \
  -d @contracts/fixtures/events/unknown_payments.json

# 500 identical events in one batch -> one alert with x500
python3 -c 'import json; e=json.load(open("contracts/fixtures/events/rates_trade_rejected.json")); e["payload"]["reason"]="DUP_STORM_DEMO"; json.dump([e]*500, open("/tmp/rates_500.json","w"))'
curl -s -X POST localhost:8001/api/v1/ingest/rates-oms/batch -H 'content-type: application/json' -d @/tmp/rates_500.json

# SMS gateway down / up
curl -s -X POST localhost:8090/admin/outage -H 'content-type: application/json' -d '{"is_down": true, "channels": ["sms"]}'
curl -s -X POST localhost:8090/admin/outage -H 'content-type: application/json' -d '{"is_down": false, "channels": ["sms"]}'

# Alertmanager firing, then resolved: the alert closes itself (keep labels.instance identical)
curl -s -X POST localhost:8001/api/v1/ingest/alertmanager -H 'content-type: application/json' \
  -d @contracts/fixtures/events/alertmanager_firing.json
curl -s -X POST localhost:8001/api/v1/ingest/alertmanager -H 'content-type: application/json' \
  -d @contracts/fixtures/events/alertmanager_resolved.json

# Load test and horizontal scaling (back to defaults afterwards)
uv run python loadtest/scenarios.py steady --duration 60
docker compose up -d --scale processor=4 --scale delivery=4 --scale ingest=3 --scale api=2
docker compose up -d --scale processor=1 --scale delivery=2 --scale ingest=1 --scale api=1
```

Measured numbers to quote, from the README and [docs/benchmarks.md](benchmarks.md):

- **Sustained:** 800.0 msg/s (1,600 deliveries/s), p50 416.9 ms, p99 1,000.7 ms, with replicas
  `2:2:2:1` behind `proxy`.
- **Steady:** 200 msg/s, p50 41.1 ms, p99 83.8 ms.
- **Peak:** 983.8 msg/s, which is not sustainable.
- **Losses:** 0 lost in every scenario, including a 60 s gateway outage, `docker kill` of a
  processor mid-load, and a 120 s soak.

## Live judging: "the judges bring a schema and a runbook"

Untimed. Everything here happens in the UI.

1. **Their event.** Have them POST it to `localhost:8001/api/v1/ingest/generic-webhook`, or paste it
   in **Connect a system → Pick a sample → Paste a sample event**. Then **Check the mapping**, then
   **Test and save** and **Save mapping**.
2. **A rule for it.** Click **Create a rule for it**, then **New rule**. Build it with the form
   (**When**, **Who & how**, **Preview**) and **Save rule**.
3. **Their runbook.** Go to **Runbooks → Add a runbook** and paste YAML, Markdown or plain text.
   Beacon shows "Beacon turned this into N steps", with risky actions marked as needing approval,
   then **Save runbook**. Link it from the rule's YAML under **Advanced** (`runbook: <id>`).
4. **Send their event again.** The alert, the filled-in runbook and the deliveries appear live in
   the Inbox. Mailpit shows the email.
5. **A new source with YAML only, no restart of the pipeline:**

   ```bash
   sed 's/^id: generic-webhook$/id: judges/' config/sources/generic-webhook.yaml > config/sources/judges.yaml
   curl -s -o /dev/null -w '%{http_code}\n' -X POST localhost:8001/api/v1/ingest/judges \
     -H 'content-type: application/json' -d @contracts/fixtures/events/unknown_payments.json   # 202
   rm config/sources/judges.yaml
   ```
