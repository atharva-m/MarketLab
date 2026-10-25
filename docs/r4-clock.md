# Post-R4 clock follow-up: partial mitigation, then application claim fix

**Update October 25, 2026:** the remaining writer was attributed to Docker Desktop's
/initd, and the user authorized an application-level claim fix. See
[root cause and application fix](#root-cause-and-application-fix-october-25-2026).
**The backward-clock issue persists.** It was worked around at the application layer
(job claim logic) rather than fixed at the system level (Docker, WSL, host clock or
time-sync configuration). Everything
from here until that section is the October 24 record, and describes the code as it
was then.

Approved October 24, 2026 after R4 local closeout. The user authorized investigating
and fixing the measured clock limitation through the prescribed coder/reviewer
workflow, preserving R1-R4 and original services, with actual evidence and no
commit or push. This is not R5 authorization. The original
[R4 verification](r4-verification.md) remains historical evidence.

**The clock limitation is not fully fixed.** Large steps diminished after the guest
NTP conflict was removed and PHC synchronization converged, but dense sampling
still detected smaller Docker initd backwards steps. An exploratory command also
unexpectedly restarted original containers, violating the uptime-preservation
requirement. Earlier passing tests do not erase that incident.

## Preservation and selected intervention

Database time remains authoritative. Eligibility predicates, 60-second leases,
10-second heartbeats, three-attempt budgets, fencing tokens, stale-owner rejection
and atomic publication are unchanged. No runtime time clamp, eligibility bypass,
artificially past eligibility, hidden claim retry, schema or dependency change.

The only clock-configuration operation applied was stopping/disabling
Ubuntu-22.04 systemd-timesyncd.service at **21:29:49 UTC**, followed by systemd
daemon-reload. The reviewed purpose was to remove competing guest NTP while
retaining built-in Hyper-V/WSL synchronization. The selected Ubuntu intervention did not restart original services, but a later
initd exploration unexpectedly restarted their containers (see incident below).
No direct manual time/rate setter, clocksource switch or Windows time-service
change was issued. Original service identity/storage recovery and final resource
audits are recorded below; uninterrupted uptime cannot be claimed.

[Canonical's WSL guidance](https://ubuntu.com/wsl/docs/stable/explanation/time-sync/)
describes conflicts between guest NTP and implicit Hyper-V synchronization and
recommends disabling systemd-timesyncd for Ubuntu 24.04 and earlier when retaining
the default host synchronization. It supports this targeted configuration change;
the local measured evidence below is needed to assess its outcome.

## Diagnosis and refinement

Read-only configuration inspection found Ubuntu-22.04 systemd-timesyncd active
against Ubuntu NTP with 32-second polling, while implicit Hyper-V synchronization
was enabled. Ubuntu and Docker share the same kernel boot identity and clock
domain. Clocksource remained tsc throughout; no source switch was made.

The configured 120-second before window captured **10 native realtime backwards
steps** (minimum -1.311906s) and **10 PostgreSQL backwards steps** (minimum
-1.307014s), with 2,401 native and 2,309 database observations. Native RAW divided
by Windows QPC elapsed was 0.999995774; adjusted Linux MONOTONIC divided by QPC
was 1.072795151, approximately 7.28% fast. All 60 original API-health checks were
200. Raw native clocks and server-generated epoch/text observations locate this
below application datetime adaptation. The original probe used native fixed-count
sampling; its actual overlapping host span must be distinguished from the
configured 120 seconds. Later probe tooling measures a host-controlled span.

An independent pure-server PL/pgSQL loop earlier collected 6,000 clock observations
without a backwards step during approximately 66.31 database seconds. The symptom
is intermittent; that short non-reproduction does not invalidate the paired
before window or R4's earlier eligibility captures.

Stopping the Ubuntu daemon was **not an immediate complete fix**. The first
configured 600-second after window still recorded 20 native and 20 database
backwards steps; a separate 90-second stress run had two immediate-claim failures
among 9,269 attempts. Those failed partial results are retained.

Read-only timex inspection initially found tick 10597 microseconds and scaled
frequency 380210, prompting a stale-rate hypothesis. However tick subsequently
changed 10597 to 10175 to 9810 while the Ubuntu unit was disabled. A bounded
60-second trace captured 29 adjustment calls by global PID 154, chronyd. The
built-in WSL system environment reported PHC0 synchronization, rather than another
application process or Python timestamp conversion. This demonstrated active
adjustment and rejected the premise of a merely static stale tick value.

No proposed manual rate correction was applied. The built-in PHC synchronizer was
left intact and allowed to settle after the guest conflict was removed. Subsequent
tracking observations reported a reducing correction (approximately 2807 ppm,
then 2373/207/62 ppm); tick reached 10001 and reported host offset was tens of
microseconds. These are observations during convergence, not proof of permanent
clock stability or a claim that those intermediate rates were already acceptable.

## Completed workload verification and limits

The configured 660-second settled observation started at approximately 21:47 UTC
and completed before the incident below. It collected 13,201 native samples over
663.972138 Windows host seconds and 12,700 PostgreSQL samples over 659.7632612 host
seconds, with zero reversals at approximately 50ms sample spacing. RAW/QPC ratio
was 0.999999246; MONOTONIC/QPC was 1.000061346. All 326 API health samples were
200. This coarse result did not prove that smaller steps had ceased.

Already observed after settling:

- 1,000 fresh R2 and 1,000 fresh R4 submissions claimed immediately.
- The retained diagnostic completed 9,157 iterations in 90.002 seconds with zero
  claim failures.
- Real clock/claim/lease acceptance completed in 247.990 seconds. Both kinds
  passed replay and concurrent SKIP LOCKED cases. Retry eligibility gates were
  observed at 10.1872 and 30.2436 seconds. Three genuine lease-expiry cycles took
  60.00685, 60.19510 and 60.20664 seconds; six heartbeats per kind followed the
  ten-second cadence. Stale mutations and a fourth attempt were rejected.
  The owned test schema was removed and public table counts remained unchanged.
- Locked offline tests passed 655 cases in 10.73 seconds; strict mypy passed 31
  sources. The retained real PostgreSQL suite passed 152 cases in 49.19 seconds.
  Final tooling/documentation checks and independent review are recorded at
  closeout; none changes the unresolved dense-step result.
- R1-R4 application-source fingerprint remains d868cec2d64ae53661ff2bcd716f8b09a8ee89c99c3c8e754835cec0f899bc7c.

Evidence is retained under ignored artifacts/r4-clock. Probe tooling selects an
explicit existing observer image, never pulls, verifies observer ID/name/ownership
before removal, records partial evidence on failure and uses host time to measure
the requested observation span. It does not alter any clock or job.

## Finer observation still unresolved

Later coarse 50-millisecond observations reported no realtime reversals, but a
finer helper observed a persistent approximately 2.44-millisecond decrease in the
REALTIME-minus-MONOTONIC offset. A function trace identified Docker initd global
TIDs 322/283 calling settimeofday at approximately 30-second cadence, distinct
from the earlier chronyd rate adjustments. The dense 90.000033s probe with 499,311
observations detected three actual backwards steps, worst -1.547479ms. Evidence
is dense-native.json and clock-step-trace.txt. No supported Docker synchronization
fix has been applied.

Therefore the zero-reversal coarse samples must not be reported as proof that all
clock steps ceased: this is partial mitigation, not a completed fix. No direct
manual clock/rate correction or supported Docker synchronization change was
applied. The unrelated exploratory incident below must also be reported.

## Actual observation spans

Configured durations are not substituted for measured windows. The native stream
used the original fixed-count sampler for the first three windows; the repaired
helper uses Windows host-controlled termination and verified owned cleanup.

| Window | Native host span (s) | Database host span (s) | Native MONOTONIC / RAW |
| --- | --- | --- | --- |
| Before, configured 120s | 116.7319537 | 119.7649508 | 1.072799685 |
| First after, configured 600s | 599.3352479 | 599.7853448 | 1.019678758 |
| Settled, configured 660s | 663.9721380 | 659.7632612 | 1.000062100 |
| Repaired helper, configured 30s | 30.1036781 | 29.6573317 | 1.000037923 |

Evidence: window-summary.json. The repaired helper smoke verified its observer
ID/name/ownership before removal and had 15/15 HTTP 200 health samples. This is
tooling/cleanup evidence; approximately 50ms samples cannot rule out 1ms backwards
steps, so neither that smoke nor coarse zero-reversal windows negate the dense
negative evidence.

## Operational incident and recovery status

At 21:58:21 UTC, the agent ran nsenter -t 62 -m /initd --help expecting help output.
The binary instead attempted VM initialization and failed against the existing
services namespace. Original containers stopped at approximately 21:58:35.647 UTC
and restarted at 21:58:37.45 UTC with the same IDs and volumes. The owned probe
PostgreSQL exited with status 255; the WSL boot ID remained unchanged.

This was an unintended operational interruption caused during investigation. The
no-restart/uptime constraint was not met. Do not describe it as harmless help
inspection or claim continuous original-service availability. No further initd
help or VM-init experiments are permitted. The retained test and coarse probe
passes preceded this event and do not prove post-incident data preservation.

The automatic container cycle did not restore usable host forwarding: Docker
backend logs showed stale addresses (API .2 to .3, PostgreSQL .3 to .4, Redis .4
to .2). The initial two-second container cycle is therefore not the total service
availability gap. Standard recovery restarts of the same containers were required:

| Original service | Recovery container StartedAt UTC |
| --- | --- |
| API | 22:02:04.538588572 |
| PostgreSQL | 22:02:56.624983827 |
| Redis | 22:03:10.874684336 |

Final inspection confirmed the same original IDs, images and volumes, running and
healthy. Host API live/ready/dependencies were 200 with PostgreSQL/storage/Redis
up and optional Ollama down; Redis host PING succeeded. Read-only original database
inspection found the retained 0002_trades schema and zero trades. Original API
OpenAPI exposes health routes only, so its /trades 404 was consistent with that
image, not a new route regression. These checks are recorded in recovery evidence
and final-original-services.txt. They do not constitute a fresh full 62-partition
historical-data readback. Uptime was interrupted; Redis cache continuity was not verified and is not
claimed; the incident remains a failed preservation requirement.

Owned cleanup verified the exact stopped probe PostgreSQL ID/name/ownership label
before removing it. The clock-owner container inventory and owned tracefs-instance
inventory were empty afterward. Original services were not removed. No further
service action or VM-init exploration followed the recovery.

## Final outcome and remaining limitation

This is partial mitigation, not a completed clock fix. Guest NTP was disabled and
large distortions diminished after built-in PHC convergence; unchanged real job
workloads passed, but Docker initd still generated dense-sampling backwards steps.
No supported safe live Docker control for that writer was identified. Built-in
PHC synchronization remains intact; any later Docker/vendor maintenance decision
requires a separate reviewed operational plan.

The helper's approximately 50ms sampling resolution is material: zero adjacent
negative samples cannot exclude shorter clock steps or persistent offset
corrections. Its successful 30-second cleanup smoke and the long coarse window
must not supersede the denser negative evidence.

Disabled-unit state after daemon-reload was verified. No deliberate reboot was
performed to test persistence. Final source-preservation evidence reconfirmed
application fingerprint d868cec2d64ae53661ff2bcd716f8b09a8ee89c99c3c8e754835cec0f899bc7c,
lock 730f02bec94d1f824a2cadf74f60cf5dcc246faa55004d5d060b92931224618f and
unchanged HEAD 111d3b8695573e43ac56c813c2b45e0781e86843. Source/eligibility/fencing
semantics were not edited to obtain passing checks. Historical
[R4 acceptance](r4-verification.md), failed partial attempts and this incident
remain retained. No commit/push, R5-R9 expansion or manual rate reset occurred.

## Root cause and application fix (October 25, 2026)

### Status: issue persists, application-layer workaround

**The backward-clock issue persists.** Docker Desktop still steps the shared WSL2
clock backwards about every 30 seconds, and PostgreSQL `clock_timestamp()` still
observes those steps. The workaround is at the application layer: R2/R4 job claim
logic no longer assumes database wall time is monotonic.

No system-level fix was attempted. Docker Desktop, WSL, the host clock, Windows time
service, chrony and timesyncd were left as they were. That level has no supported
control for this writer, and the earlier exploration there caused the incident
recorded above.

### Attribution

Environment: Docker Desktop 4.92.0 (engine 29.8.0), WSL 2.4.12, kernel
5.15.167.4-microsoft-standard-WSL2. The settimeofday writer traced above (Docker
initd TIDs 322/283, ~30s cadence) matches publicly reported Docker Desktop behaviour.
/initd in the docker-desktop distro steps the single shared WSL2 VM clock about
every 30 seconds, usually 1-2ms backwards
([docker/desktop-feedback#761](https://github.com/docker/desktop-feedback/issues/761)).

- That thread has no maintainer fix and offers no setting to disable the correction.
- Reporters found `hv_utils.timesync_implicit=0` ineffective. Only quitting Docker
  Desktop stops the steps.
- Reports for 4.95/4.96 describe larger steps (about 5-32ms), so upgrading is not a fix.

No Docker, WSL, host-clock, timesyncd or original-service change was made.

Fresh measurements on October 25:

- **Dense native probe** (same dense_native.py, Ubuntu-22.04): 515,085 samples over
  90.000104s. Three backward steps, -1.844905, -1.692398 and -1.383656ms, 29.999s
  and 30.001s apart. Evidence: clockfix-dense-native.json.
- **Server-side clock_timestamp() loop** on the owned database: 407,800,000 samples
  over 90.016148 database seconds. One backward step, -1.344ms. Evidence:
  clockfix-server-dense.sql/log.
- **Conclusion:** database time itself is not monotonic.

### Why the application failed

Submission wrote `eligible_at = clock_timestamp()`. A later claim transaction then
required `eligible_at <= clock_timestamp()`. A backward step larger than the gap
between submit and claim made freshly queued work unclaimable. The synchronous R1
path then raised "inline ingestion job is not eligible", and an immediate R4 worker
returned zero runs.

The synchronous retry path had the same weakness. It sleeps on the host for the
database-computed remaining delay and then claimed only once, so it failed whenever
database time had not yet reached eligibility.

### Change (claims only, user-authorized)

- **Queued claims.** In R2 `jobs.claim` and R4 `store.claim`, `queued` work is
  eligible without a later wall-clock comparison. `retry_wait` still requires
  `eligible_at <= clock_timestamp()`, and expired running work still requires
  `lease_until <= clock_timestamp()`. `queued` is written only by submit, with
  `eligible_at = created_at = now`, so the change is behaviour-identical except for
  the clock-step case. `eligible_at` remains recorded.
- **Synchronous retry recheck.** When a due-looking `retry_wait` claim returns none,
  `ingest_day` re-reads persisted eligibility and the database-time delay at most
  three times per attempt, then raises "not eligible". Running/unexpired, terminal or
  locked jobs still raise as before.
- **Unchanged:** 60s leases, 10s heartbeat, three attempts including crashes, fencing
  token increments, stale-owner rejection, SKIP LOCKED, generic-worker source/contract
  filters, fenced atomic publication, schema, migrations, dependencies and lock.
- **Worst case:** if database time stalled entirely, one synchronous retry gap could
  now wait up to four times its remaining delay. That is still bounded, by the three
  rechecks and the existing 3600s cap.

### Verification

All verification ran on an owned disposable PostgreSQL:

- Container `marketlab-clockfix-pg-20261025`, ID d2d0c524933254f70262c01d0ca41571fdf3033cf3121fdf6ee3017c06d399e4.
- Image postgres:17-alpine eee6c6e1b089, no pull, loopback 127.0.0.1:55436.
- Label marketlab.clock.owner=clockfix-20261025, migrated to 0005_research.

`uv` was not on PATH in this shell. Checks therefore ran from the project .venv
(Python 3.13.7, same pytest plugins as the earlier logs), with uv.lock hash 730f02be…
unchanged.

- **Ruff and format:** clean (96 files). Strict mypy passed 31 sources.
- **Offline:** 655 passed.
- **Real PostgreSQL:** 158 passed (152 retained + 6 new). Evidence:
  clockfix-integration-final.log, clockfix-offline-final.log.
- **New deterministic regressions** use no real clock step:
  - A queued R2 job and R4 run with `eligible_at` one hour in the future (equivalent
    to a backward step) are claimed with attempt 1/token 1. After a transient
    failure the future `retry_wait` is still not claimable.
  - `ingest_archive` succeeds end to end after a post-submit backward step.
  - `ingest_day` rechecks when database time trails the host sleep, then succeeds with
    attempts transient/succeeded and token 2.
  - The recheck is bounded: exactly four waits, then "not eligible", with the job left
    in retry_wait/attempt 1.
  - Resuming an unexpired owner is still not eligible.
- **Relaxed test bounds:** three upper bounds on DB-time deltas gained +1s slack for a
  backward step after the write: lease 60 to 61, retry 10/30 to +1, Retry-After 120
  to 121. The lower bounds are unchanged.
- **Live stress (claim_fixed.py):** over 180.001 host seconds, all 4,901 R2 and 4,900
  R4 submissions were claimed immediately with zero unclaimed. However, no backward
  step fell inside a submit-to-claim gap: there were zero backward-since-submit
  observations, because ~18ms iteration spacing exceeds the ~1.5ms steps. This run
  shows no regression under real steps; the deterministic cases are what demonstrate
  the fix. Evidence: clockfix-claim-stress.json/log.
- **Clock acceptance:** `r4_clock_acceptance.py --after-fix --port 55436 ...` passed
  in 268.266s:
  - 1,000/1,000 immediate claims per kind. The queued predicate makes these pass by
    design, so this is not clock evidence.
  - Replay/conflict/SKIP LOCKED cases passed.
  - Retry gates were observed at 10.0127 and 30.1390s.
  - Three genuine lease-expiry cycles took 60.0120, 60.2014 and 60.1816s.
  - Six heartbeats per kind followed the 10s cadence.
  - Stale mutations and a fourth attempt were rejected.
  - Public counts were unchanged and the owned schema was removed.

  Evidence: clockfix-acceptance-complete.json/log. The script's fixed output names
  initially overwrote the October 24 acceptance-complete/progress files. They had been
  copied beforehand and were restored byte-identical (SHA-256 1c7264d6… and ebcc3de5…;
  *.20261024.json copies kept). The script now takes `--evidence-prefix`, refuses to
  overwrite completed acceptance evidence, records its arguments and resource ID, requires a
  loopback binding and keeps record files inside artifacts/r4-clock.
- **Final-tooling acceptance:** a rerun with `--evidence-prefix clockfix-final-`
  passed in 269.881s:
  - 1,000/1,000 claims per kind.
  - Retry gates at 10.2382 and 30.1786s.
  - Lease cycles of 60.1089, 60.1065 and 60.2375s.
  - Twelve heartbeats with no failures, and resource ID d2d0c524… recorded.

  The default-name invocation refused to overwrite completed acceptance evidence, and a record
  path outside artifacts/r4-clock was rejected. Evidence:
  clockfix-final-acceptance-complete.json/log.
- **Cleanup and preservation:** the owned container was removed by ID after its ID,
  name, owner label and loopback binding were verified, and the clock-owner
  inventory is empty. The original API/PostgreSQL/Redis containers kept identical IDs,
  identical October 24 StartedAt times (22:02:04, 22:02:56, 22:03:10 UTC), zero
  restarts and healthy status. API /health/live and /health/ready returned 200.
  Evidence: clockfix-original-services-before/after.txt, clockfix-owned-cleanup.txt.
- **Independent review:** a read-only Claude subagent reviewed the diff, replacing
  the unavailable coder/reviewer models at the user's choice. It found no blocking
  issues. Its should-fix items were the evidence overwrite and docs still claiming
  unchanged eligibility; both were resolved. Its nits were also applied: a one-hour
  future offset, an end-to-end ingest_archive case and the missing slack comment.

### Remaining limitations

- The backward-clock issue persists at the system level. Only the application-layer
  workaround is in place; no system-level fix was attempted.
- In the acceptance script, `retries()`/`leases()` still claim immediately after
  waiting for database time. A millisecond step inside that window could still fail
  an assertion. This is pre-existing tooling behaviour and rare.
- Peak memory is unmeasured. At application-fix closeout hosted CI was unrun and
  publication was excluded; the fix sat on the user's local backup commit f600ccb.
  The later publication authority below supersedes that restriction. R5-R9 remain
  unauthorized.

## Fresh verification and publication authority (October 25, 2026)

Fresh locked verification passed 655 offline/158 real PostgreSQL tests, including
the six deterministic clock regressions. Independent gpt-6-astra read-only review
found no blocking source issue. Live acceptance passed in 249.827s: 1,000 immediate
claims per kind, concurrent replay/conflict/SKIP LOCKED checks, real 10s/30s retry
gates, twelve successful heartbeats, three real 60s lease-expiry cycles,
stale-worker rejection and the three-attempt limit.

The application works as intended with the known Docker clock discrepancy. A
separate server-only clock loop collected 409,100,000 samples over 90.021s and
captured three backward steps, largest 2.788ms; no system clock fix is claimed.
Retry gates and leases still use database wall time, and bounded rechecks do not
guarantee progress under arbitrary sustained reversal.

Evidence remains ignored under artifacts/r4-clock/verify-20261025-2250dfb0-*.
The owned database on loopback 55437 and its acceptance schema were removed after
ownership checks. Original service IDs/images/start times/restart counts/health
matched the baseline; API live/ready returned 200 and Redis PING returned PONG.
The harness's first launch stopped before acceptance because the newly written
resource record was an object rather than an array; correcting only that evidence
record allowed the completed run. Sandbox cache-permission failures also preceded
the successful locked test invocations; their logs remain retained.

The user then authorized committing/pushing verified R4 and the application clock
fix and checking hosted CI. This supersedes earlier publication restrictions for
that scope only. Hosted CI is pending; its exact revision/run outcome belongs in
[R4 verification](r4-verification.md). Historical failures and the October 24
preservation incident remain recorded above. R5-R9 remain unauthorized.
