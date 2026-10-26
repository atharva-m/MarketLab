# MarketLab local research workspace

Use Node.js 22.12+ (CI uses Node 24) and the separately locked frontend packages:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite listens on loopback only, uses a strict port,
and proxies `/v1` and `/health` to the existing local API on port 8000. Start the
API and bounded ingestion/research/shared-inference CLI workers using the root
README. Browser submission does not execute a worker or schedule work. Existing
jobs remain durable after closing the page.

The test-only environment variable `MARKETLAB_R7_TEST_API_PORT=58007` selects the
owned acceptance API port. No other value is accepted. This is process
configuration, never a browser input or arbitrary URL proxy.

```powershell
npm run typecheck
npm run lint
npm test
npm run build
npm exec playwright -- install chromium firefox webkit
npm run test:e2e
```

Browser tests mock HTTP responses and are separate from actual retained-data,
model, outage and cold-workflow acceptance. The production build is generated
under ignored `dist/`; R7 does not change Docker/Compose or publish a site.

In the Windows packaged Codex environment, Firefox's logical default cache path
can fail SxS startup despite an intact bundle. The verified
[physical-cache invocation](../docs/r7-verification.md#windows-firefox-physical-cache-configuration-fix-october-26-2026)
sets Playwright's supported browser-path variable for one process/session and
restores it afterward. All 11 Windows Firefox cases passed with pristine binaries;
no DLL patch or global environment change is required.

Choose dataset versions explicitly in Catalog or paste their full identities in
the research form. Include history as well as evaluation. No latest version is
selected automatically. The server is authoritative for integrity and warm-up.
Research submission may spend several minutes validating before a durable run
identity is returned. A successful copilot interpretation queues a research run;
it does not mean numerical execution has completed.

The browser saves up to 20 operation keys and exact request bodies in the local
profile before POST. On an uncertain response, use **Retry saved operation** to
replay the same request. Reload never automatically submits. Discarding a saved
operation does not cancel work the server may already have accepted. Do not use
this unauthenticated local workspace on a shared/public network.

Active visible details poll every two seconds, back off to ten seconds for
transport/503 failures, pause in hidden tabs, and stop after 30 minutes. Permanent
errors need explicit refresh. Browser cancellation is not a durable-job cancel or
proof of upstream model cancellation. Numerical results and memo status are
fetched independently.

Tables preserve exact decimal strings and integer lexemes. Chart coordinates
are approximate; no research calculations occur in JavaScript. Load each chart
window explicitly, at most 1,440 buckets. **Use pinned versions for window**
selects only versions already pinned by that run, filtered by asset and UTC days;
review the IDs before loading. Missing bars stay empty. Generated memos render as
text paragraphs, with no executable HTML.

The Vite boundary rejects foreign Origins on proxied mutations. The new ingestion
adapter also validates local Host/Origin. This does not add authentication or alter
the retained direct API contracts. No database or model credentials enter the
browser bundle.
