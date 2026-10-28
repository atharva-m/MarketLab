# UI regression verification — October 28, 2026

The user requested regression coverage and thorough CI-aligned testing after the
UI changes, identifying the last commit without Claude co-authorship as the
known-working baseline. That baseline is `740b4851cdc3283d8f990e038b21f887b23cf6de`.
The tested starting HEAD is `59b49671aa6bdb6f0d09f17da5157b4ea5f133a7`; the changes
under test include all three subsequent commits, not only the main UI redesign.
This follow-up preserves the redesign, fixes confirmed regressions and adds
tests. The local acceptance below preceded the publication authorization recorded
at the end of this report.

## Completed backend and packaging checks

Backend source did not change from the baseline. The existing CI checks were
nevertheless exercised using locked dependencies and disposable resources:

| Check | Observed result |
| --- | --- |
| Windows Python 3.13.7 offline suite | 1,013 passed; 200 integration cases deselected |
| Windows real PostgreSQL suite | 200 passed, including locally available historical-input cases |
| Linux Python 3.13.18 offline suite | 1,012 passed; one Windows-only skip |
| Linux real PostgreSQL suite | 196 passed; four expected historical-input skips in the clean source copy |
| Ruff lint, formatting, strict mypy on both platforms | Passed; 187 formatted files, 50 typed sources |
| Compose configuration, Docker build and migrations | Passed in a separate test project |
| Packaged API health/dependencies/metrics | Passed with Redis healthy and after stopping only test Redis |
| Optional Redis outage semantics | Ready before outage; degraded with Redis down afterward |

The initial Linux offline invocation had 1,011 passes, one expected skip and one
failure because the minimal runtime image lacked Git, which the provenance test
requires. The disposable harness was corrected to include Git and the exact HEAD
history, then the complete suite passed as shown above. No application fix or
weaker assertion was used. The initial Windows check invocation failed before
tests because the sandbox denied uv interpreter-cache writes; its authorized
retry passed. Existing Starlette/httpx deprecation warnings remain visible.

## Demo coverage and CI

Seven new deterministic tests exercise the actual TypeScript camera helper:
viewport geometry, fractional cursor interpolation and cut boundaries, idle and
settling behavior, click lead and typing hold, scroll interruption, grouped
panning, explicit focus and camera bounds. The test uses the existing locked
TypeScript dependency and requires no media or rendering service.

The new CI demo job uses Node 24 and runs `npm ci`, `npm run lint` (including
TypeScript) and `npm test`. Locally, all 11 demo tests and lint/type checks passed
after a clean install on Node 22.19.0 and in a disposable Linux Node 24.22.1
container matching the CI major version. Linux output is retained in ignored
`artifacts/ui-regression-20261028/demo-node24.log`. An initial container copy-path
error prevented npm from seeing the lockfile; the corrected harness then passed
all three commands. The owned container was removed after its label and exit
status were verified. The first sandboxed Windows install failed with
`Exit handler never called!`; the authorized retry succeeded. No dependency lock,
demo runtime or media changes were needed. Independent read-only review found no
actionable issue in the demo tests or CI addition.

## UI verification

The regression audit found and fixed these issues:

- Catalog metadata stopped after 1,000 rows, hiding later registered versions.
  An explicit continuation loads another bounded batch of metadata.
- The same cutoff hid a run's pinned historical versions. The close-price chart
  now waits for every pinned ID, with explicit metadata continuation, error,
  retry and missing-version feedback. No expensive dataset verification is
  triggered automatically.
- Command-menu autofocus replaced the saved opener, losing focus on close. The
  opener is now captured before the menu renders. The clicked button is passed
  explicitly because WebKit clicks need not focus buttons; keyboard opening
  retains the previously focused element. The mobile icon-only opener also
  retains its accessible name.

The mobile test exposed a 544-pixel document width at a 390-pixel viewport.
Waiting for fonts did not resolve the Chromium failure. The cause was absolutely
positioned screen-reader-only table text escaping its scroll container. Giving
`.table-wrap` a positioning context contains that text while retaining internal
scrolling; the focused 390-pixel Catalog/Run test then passed. Speculative
navigation and ID-wrapper CSS changes were removed. The regression waits for
fonts and checks settled document width rather than suppressing overflow.

Linux Node 24.22.1 passed a clean frontend install, typecheck, lint, all 20 unit
tests and production build. Final copied source/configuration/test hashes match
the working frontend, including CSS. Two new component cases cover exact
decimal/int64 display and full-ID clipboard copy/failure behavior. Output and
hashes are retained in ignored
`artifacts/ui-regression-20261028/frontend-node24-final2.log` and
`frontend-node24-final2-source-hashes.json` in that directory. This final Linux
run includes the WebKit opener correction.

The initial expanded browser run had 32 passes and 25 failures: 19 Firefox launch
failures using the logical cache path, two focus failures, two mobile
layout assertions and two overstrict SVG whitespace assertions. The assertions were
corrected to test disconnected paths without requiring insignificant whitespace;
the application defects received fixes rather than weaker expectations.

An intermediate full run passed 65 cases and failed one WebKit focus case,
revealing the click-versus-focus distinction described above. After the explicit
opener correction, the final full run passed **66/66 cases in 33.2 seconds**:
22 each in Windows Chromium, Firefox and WebKit. Firefox used the documented
physical browser cache rather than the affected logical MSIX path. The final
post-fix Windows typecheck, lint, 20 component tests and production build also
passed. `git diff --check` passed. Independent read-only review found no remaining
blocking issue, including a separate rereview of the WebKit correction.

Eleven new browser scenarios cover day click/shift/drag selection and persistence,
ambiguous versions, command-menu keyboard/ID navigation and focus, worker-command
copy, explicit bounded chart paging/gaps, catalog/run metadata beyond 1,000
versions, lookup failure/retry, cross-asset sequential reads and exact profile
values, and 390/768/1440-pixel layouts. The existing first-submission test now uses
a controlled deferred response rather than a timing delay to check validating
versus unconfirmed state and prevent duplicate submission.

Frontend checks used a fresh isolated copy and owned Vite port 5178, not the
pre-existing UI server. Browser API responses are fixture-controlled, while the
separate PostgreSQL and packaged API checks above exercise real services. These
browser tests do not constitute a fresh model/month acceptance run. The foreign
origin rejection check remains exercised; mocked mutations on port 5178 are not
claimed as a live allowed-origin mutation test.

The first frontend `npm ci` attempt hit an existing `esbuild.exe` file lock;
the fresh isolated install succeeded. Missing original dependency files were
restored from the same locked install without overwriting existing binaries or
stopping existing processes. Original frontend `npm ls --depth=0` and typecheck
passed afterward. Sandbox Vitest temporary-file restrictions required an
authorized retry. The owned Vite listener was absent after Playwright exited.

## Scope of evidence

These acceptance results are local checks, including Linux containers, not a
hosted GitHub Actions run. No commit or push had been performed at local closeout.
The existing hosted workflow uses
Ubuntu and Node 24; Windows JavaScript checks use Node 22.19.0, with both frontend
build/unit checks and the new demo job additionally checked on Linux Node
24.22.1. This follow-up does not rerun historical model, full-month,
cold-performance or video acceptance and
does not replace those records. Passing tests cannot prove the absence of every
possible bug.

Backend test resources used the `marketlab-uiqa-20261028` project, separate ports
55448, 56388 and 58008, and image `marketlab-uiqa:20261028`. After verifying exact
project labels, its containers, volumes, network and test image were removed;
the separately labelled Linux test container was also removed. Existing service
identities, images, start times, restart counts and mounts matched the pre-test
snapshot after cleanup. Temporary evidence stays ignored under
`artifacts/ui-regression-20261028/`.

## Publication authorization — October 28, 2026

After local acceptance and independent review, the user explicitly authorized
committing and pushing these changes, checking hosted CI for the published
revision, and fixing actual failures through coder gpt-6.1-sol/high followed by
independent read-only reviewer gpt-6-astra/medium. The existing README GIF is
permitted; other artifacts, data, credentials, environments and weights remain
excluded from Git. No original-service deployment or unrelated change follows.
Publication and hosted results are pending at this authorization entry.

### Prior HEAD hosted failure observed before publication

[Run 40705114048](https://github.com/atharva-m/MarketLab/actions/runs/40705114048)
for `59b49671aa6bdb6f0d09f17da5157b4ea5f133a7` failed its Ubuntu offline job:
1,011 passed, one Windows-only skip, and one failure in
`test_spawned_workers_stop_after_owned_parent_death[active]`. The owned worker
exited while the test read `/proc/<pid>/stat`, producing `ProcessLookupError`
(`ESRCH`) rather than the already handled `FileNotFoundError`. The Windows
quality job was cancelled; its partial execution is not a pass. Frontend and
integration jobs succeeded. The ignored job log is retained as
`artifacts/ui-regression-20261028/prior-ubuntu.log`.

The prescribed coder implemented a test-only repair and the independent reviewer
found no actionable issue. Linux inspection now reads identity and state from
one stat snapshot and treats only `ENOENT`/`ESRCH` as disappearance. Permission and
I/O errors still propagate. Eight new deterministic cases cover disappearance,
unexpected errors, live/zombie/reused identities and a one-read assertion. The
real active/idle worker-death tests and deadlines remain unchanged; no Python
application runtime changed.

Post-repair validation passed 1,021 Windows offline cases and 1,020 Linux offline
cases plus the expected Windows-only skip, with 200 integration cases deselected
on each platform. Focused parent-death/pool/startup checks passed 29/29 on each
platform. Ruff lint/format and strict mypy passed on both. The first sandboxed
focused Windows attempt had eight passes and 21 temporary-directory fixture
errors; the authorized retry passed. Linux used the exact prior HEAD history
with the reviewed test overlay in an isolated container; its retained real
process evidence is ignored under `ci-fix-linux-evidence` in the evidence folder.
The exact owned container was removed after ownership checks; original services
remained untouched. Hosted validation of the publication remains pending.

### Publication and hosted CI verified

The 13 audited source/test/CI/documentation files were committed and pushed
normally to `origin/main` as
`a21a1992fa46ca6c10429b2632873ab33f889e42`.
[Hosted run 40721875385](https://github.com/atharva-m/MarketLab/actions/runs/40721875385)
completed successfully for that exact SHA. All five jobs passed:

- Ubuntu quality: 1,020 offline passes and one expected Windows-only skip.
- Windows quality: 1,021 offline passes.
- Integration: 196 real PostgreSQL passes and four expected historical-input
  skips, plus Docker build/migration/API/healthy Redis/outage/cleanup checks.
- Frontend: typecheck, lint, 20 component tests, production build and 66 browser
  tests across Chromium, Firefox and WebKit on Ubuntu.
- Demo: locked clean install, lint/type checks and all 11 tests on Node 24.

No further repair was needed in this published run. The earlier failed run and
cancelled Windows job remain historical failures; the later pass does not erase
them. Hosted job logs are retained under the ignored evidence directory with
`hosted-` names. The commit contains no artifacts, data, credentials, environments
or weights. The pre-existing README GIF was unchanged. Original local services
were not deployed or modified.

This documentation-only outcome update is published separately. Its exact-SHA
hosted CI outcome will be checked and reported in the session; the success above
applies specifically to `a21a1992fa46ca6c10429b2632873ab33f889e42`.
