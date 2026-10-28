# Workspace UI revamp

The owner approved a mockup-led redesign of the browser workspace on October 28, 2026.
This contract fixes scope and what must not change before code. Design direction,
tokens and owner revisions live in `PRODUCT.md` and the Impeccable surface brief
`.impeccable/surfaces/frontend-src-app-tsx.md`; the signed-off mockup is the
private canvas "MarketLab revamp mockup".

## Scope

Phase 1 and 2 (this change):

- Self-hosted Geist and Geist Mono (`@fontsource-variable/geist`,
  `@fontsource-variable/geist-mono`, OFL-1.1). No remote font or asset requests.
- Black theme tokens, shell (ASCII wordmark, navigation with drawn icons, recent
  runs, path breadcrumb), command menu (Ctrl/Cmd+K and button) and shared parts:
  short IDs with copy, trading-pair pills, status pills, copyable worker commands,
  exact values with dimmed trailing digits.
- Catalog: summary strip derived from catalog rows, titanium day matrix
  (five equal-count tiers) as a second selection surface, selection bar, restyled
  versions table and verification panel.
- Run: workflow title with pair pills, window track, key figures, cross-asset
  comparison, explicit close-price chart, red/green price and volume chart,
  profile tables, volume spikes, memo and receipt.
- Remaining screens take the new tokens without structural redesign.

Later phases: research form, copilot thread, jobs, ingestion matrix, empty and
error states pass, finish review, DESIGN.md and README demo re-recording.

## Must not change

- No backend, API, schema or dependency change beyond the two font packages.
- Exact values: decimal strings and integer lexemes render as received; only
  client-side aggregates (catalog totals) are formatted. Null stays
  "Unavailable (null)" with its reason.
- Chart reads stay explicit: no `/v1/bars` request until the user asks, at most
  one bounded window per request, no hidden month fan-out. The close-price chart
  therefore loads on request, bounded to five days of five-minute bars.
- Polling, replay-safe operations, local-origin mutation guard, three-paragraph
  memo text rendering, and queued work only described, never started.
- Test hooks: existing `data-testid` values, accessible names and visible strings
  used by `tests/workspace.e2e.ts` stay, except the deliberate copy changes listed
  below, which update the test in the same change.

## Deliberate copy changes

- Navigation "Jobs & submissions" becomes "Jobs".
- Chart coverage line "N observed / M expected · K empty buckets" becomes
  "N of M buckets observed, K empty".

## Acceptance

Frontend typecheck, lint, component tests, build, and Playwright Chromium, Firefox
and WebKit pass with `PLAYWRIGHT_BROWSERS_PATH` set to the existing physical cache.
The redesigned screens are checked against the owned demo stack at 1440, 768 and
390 px with taste-skill's inspector and Impeccable's detector; findings are fixed
or reported.
