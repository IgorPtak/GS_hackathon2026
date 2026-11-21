# 5-minute demo video: script, shot list and editing notes

The video is the main thing the judges score, across every category. Everything happens in the
UI. The heart of it is Scene 2: a team sets up alerting from nothing (a new system, a runbook, a
rule) and gets its first alert, with no code and no restart. Every click below is a label the UI
really shows, and every timing was measured on `main`. Terminal equivalents are in the appendix,
for retakes and for the live Q&A only.

## What the video has to prove

| Judging criterion | Scene | The one thing the viewer must remember |
|---|---|---|
| UX: fresh clone to working demo, first-time users | 1 | 3 commands, healthy in 18 s; a welcome and a test alert in one click |
| Flexibility: new source, schema, rule; rule editor | 2 | An unseen event becomes a mapped system, a runbook and a rule in about 2 minutes, all in the UI |
| Per-rule routing and presentation | 2 | The rule says who is told, on which channel, and how the alert reads |
| Runbooks in many formats; actions; approval | 2, 3 | Plain text becomes steps; risky steps wait; the phone reads a code |
| Channel preferences, working hours | 4 | Each person picks channels and hours in a form |
| Propose fixes | 4 | Anyone suggests a change; the owning team accepts it; it goes live |
| Don't flood; survive failure | 5 | 500 events become 1 alert; SMS down means *Paused*, none lost |
| Scalability, throughput, latency (measured) | 6 | 800 msg/s sustained, p99 about 1 s, 0 lost; more replicas, more lines |
| Innovation, AI safety, how we used AI | 7 | The AI only proposes; approvals cannot be removed; synthetic data |

## Before recording

1. **Clean slate.** Run on `main`, rehearse, forget what the rehearsal and earlier tries created
   in the UI, then reset:

   ```bash
   git pull && docker compose up -d --build
   uv run python scripts/demo_rehearsal.py           # expect "9/9 scenes passed"
   uv run python scripts/forget_demo_config.py       # lists UI-made rules, runbooks, mappings
   uv run python scripts/forget_demo_config.py --yes # removes them and empties the unknown inbox
   uv run python scripts/reset_demo.py --seed        # clean alerts, Mailpit, 1 alert per team
   ```

   Repeat this before every full take of Scene 2. That scene creates `payments-declined` and a
   "Payment declined check" runbook, and a second take needs them gone.
2. **AI on:** the LLM endpoint in `.env` must answer, because Scenes 2 and 4 use it. Check it in
   **Settings**, where the AI assistant card shows the model.
3. **Browser:** Chrome, a fresh profile or a guest window, no extensions or bookmarks bar, window
   1440×900 or larger, zoom 100%. Record at 2560×1600 and export at 1080p, so text stays sharp after
   zoom-ins.
4. **Theme:** use one theme for the whole video. Light reads best when compressed; dark looks more
   premium. Do not switch.
5. **Sound:** turn the volume up. In **Settings → Phone voice**, pick an English voice (Samantha or
   Daniel) and press **Test voice**. Before Scene 3, click once on the page so audio can play.
6. **Quiet machine:** Do Not Disturb on, Docker notifications off, Dock hidden.
7. **Who to sign in as:**
   - Anna Kowalska (Rates) for Scenes 1, 2, 4 and 7.
   - Piotr Nowak (Settlements) for Scene 3 and the SMS part of Scene 5. The test console shows the
     signed-in person's phone, and Piotr gets calls and SMS at any hour.
   - Sign-in lasts one tab session, so a new window always starts at "choose who you are".

## Automated recording (what we used)

`scripts/demo_video/` records every scene with scripted clicks and builds the film.

- **Recording:** Chrome screencast at 2880×1620, a drawn cursor, and waits on the AI cut out.
- **Editing:** zooms, captions, chapter labels, title cards and the benchmark card.
- **Voice:** a guide voice from macOS `say`. The phone's lines are dubbed exactly where the app
  speaks them.

```bash
uv run python scripts/forget_demo_config.py --yes && uv run python scripts/reset_demo.py --seed
uv run --with playwright python scripts/demo_video/record.py --all    # silent clips, about 8 min
uv run --with playwright python scripts/demo_video/render.py          # ~/Movies/beacon-demo/beacon-demo.mp4
```

To put your own voice in, record one file per block of `~/Movies/beacon-demo/VOICE_SCRIPT.md`
(`s1.wav`, `s3-1.wav`, …) into `~/Movies/beacon-demo/voice/`, then run `render.py --voice
~/Movies/beacon-demo/voice`. Leading silence is trimmed, and a missing file keeps the guide
voice. To redo one scene, run `record.py <scene>` and render again. Scene 2c needs the
`payments-declined` rule deleted first.

## Recording plan by hand: one silent clip per scene, the voice last

1. Record each scene as its own silent clip (`s1-setup.mov` … `s7-ai.mov`), with 2 s of stillness
   at both ends for transitions. A mistake costs one scene, not the whole video.
2. Set the start state (table below) before pressing record. Do not record navigation that is not
   part of the story.
3. Put the clips on a timeline in order. Cut every wait, then add zooms and captions.
4. Record the voice last, scene by scene, while watching the cut. Fit the picture to the voice: if a
   clip is short, hold a still or slow a zoom. Never rush the reading.
5. Add music and the title card. Watch once muted: the captions alone must tell the story.

| Clip | Sign in as | Start on | Before pressing record | Ends when |
|---|---|---|---|---|
| s0 problem | nobody | sign-in screen | new window; let the star finish drawing | after a 6–8 s still |
| s1 setup | nobody → Anna | sign-in screen | clean slate (above); new window | the test alert is open in the Inbox |
| s2a connect | Anna | Home | welcome already done | **Save mapping** shows "Saved" |
| s2b runbook | Anna | Runbooks | the runbook text copied to the clipboard (below) | "Beacon turned this into N steps" |
| s2c rule | Anna | Rules | nothing | **Save rule** done |
| s2d first alert | Anna | Home | nothing | the payment alert is open, its runbook in view |
| s3 phone | Piotr | Home | one click on the page (sound) | the Inbox timeline shows the approval and the escalation |
| s4 people & fix | Anna | People & channels | Mailpit tab open | the fix card folds away in Approvals |
| s5a ×500 | Anna | Home | nothing | the ×500 alert is open |
| s5b SMS outage | Piotr | Insights | console says **Take SMS down** (SMS is up) | SMS is back to **Sending**, nothing waiting |
| s6 scale | n/a | Insights | start a load run off-camera (appendix) about 15 s before | Grafana shows one line per replica |
| s7 AI | Anna | Runbooks | nothing | closing card |

## Shot list and voiceover (5:00)

The voiceover is about 570 words: roughly 4:05 at a calm pace, which leaves room for pauses. Text in *[brackets]* is a caption.

### Scene 0 · 0:00–0:15 · The problem

- **Screen:** the sign-in screen with the ASCII star, with a slow push-in.
- **Voice:** "Every system throws errors, warnings and business events. They end up in logs,
  dashboards and mailboxes. The right person finds out late, or gets so many alerts they stop
  reading. Beacon fixes that."
- *[Beacon · alerts that reach the right person, and help them fix it]*

### Scene 1 · 0:15–0:40 · From a fresh clone to the first alert

- **Screen:**
  1. A title card (not a terminal) showing the three README commands.
     *[git clone · cp .env.example .env · docker compose up -d --build — healthy in 18 s]*
  2. Sign-in: click **Anna Kowalska**.
  3. Welcome: **Next** to "How an alert reaches you", hold for one beat, **Next**, then **Send a
     test alert**.
  4. The Inbox opens with the test alert. *[about 1 s from event to alert]*
- **Voice:** "From a fresh clone it is three commands, and the stack is healthy in eighteen
  seconds. There is no password: you pick who you are. A short welcome shows the idea: an event, a
  rule, one alert, the right person. One click sends a test alert, and here it is, a second later."

### Scene 2 · 0:40–2:30 · A team sets up alerting from nothing, in the UI

This is the scene the judges care about most, so give it time.

**2a · Connect a system (0:40–1:05)**

- **Screen:**
  1. **Shift + D**, then **Event from a new system**. Beacon opens **Connect a system**, and the
     payment event is first under "Recently seen unknown events".
  2. **Map this event.** The AI takes about 8 s; cut it. "Beacon suggests this mapping": Event type
     ← `evt`, Source ← `svc`, Severity ← `lvl` (WARN → warning), Time ← `at`, Entity ←
     `data.paymentId`, plus "Group repeats by". Hover on "Why Beacon chose this".
  3. **Test this mapping** (about 8 s; cut): "Matches your sample", with the values read from the
     event. Then **Save mapping**.
- **Voice:** "Say a payments team wants alerts. Beacon has never seen their events. One payment
  event arrives, and it waits in Connect a system. Beacon suggests how to read it: the type, the
  severity, the time, and what makes two events the same. We check it against the sample, and
  save. No code, and nothing restarts."

**2b · A runbook in plain words (1:05–1:30)**

- **Screen:** **Runbooks → Add a runbook**. Name: `Payment declined check`. Paste the text below,
  click **Turn into steps**, then **Save and read it**. The AI takes about 6 s; cut it. The result
  reads "Saved. Beacon turned this into 4 steps. 2 need approval before running", with a "Read by
  AI" chip and a **Needs approval** tag on the risky steps.

  ```text
  When a payment is declined, first check the payment gateway health. If the gateway is fine,
  retry the payment once. If it is declined again, escalate to the payments on-call lead, which
  needs approval. Afterwards tell the customer support team.
  ```

- **Voice:** "Next, what to do when it happens. Teams write runbooks the way they talk. We paste
  a few sentences, and Beacon turns them into steps: a health check, a retry, an escalation, a
  ticket. Anything risky is marked as needing approval. YAML and Markdown work too."

**2c · The rule (1:30–2:15)**

- **Screen:** **Rules → New rule**.
  - **When:** Rule id `payments-declined`, description "Declined payments". Field `evt` · *matches
    the pattern* · `payment.declined*`. **Add condition**: field `lvl` · *at least severity* ·
    Warning. "Rule is valid" appears. **Next**.
  - **Who & how:** default channels *email* and *the app*, already selected. Under **How the alert
    looks**, Title `Payment {{data.paymentId}} declined`, Text
    `{{data.amount}} {{data.currency}} declined: {{data.declineCode}}`. **Runbook**: *Payment
    declined check*. **Next**.
  - **Preview** (under 1 s): "In the last hour this rule would have created N alerts and sent M
    messages", then "Who would be messaged". *[nothing is sent yet]*
  - Open **Advanced** for 2 s to show the same rule as YAML, then **Save rule**.
- **Voice:** "Now the rule, as a form, not code. When: the event type matches 'payment declined',
  at warning or above. Who and how: Anna's team, in the app and by email. How the alert reads,
  with values from the event in double braces. And which runbook it carries. Before anything goes
  live, Preview replays the last hour: how many alerts, how many messages, and exactly who. Under Advanced
  it is plain YAML, ready for Git. Save, and every worker reloads live."

**2d · The first alert (2:15–2:30)**

- **Screen:** **Shift + D → Event from a new system** again, close the console, then the **Inbox**.
  "Payment P-… declined", with the text "1250 PLN declined: Insufficient funds". Open it and scroll
  slowly through **What happened** and **Runbook**. The retry step shows **Waiting for approval**
  with the code. A step whose input is not in the event says **Missing values** instead of
  guessing.
- **Voice:** "The next payment event is a real alert: our title, our text, our runbook, filled in
  with this payment. The risky step is already waiting for a human."

### Scene 3 · 2:30–3:15 · A runbook that acts, and a phone that asks first

- **Screen:**
  1. Sign in as **Piotr Nowak** and click once on the page.
  2. **Shift + D → Settlement workflow fails.** Keep the console open: the phone is on its right.
  3. The phone rings. **Answer**. It reads the alert, then "To approve, enter code: two, four…".
     Type the code on the keypad. Speed up the ringing, but keep the voice at 1×.
  4. Close the console, open the alert in the **Inbox**, and scroll through **What happened**: the
     health check, the failed retries, "waiting for Piotr", approved by phone, escalated.
- **Voice, part 1** (while it rings): "When a settlement workflow fails, the team's runbook runs
  on its own. It checks the service and retries the workflow twice. The retries fail, and
  escalating is risky, so Beacon asks first. It calls Piotr."
- *The phone's own voice reads the problem and the four-digit code. Leave it alone.*
- **Voice, part 2** (after the code is typed): "He approves on the keypad. He could also reply to
  the SMS, or click Approve. Every step is recorded: what ran, who approved, and how."

### Scene 4 · 3:15–3:50 · Everyone picks their channels; anyone can propose a fix

- **Screen:**
  1. Sign in as **Anna**. **People & channels** → Anna's card → **Edit**. Critical alerts are sent
     by SMS and phone until 20:00; outside working hours, by email. Change something small and
     **Save**: "Saved".
  2. Back in the **Inbox**, open the payment alert. **Propose a fix → Draft with AI** fills in a
     change, then **Send proposal**.
  3. **Approvals**: the proposal shows as a before/after diff. **Accept**. The card shows
     "Accepted. The change is saved and live now", then folds away.
- **Voice:** "Each person chooses their own channels and hours. Anna gets an SMS and a call while
  at work, and email after that. And if an alert is too noisy, anyone can propose a fix. The AI
  can draft it, but it is only a proposal: the owning team sees the diff, accepts it, and it is
  live, with no restart."

### Scene 5 · 3:50–4:15 · Don't flood people, and never lose an alert

- **Screen:**
  1. As Anna: **Shift + D → 500 identical events**. The Inbox shows one alert with **×500**.
     *[500 events → 1 alert]*
  2. As Piotr: **Take SMS down**, then click **Settlement workflow fails** two or three times.
     Under **Insights → Channels**, within about 5 s, SMS shows **Paused** with "N waiting, none
     lost" while the other channels keep **Sending**.
  3. **Bring SMS back.** Within about 10 s SMS returns to **Sending** with nothing waiting. *[0 lost]*
- **Voice:** "Five hundred identical errors are one alert with a counter, not five hundred
  messages. And when a channel goes down, here the SMS gateway, Beacon pauses it, keeps every
  message, and keeps the other channels working. When it comes back, the queue drains. Nothing is
  lost."

### Scene 6 · 4:15–4:40 · Built to scale, and measured

- **Screen:**
  1. **Insights → Pipeline queues and deliveries** during a load run started off-camera, with 3
     processor replicas: Retries 0, Dead-lettered 0, no stream lag.
  2. Grafana, the **msg/s processed by replica** panel alone (`viewPanel=8`): one line per
     replica, sharing the work.
  3. A "Measured, not estimated" card with the README benchmark table.
  - Do not show live p99 tiles while recording. Screen capture and the SMS and phone mocks
    (inside working hours) slow the laptop, so the live p99 does not match the controlled
    benchmark, and the 5-minute window still includes any outage scene.
- **Voice, part 1** (live): "Under the hood, every worker is stateless and scales out. Alerts
  and their deliveries are written in one database transaction, so a crash cannot lose them."
- **Voice, part 2** (benchmark card): "We measured, not estimated: eight hundred messages a
  second sustained, p99 around one second, and zero lost in every test, including a gateway
  outage and killing workers under load."

### Scene 7 · 4:40–5:00 · AI that helps, humans that decide

- **Screen:**
  1. **Runbooks**: the runbook from Scene 2, with **Advanced** open on the original text next to
     the steps and the "Read by AI" chip.
  2. Closing card: the repository link and the tagline. *[github.com/IgorPtak/GS_hackathon2026]*
- **Voice:** "The AI only reads runbooks and drafts proposals, and never on the alert path. It
  cannot remove an approval, secrets are redacted before every call, and all the data here is
  synthetic. Beacon: teams change alerts without fear and without code, and the AI only proposes."

## Editing notes

- **Cut every wait:** the two AI calls in Scene 2 (about 8 s and 6 s), ringing and loading. Speed
  up with a small "4×" badge. Keep speech and the phone voice at 1×.
- **Zoom 1.5–2× on proof**, and hold each for about 1.5 s:
  - "Matches your sample";
  - "Beacon turned this into 4 steps";
  - the Preview sentence;
  - the alert title filled with values;
  - the approval code;
  - ×500;
  - "Paused · N waiting, none lost";
  - the Grafana p99 tile.
- **Captions carry every number and claim.** Judges may watch muted.
- **Typing:** speed up the typing in Scene 2 (2–3×), or paste values. Never let the viewer watch
  slow typing.
- **Cursor:** use a larger cursor with a click highlight (Screen Studio, or the cursor size
  setting in macOS Accessibility). Move slowly and never hunt for a button on camera.
- **Chapter labels** in a corner: Setup · New team, no code · Runbook & phone · People & fixes ·
  No flood, no loss · Scale · AI.
- **Audio:** record the voice with a headset or a lavalier mic in a quiet room. Music only under
  Scene 0 and the end, at -25 dB, and duck it under the phone's voice.
- **Length:** at most 5:00. If it runs long, trim Scene 6 first; the README carries the numbers.
- **Export:** 1080p, H.264, 30 fps.
- **Suggested tools:** Screen Studio or OBS for capture; DaVinci Resolve, CapCut or iMovie for the
  cut.

## Retakes

- Test console scenarios make fresh ids on every click, including **500 identical events**, so
  retakes never merge into old alerts.
- **Scene 2:** run `forget_demo_config.py --yes` and `reset_demo.py --seed` before every retake,
  or `payments-declined` and the runbook already exist.
- **Other scenes:** `reset_demo.py --seed` resolves alerts, rejects pending approvals and fix
  proposals, clears Mailpit, heals the gateway and seeds one alert per team.
- **SMS left down:** click **Bring SMS back** in the console.
- **Welcome again:** open a new window, or use **Settings → Show the welcome again**.

## Appendix: terminal equivalents (retakes and live Q&A only)

All fixtures are in `contracts/fixtures/events/`.

```bash
# Load run for Scene 6 (start off-camera), and scaling out / back
uv run python loadtest/scenarios.py steady --duration 60
docker compose up -d --scale processor=4 --scale delivery=4 --scale ingest=3 --scale api=2
docker compose up -d --scale processor=1 --scale delivery=2 --scale ingest=1 --scale api=1

# Rates alert with runbook and email (change payload.reason for a fresh alert)
curl -s -X POST localhost:8001/api/v1/ingest/rates-oms -H 'content-type: application/json' \
  -d @contracts/fixtures/events/rates_trade_rejected.json

# An unknown system (lands in Connect a system)
curl -s -X POST localhost:8001/api/v1/ingest/generic-webhook -H 'content-type: application/json' \
  -d @contracts/fixtures/events/unknown_payments.json

# SMS gateway down / up
curl -s -X POST localhost:8090/admin/outage -H 'content-type: application/json' -d '{"is_down": true, "channels": ["sms"]}'
curl -s -X POST localhost:8090/admin/outage -H 'content-type: application/json' -d '{"is_down": false, "channels": ["sms"]}'

# Alertmanager firing, then resolved: the alert closes itself (keep labels.instance identical)
curl -s -X POST localhost:8001/api/v1/ingest/alertmanager -H 'content-type: application/json' \
  -d @contracts/fixtures/events/alertmanager_firing.json
curl -s -X POST localhost:8001/api/v1/ingest/alertmanager -H 'content-type: application/json' \
  -d @contracts/fixtures/events/alertmanager_resolved.json
```

Measured numbers to quote, from the README and [docs/benchmarks.md](benchmarks.md):

- **Sustained:** 800.0 msg/s (1,600 deliveries/s), p50 416.9 ms, p99 1,000.7 ms, with replicas
  `2:2:2:1` behind `proxy`.
- **Steady:** 200 msg/s, p50 41.1 ms, p99 83.8 ms.
- **Peak:** 983.8 msg/s, which is not sustainable.
- **Losses:** 0 lost in every scenario, including a 60 s gateway outage, `docker kill` of a
  processor mid-load, and a 120 s soak.

## Live judging: "the judges bring a schema and a runbook"

Untimed, all in the UI. It is Scene 2 with their material.

1. **Their event:** POST it to `localhost:8001/api/v1/ingest/generic-webhook`, or paste it under
   **Connect a system → Paste a sample event**. Then **Map this event**, **Test this mapping** and
   **Save mapping**.
2. **Their runbook:** **Runbooks → Add a runbook**, paste YAML, Markdown or plain text, then **Turn
   into steps** and save.
3. **A rule:** **Rules → New rule**. Fill in **When**, then **Who & how** (channels, title and
   text, their runbook), check **Preview**, and **Save rule**.
4. **Their event again:** the alert, the filled-in runbook and the deliveries appear live in the
   Inbox; the email is in Mailpit.
