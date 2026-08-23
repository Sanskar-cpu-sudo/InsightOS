# InsightOS — Operations Console (Frontend)

A React (Vite) + plain CSS frontend covering all four InsightOS backend
workflows: Dashboard, Ask, History, and Upload.

## Design

Built as an "instrument panel" reading the business's vitals — every
number is a labeled reading, not a generic stat card. Revenue renders as
an animated bar chart; alerts pulse; cards reveal with a staggered
fade-in. No UI framework — the whole design system lives in
`src/styles.css`.

## Setup

```bash
npm install
cp .env.example .env   # edit VITE_API_BASE_URL if your backend isn't on localhost:8000
npm run dev
```

Requires the InsightOS backend running (CORS is already open on the
backend for local development).

## Build

```bash
npm run build
```

## Structure

```
src/
  components/    Reusable pieces (AppHeader, AppFooter, DecisionCard,
                 DecisionList, EmptyState, HeroPanel, Metric, PanelTitle,
                 RevenueBar, StatusMessage, WeeklyReport)
  pages/         Dashboard, AskPage, HistoryPage, UploadPage
  utils/         format.js — shared formatting/tone helpers
  api.js         All backend endpoint calls
  styles.css     Full design system (palette, type, animations)
  App.jsx        Routing shell (react-router-dom)
  main.jsx       Entry point
```

## Pages

- **Dashboard** (`/`) — revenue vitals bar chart, system readings grid,
  weekly report, and a "Run Pipeline Now" action.
- **Ask** (`/ask`) — ask a question, see the resulting decision.
- **History** (`/history`) — every past decision, with buttons to mark
  outcome (resolved / false positive / ignored).
- **Upload** (`/upload`) — drag-and-drop PDF upload into the knowledge base.
