# Post-R4 clock follow-up: partial mitigation

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
