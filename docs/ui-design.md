# UI design system and screen plan

This is the single source of truth for every UI task in `web/`. Read it before you touch a component. When a screen is not described here, extrapolate from the tokens and principles. Do not invent a new look.

## Brief

- **Product.** A real-time alerting console for operations teams at a trading firm. The teams are Rates, Settlements, Pricing and Platform.
- **Audience.** On-call engineers and ops staff (non-technical people included) during an incident, and a hackathon jury watching a 5-minute video.
- **Primary job.** In this order: what is wrong, who has been told, what is being done about it, and approve the next step.
- **Selling point to make visible.** It is fast (350 msg/s, p99 163 ms). Nothing gets lost. Duplicates fold into one alert. Fixes wait for a human.

## Visual direction

The reference is a calm, Apple-like productivity app (see the inbox reference the team picked):
- a light grey canvas holding one big white rounded "window";
- a narrow icon rail on the left with a dark logo tile;
- the active item is a raised white tile;
- soft pill buttons, with one solid near-black primary pill;
- generous whitespace, and list rows with a round avatar, a semibold title, a two-line muted preview and the time on the right.

Spend boldness in one place, the **live pulse card**. Everything else stays quiet.

### Signature element: the live pulse card

The pulse card is a wide card at the top of the Inbox:
- **Bars.** A row of thin vertical rounded bars, one per second for the last 60 s. Each bar's height is the events processed in that second, and the bars fill in from the right as time passes.
- **Labels.** Left of the bars: the team's monogram, "Live pipeline" and a muted subline such as "350 events/s · p99 163 ms".
- **Bar colours.** Normal bars are ink at 85% opacity. A second with any dead-lettered delivery gets a red bar; there should be none.
- **Zero-lost chip.** On the right, a small green chip: "0 lost".
- **Data.** Built from `GET /api/v1/metrics/summary`, polled every 2 s. The bars are client-side history, so no new API is needed.

## Tokens

Define them as CSS custom properties in `web/src/index.css`, mapped into Tailwind v4 with `@theme`. Never hard-code a colour in a component.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--canvas` | `#E9E9EC` | `#0E0E10` | page behind the window |
| `--window` | `#FFFFFF` | `#1C1C1E` | the main rounded window |
| `--panel` | `#F6F6F8` | `#151517` | content area behind cards |
| `--card` | `#FFFFFF` | `#232326` | cards, rows |
| `--ink` | `#1D1D1F` | `#F5F5F7` | primary text, primary pill |
| `--ink-2` | `#6E6E73` | `#A1A1A6` | secondary text |
| `--ink-3` | `#A1A1A6` | `#6E6E73` | tertiary text, icons at rest |
| `--hairline` | `#E5E5EA` | `#2C2C2E` | 1 px borders and dividers |
| `--fill` | `#F2F2F4` | `#2C2C2E` | secondary pill, inputs |
| `--accent` | `#0A84FF` | `#0A84FF` | links, focus ring, selection (use sparingly) |
| `--critical` | `#FF3B30` | `#FF453A` | severity critical |
| `--error` | `#FF9500` | `#FF9F0A` | severity error |
| `--warning` | `#FFCC00` (text `#A05A00`) | `#FFD60A` | severity warning |
| `--info` | `#8E8E93` | `#8E8E93` | severity info |
| `--success` | `#34C759` | `#30D158` | delivered, approved, 0 lost |

### Team colours

Used for avatars and monograms only:

| Team | Colour |
|---|---|
| rates | `#0A84FF` |
| settlements | `#AF52DE` |
| pricing | `#FF9500` |
| platform | `#34C759` |

The avatar is a circle with the colour at 16% opacity, and the monogram glyph or initial in full colour.

### Type

- **Family.** The system stack `-apple-system, BlinkMacSystemFont, "SF Pro Text", "Inter", "Segoe UI", system-ui, sans-serif`. That is SF Pro on the Mac we record on.
- **Numbers.** Use `font-variant-numeric: tabular-nums` everywhere numbers update live.
- **Scale (px).**

  | Size | Use |
  |---|---|
  | 12 | caption |
  | 13 | meta |
  | 15 | body |
  | 17 | row title |
  | 22 | card title |
  | 28 | page title |
  | 40 | hero number |

- **Weights.** 400 body, 500 labels, 600 titles. No 700 or above.
- **Case.** Sentence case everywhere. No ALL-CAPS labels and no tracked-out eyebrows.

### Shape and depth

Radius follows hierarchy; do not use one radius for everything:

| Element | Radius |
|---|---|
| window | 28 |
| card | 20 |
| list row and inner tile | 14 |
| input | 12 |
| pill | 9999 |
| avatar | 50% |

Depth:
- **Window:** `0 1px 0 rgb(0 0 0 / .04), 0 24px 60px -24px rgb(0 0 0 / .18)`.
- **Cards:** a 1 px `--hairline` border, plus at most `0 1px 2px rgb(0 0 0 / .04)`. No big grey drop shadows on every card.
- **Active rail tile:** white, a 1 px hairline border and `0 2px 6px rgb(0 0 0 / .06)`.

### Spacing

- A 4 px base grid.
- The window has a 16 px gutter to the canvas.
- Content padding is 32 px, cards have 24 px of padding, and rows have 16–20 px vertical padding.

### Motion

Keep it rare and meaningful. Allowed:
- a new alert row slides in from the top over 200 ms;
- the `×N` count badge does a quick scale bump when dedup increments it;
- timeline steps tick from pending to done;
- the phone rings.

Do not:
- add hover animations on every card;
- add entrance animations on page load.

Honour `prefers-reduced-motion`.

### Icons

Use our own inline SVG set in `web/src/components/ui/icons.tsx`:
- 24×24 viewBox, 1.75 px stroke, round caps and joins, `currentColor`, in the SF Symbols spirit;
- there is no icon dependency.

Needed: inbox, approval (checkmark seal), phone, rules (slider), connect (plug), runbook (list-checklist), people, insights (chart), send, bell, check, cross, clock, retry, escalate (arrow-up-circle), sun/moon, search, filter, chevron, plus, more.

### Logo

A dark rounded tile on the rail with a white glyph: a small dot inside two concentric arcs, the way a signal or beacon reads. Do not use an asterisk or burst. The working product name is **Beacon**.

## Layout

```
┌ canvas ──────────────────────────────────────────────────────────────┐
│ ┌ window (radius 28) ───────────────────────────────────────────────┐ │
│ │ rail │ Inbox  •  21 open alerts                    (◐) [Rates ▾]  │ │
│ │ ┌──┐ │───────────────────────────────────────────────────────────│ │
│ │ │◉ │ │ (Open 21)  (Acknowledged)  (Resolved)  (All)               │ │
│ │ └──┘ │───────────────────────────────────────────────────────────│ │
│ │  ✉   │ ┌ pulse card ───────────────────────────────────────────┐ │ │
│ │  ✓ 3 │ │ (R) Live pipeline      ▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮▮ ● 0 lost   │ │ │
│ │  ☎   │ │     350 events/s · p99 163 ms                         │ │ │
│ │  ─   │ └───────────────────────────────────────────────────────┘ │ │
│ │  ⚙   │ ┌ list (card) ────────────┐ ┌ detail (card) ────────────┐ │ │
│ │  ⌁   │ │ (R) Rejected EUR 25M ×3 │ │ title, severity, owner    │ │ │
│ │  ☰   │ │     Trade T-1 for ACME… │ │ timeline                  │ │ │
│ │  ☺   │ │ (S) Workflow failed  2m │ │ runbook progress          │ │ │
│ │  ▤   │ └─────────────────────────┘ └───────────────────────────┘ │ │
│ └──────┴───────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### Rail

The logo sits at the top. Then these items:
1. Inbox
2. Approvals (red count badge)
3. Phone
4. — divider —
5. Rules
6. Connect a system
7. Runbooks
8. People & channels
9. — divider —
10. Insights

At the bottom of the rail are the appearance toggle and the current-team avatar, which opens the team switcher.

Every rail item has a tooltip with its name; use the Popover API or `title` as a fallback. On screens narrower than 1100 px the rail stays and the detail pane becomes a full-width drill-down.

### Header

The page title, then the context in muted text, then the right-side actions.

### Toolbar

At most one primary pill, a hairline vertical divider, then secondary pills that act as filters (with counts).

## Components

All components live in `web/src/components/ui/`. Each component does one thing:
- `Button`: primary, secondary, ghost and danger variants; pill shape; 36 px or 44 px; loading state.
- `Pill`: a filter toggle with a count.
- `Card`, `Avatar`, `SeverityDot`, `StatusChip`.
- `CountBadge`: `×500`, with a bump animation.
- `Rail`, `RailItem`, `PageHeader`, `Toolbar`.
- `EmptyState`: icon, one sentence and one action.
- `Dialog`: native `<dialog>`, light-dismiss.
- `Toast`: a persistent region.
- `Tooltip`.
- `Timeline`, `TimelineStep`: pending, running, done, failed and skipped states.
- `Field`: a label, control, help text and an inline error rendered by API path.
- `Select`, `MultiSelect` as chips, `Toggle`, `Segmented`.
- `Spinner`, `Skeleton`.
- `PulseBars`.

Use modern platform features where they fit:
- native `<dialog>` and the Popover API;
- `:focus-visible`;
- `color-scheme`, `light-dark()`;
- container queries for card internals;
- View Transitions for list → detail when supported.

The guides are in `~/.claude/design-refs/mwg-guides/` (ui-components, visual-design, accessibility, forms, user-experience). Read the relevant one before you build a component.

## Screens

1. **First run.**
   - **Sign in.** Pick who you are; Beacon opens that person's team. There is no password.
   - **Welcome.** Shown once per person after signing in. Sign-in is kept for the tab session only, so a fresh visit starts on the account picker. Settings can reopen it. Three pages: what Beacon is (Inbox, Rules, Approvals), how an alert reaches you (event → rule → one alert → the right person), and "Try it now", whose primary button sends a test alert and opens the Inbox.
   - **Setup checklist on Home.** Shows "Set up <team>": connect a system, write a rule, choose who is told, send a test alert. Every tick comes from live data (schema profiles, team rules, recipients with channel preferences, any team alert), so it cannot claim a step that does not work. The next step is highlighted and carries the primary button. A team that is fully set up gets one quiet line with "Show steps". Hiding is stored per team.
2. **Inbox.** The pulse card, then the alert list and the detail pane.
   - **Row:** team avatar, title (17/600), a two-line preview of the body, a `×N` badge when count > 1, a severity dot, relative time, and a status chip when not open.
   - **Detail:** title, severity and owner team; the actions Acknowledge, Resolve and Propose a fix.
   - **Detail timeline, in plain language:**
     - "Event received from Settlements engine"
     - "Alert created"
     - "Emailed Anna"
     - "Health check passed"
     - "Retry failed (2 of 2)"
     - "Waiting for Piotr to approve escalation"
     - "Approved by Piotr by phone"
     - "Escalated"
   - Steps tick live via SSE.
   - Technical details (raw event, fingerprint, deliveries table) sit behind a "Details" disclosure.
3. **Approvals.** Cards that read as a request: "Escalate wf-… to the settlements lead?", who asked, why, and Approve/Reject buttons. Fix proposals sit below with a diff.
4. **Phone.** An iPhone-like device frame. The full-screen route `/phone` works on a real phone over Wi-Fi.
   - **Lock screen.** A big clock and SMS banners in iOS style.
   - **Incoming call.** A blurred background, the caller "Beacon alerts", and round green and red buttons.
   - **In call.** A spoken script and the iOS keypad. `*` rejects and `#` repeats.
   - **Speech.** Pick the best installed voice: prefer names containing "Premium", "Enhanced" or "Siri", in en-US/en-GB; otherwise the default. Use rate 0.95 and read digits one by one with pauses.
5. **Rules.** A list of rules. A rule opens as a 3-step flow:
   1. When: the condition form.
   2. Who and how: recipients and channels.
   3. Preview: "Last hour this rule would have created 3 alerts and sent 5 messages", then Save.

   YAML lives under "Advanced".
6. **Connect a system.** 3 steps: paste a sample event (or pick one from "Recently seen unknown events") → "Beacon suggests this mapping" (AI badge) with editable fields → a green "Matches your sample" test → Save. Then a link to "Create a rule for it".
7. **Runbooks.** A list. "Add a runbook" lets you paste plain text, then "Beacon turned this into 4 steps" shows a checklist with "Needs approval" chips, then Save. YAML lives under "Advanced".
8. **People & channels.** A person card with their channels and working hours, edited in plain language: "During 08:00–20:00 Europe/Warsaw send critical alerts by SMS and phone, otherwise by email."
9. **Insights.** Three hero numbers (events/s, p99, lost = 0) plus open alerts, small SVG sparklines from client-side history, and "Open Grafana" as a secondary pill.
10. **Test console.** Kept off the product screens: `Shift+D` (or Settings → Test console, or `?demo=open`) opens a side sheet with scenario buttons, the live stream of incoming events and the on-call phone. The route `/demo` still shows the scenario buttons. The scenarios are:
    - Send rates alert
    - Settlements workflow failure (fresh workflowId)
    - Send 500 duplicates
    - SMS gateway down / up
    - Ask the jury's sample

    Each button calls the existing ingest and mock-gateway endpoints and shows a toast.

## Copy rules

- Write from the user's side: "People & channels", not "Recipients config"; "Connect a system", not "Schema profiles".
- Use plain verbs and keep the same verb through a flow. "Approve" produces the toast "Approved".
- Errors say what happened and how to fix it, next to the field. They never apologise and are never vague.
- Empty states invite action: "No alerts right now. Send a test alert to see one arrive."
- Show status as words, not enums. `pending_approval` becomes "Waiting for approval" and `delivered` becomes "Delivered".

## Quality floor (every PR)

- Keyboard reachable, with a visible `:focus-visible` ring (`--accent`, 2 px, offset 2).
- Contrast meets WCAG AA in both themes. `prefers-reduced-motion` is respected.
- Works at 1280×800, the recording size, and down to 1024 wide; `/phone` works at 390×844.
- Types come only from `web/src/api/schema.gen.ts`. No `any`. Files stay under 300 lines.
- Before handing over, check with a headless Chrome screenshot:
  ```
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars --window-size=1280,800 --screenshot=<file>.png http://localhost:5173/...
  ```
