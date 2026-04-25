# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Is

Flowra is an **interactive design prototype** — not a production application. It was created as a design handoff bundle to be reimplemented in a production tech stack. The entire app lives in `project/Flowra.html` (13K+ lines of React JSX transpiled at runtime by Babel Standalone). There is no build system, no package manager, and no test suite.

**To run it:** open `project/Flowra.html` directly in a browser. No server required.

Variants:
- `Flowra.html` — primary interactive prototype
- `Flowra Standalone.html` — self-contained offline version (all assets inlined)
- `Flowra-print.html` — print-optimized version

## Architecture

### Runtime Stack
- React 18 + ReactDOM (loaded from CDN via UMD builds)
- Babel Standalone 7 (transpiles JSX in-browser at load time)
- No charting library — all charts are hand-rolled SVG with inline geometry math
- Tailwind CSS (custom subset bundled in `tailwind.min.css`)
- Google Fonts: Fraunces (display serif), Manrope (body), JetBrains Mono (mono/tabular)

### Screen Flow
State machine driven by a `demoPhase` string:
```
'landing' → 'connecting' → 'reveal' → 'proposed' → 'replies' → 'reasoning' → 'factoring-proposed' → 'done'
```
All screens are rendered in a single React tree; phase transitions are triggered by user interactions.

### Two-Panel Main App Layout
Once past `reveal`, the UI splits into:
- **Left panel** — Chat interface (`ChatPanel`): streaming word-by-word AI responses, tool execution step animations, reasoning blocks that self-dismiss after ~4.5s
- **Right panel** — Tabs: Forecast, Terms, Credit

### Key State
| Variable | Type | Purpose |
|---|---|---|
| `demoPhase` | string | Which screen/phase is active |
| `approvedIds` | string[] | Action IDs the user has approved |
| `capriStatus` / `ombrelloniStatus` | 'pending' \| 'accepted' \| 'declined' | Per-action counterparty status |
| `factoringState` | 'pending' \| 'proposed' \| 'approved' \| 'done' | Invoice factoring flow state |

### Forecast Data Model
```js
BASE_FORECAST  // Array<{day: number, baseline: number}> — 91 entries (day 0–90)

ACTION_LIFTS   // Object mapping action ID → {startDay, amount}
  'early-pay-capri'    // +€4,365 from day 8
  'delay-ombrelloni'   // +€2,800 from day 12
  'vat-rateation'      // +€4,650 from day 14
  'triver-factor'      // +€17,020 from day 3 (invoice factoring, mutually exclusive with above)
```
Approving an action adds its ID to `approvedIds`, which recalculates the forecast line overlaid on the chart.

### ForecastChart (SVG)
Custom polyline rendering with:
- Clip paths for chart bounds
- `stroke-dasharray` animation for line draw-on entry
- Dynamic tooltip positioned on mouse hover (absolute positioning relative to SVG viewport)
- Red fill below zero (risk zone), green band above €15k (safe zone)

### Chat Streaming
Word-by-word reveal at 28ms/word. Tool execution steps appear sequentially at ~420ms intervals. The Claude API integration uses the system prompt defined inline — it describes business context (owner Chiara, Bagni Aurora beach club, Alassio).

### Tweaks Panel (`tweaks-panel.jsx`)
Floating runtime editor (draggable, bottom-right) that communicates with a parent frame via `postMessage`. Used by the design tooling to inject parameter overrides without reloading.

## Design System

### Colors (Riviera palette)
```
--cream:  #F6F4EE   (page background)
--paper:  #FBFAF5   (cards)
--ink:    #14201A   (primary text)
--forest: #1F4A3A   (positive/CTA)
--leaf:   #4F9E78   (accent)
--terra:  #C0603A   (risk/warning)
--amber:  #B8860B   (caution)
--mist:   #C8DDD1   (muted visual)
--gold:   #C8A96E   (highlights)
--line:   #E4E1D7   (borders)
```
Alternative palettes `notte` (dark) and `carta` (minimal) are defined but inactive in the main file.

### Key Animations
- `fadeUp` / `fadeIn` — entry transitions
- `pulseDot` — blinking status indicator
- `scan` — horizontal gradient sweep for active states
- `drawLine` / `dotPop` — chart entry animations
- `floatUp` — number change float label
- `glow` — ROI badge pulse

## Porting Notes

When reimplementing in a production stack (e.g. Next.js + TypeScript):
- All the business logic and data lives inline in `Flowra.html` — extract it carefully
- The SVG charts can be replaced with Recharts/Victory/D3 but the interaction model (hover tooltip, animated line draw-on, dual-zone shading) must be preserved
- The `demoPhase` state machine maps naturally to a React context or Zustand store
- `ACTION_LIFTS` and `BASE_FORECAST` are the core data contracts — keep them typed
- The streaming chat pattern (word interval + tool steps) is intentional UX, not a placeholder
