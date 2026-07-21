# Dashboard Mockup Recreation — Design Spec (2026-07-21)

## Goal

Restyle the Flask frontend to look nearly identical to the reference mockup at
`C:\Users\damon\.claude\image-cache\25b9bf4f-bb6c-48ac-915c-8e90be1c763c\1.png`,
adapted for this app's real purpose: a personal AI assistant that manages a
calendar (voice input via whisperflow and Discord reminders come later — frontend only now).

## Deltas from the mockup (user-approved)

| Mockup | This app |
|--------|----------|
| "Planned Absences" employee timeline (rows, leave bars) | **"Upcoming Events"** card: same header treatment (title, date chip, Filter, View all — inert), but the employee column and leave bars are gone; the existing calendar month grid stretches to fill the whole card in a compact/shrunken form |
| Pill tabs: Dashboard / Employees / Reports | Pill tabs: **Dashboard / Calendar** only |
| "+ Add Employee" button | **"+ Add Event"** button (inert for now) |
| Onboarding card with 4 people | **Onboarding card kept as an empty box** — header + "View all" only, blank content area (use later) |
| "Welcome, Emily" assistant card | Working chat widget styled like the mockup card: orb, welcome heading, "What can I help with today?", quick-action chips, input with attach + mic placeholder buttons and 0/300 counter |

Everything else matches the mockup: gray canvas, white rounded app frame,
icon-only left sidebar (logo top, nav icons middle, settings bottom), topbar
(pill-tab strip, round search button, overlapping avatar stack + "8+", add
button, bell, user avatar), Future Events card with yellow highlighted first
event ("In 15 min" badge, time/date chips, mini avatar stack).

## Hard rules

- **Icons: Google Material Icons via CDN font** (`<span class="material-icons">` or material-symbols). **Never emojis or Unicode glyph characters** — replace the existing `&#9635;`, `&#128197;`, `&#9790;` etc. in `templates/base.html`.
- **Theme: light is default and is tuned to match the mockup.** The existing dark glass theme stays behind the toggle and must still look coherent (no regression).
- Keep the existing token system (`tokens.css` OKLCH variables) — retune values, don't hardcode hex in component CSS.
- Calendar behavior unchanged (`calendar.js`, `/api/events`); `/calendar` page shows the full-size calendar with the same visual language.
- Chat widget stays functional (`chat-widget.js`, `dashboard.js` init).
- No new JS dependencies. CSS-first.

## Visual notes from the mockup

- Outer canvas: mid gray (~oklch 0.84 neutral). App frame: white, radius ~24–28px, soft large shadow, inset from viewport edges.
- Topbar: light-gray pill strip containing tabs; active tab = white raised pill with border + subtle shadow; inactive tabs = flat with icon + label.
- Sidebar: white column inside frame; active nav icon = white circle with border/shadow.
- Cards: white on very-light-gray content background; radius ~16–20px; soft shadows, hairline borders.
- Calendar cells: rounded light-gray squares; weekend columns get diagonal-stripe hatching; today column highlighted blue (pill day header + dashed vertical line if cheap to do).
- Accent colors seen: blue (today/highlights), yellow (#FFD84D-ish event highlight), purple, green — map onto existing tokens.
- Assistant orb: glossy blue radial-gradient blob.
- Fonts: keep existing project fonts; no Inter/Roboto introduction.

## Files expected to change

- `templates/base.html` — Material Icons CDN link, icon swaps, topbar additions (search button, + Add Event, bell), sidebar logo/settings slots.
- `templates/dashboard.html` — Upcoming Events card wrapping calendar, restyled Future Events, blank Onboarding, mockup-style Assistant card.
- `templates/calendar.html` — full-page calendar consistent with new look.
- `static/css/tokens.css`, `static/css/depth.css`, `static/css/dashboard.css`, `static/css/style.css` — retuned light theme, new component styles.
- `tests/test_dashboard.py` (and calendar route test if selectors change) — keep green.

## Acceptance

1. Full pytest suite green.
2. Side-by-side screenshot vs mockup: layout, proportions, and color story read as nearly identical (allowing the approved deltas).
3. Dark toggle still produces a coherent dark glass theme.
4. No emojis/Unicode-glyph icons anywhere in templates.
