# R9 verification and actual outcomes

## Publication and hosted CI (October 27, 2026)

Verified R9 was committed and pushed normally to origin/main as
`46a5896f4410ca0a5cff63e0009ad46a15dd8a09`, with 39 audited source/test/tooling/docs
files. No raw artifacts, data, archives, credentials, environments, weights or
generated media were included. Independent publication review found no blocker.
The initial sandbox staging command was denied index-lock access; the authorized
escalated staging succeeded. A staged EOF blank line in project-history.md was
removed by the coder and independently reviewed without changing historical text.

[Hosted run 40586299234](https://github.com/atharva-m/MarketLab/actions/runs/40586299234)
passed for that exact SHA. Actual logs record:

- Ubuntu: 1012 offline passes, one explicit Windows classic-path preflight skip,
  200 integration cases deselected (44.46 seconds).
- Windows: 1013 offline passes, 200 integration cases deselected (67.46 seconds).
- PostgreSQL: 196 passes and four explicit retained historical-source input skips,
  1013 cases deselected (74.63 seconds). This is not 200 hosted PostgreSQL passes.
- Frontend: type/lint/build, 18 component tests and 33 Chromium/Firefox/WebKit cases
  passed; the browser suite took 50.7 seconds.
- Existing Docker config/build/start, API smoke, optional Redis outage and owned
  hosted cleanup steps passed. No R9-related CI failure or repair was needed.

Run/job metadata and completed logs are retained locally under
artifacts/r9-20261027/r9-publication-first-final-*. Hosted CI does not execute the
isolated demo project's tests/render or local model/month/cold/GPU/video acceptance.
The local six-case historical-source gate and every local failed invocation remain
separate evidence. Original services were not changed during publication.

This observed-outcome documentation is being published separately; its hosted CI
will be checked for its exact SHA and reported in the session without treating the
first run as proof for the later commit.

## Local closeout and publication-approval checkpoint (historical)

The user subsequently authorized publication on October 27, 2026: commit/push the
verified R9 changes, check exact-SHA hosted CI, fix actual R9-related failures
through the prescribed coder/reviewer workflow, and document/publish observed
outcomes. Raw artifacts/data/credentials/environments/weights and generated media
remain excluded. Publication/hosted validation are pending at this entry; the
local acceptance statements below retain their original scope.

LOCAL ACCEPTANCE COMPLETE. The user approved R9 on October 27, 2026, including
the detailed plan, authority updates, a full contract before code, prescribed
coder gpt-6.1-sol/high and independent read-only reviewer gpt-6-astra/medium,
implementation and actual acceptance. The initial acceptance approval excluded
commit/push; the publication approval above now governs.
The [contract](r9-handoff.md) was written before R9 tools or demo code.

Evidence is retained outside Git under artifacts/r9-20261027. No prior R8 result
is counted as a new R9 acceptance pass. All mandatory local gates now have actual
passing evidence, with failed/incomplete invocations retained below. No R9 commit,
push, hosted CI result or original-service deployment is claimed.

Final deliverable: [180-second GPU-rendered demo](../artifacts/r9-20261027/r9-demo-final-gpu-second.mp4).
The local editable project and reproduction instructions are in
[demo/README.md](../demo/README.md). Captions, transcript and asset mapping are
retained in artifacts/r9-20261027/r9-video-prepared-second. Media and raw evidence
remain ignored local artifacts, not Git content.

## Baseline and publication reconciliation

Published base: 12ada75dddae926377d0ccc4f8cfe639e203098c. Its
[hosted run 40560664674](https://github.com/atharva-m/MarketLab/actions/runs/40560664674)
was observed completed successfully with frontend, integration, Ubuntu quality
and Windows quality jobs all successful. This resolves the earlier documentation
publication status without inventing test counts from job conclusions. Raw run/job
metadata is retained as r9-r8-documentation-status-run.json and -jobs.json.

The fresh clones carried audited uncommitted source-only R9 overlays, with
separate base SHA, file hashes and per-invocation execution identities. They are
not pristine published R9 revisions.

Initial original-service inventory found the same API, PostgreSQL and Redis
containers running and healthy. Full inspection and process inventory were saved
before creating owned resources. The fresh protected-file baseline contains 287
files, including retained datasets/research/memos, configuration and locks.
This is a new measured interval; it does not resolve the historical uptime gap.

## Invocation failures and limitations

- Initial sandbox Docker inspection was denied access to the named pipe. The
  explicitly escalated read succeeded; no service restart occurred.
- Initial sandbox Git credential lookup failed with a Windows MSYS permission
  error. The escalated read-only CI query succeeded. Credentials were not printed.
- One exploratory path lookup used an absent legacy filename; subsequent reads
  used the actual files. This did not execute acceptance or change application state.
- r9-clone-first failed in the sandbox's Git/MSYS startup. r9-clone-second
  succeeded with escalation; no environment or secrets were copied. Its first
  locked installation failed to persist the sandbox interpreter cache; the
  escalated locked installation succeeded.
- r9-fresh-checks-first passed lint/format/mypy and 1001 offline cases, but six
  verifier-pool cases failed with overlong native control-marker paths in the
  nested checkout (including a direct FileNotFoundError). No runtime/timeout or
  system long-path setting was changed.
- r9-fresh-checks-second used shorter temporary paths but lacked their parent:
  668 cases passed and 341 fixture setups errored. The harness now creates the
  parent and has a real subprocess pytest temporary-file regression.
- r9-retained-copy-first failed opening the first destination manifest because
  the nested checkout/storage path exceeded Windows' path budget. Partial owned
  directories and the failed receipt remain retained. Reviewed tooling now uses
  short artifacts/c/<hash> clone paths and preflights every copied destination
  before creating storage. r9-short-copy-second passed with original/destination
  hashes reconciled in the short clone.
- The first frontend command label test:e2e created an NTFS alternate data stream
  for its log. The actual command passed; its log was recovered without changing
  execution into a normal file with a separate receipt. The harness now sanitizes
  filenames while retaining the original command label.

## Observed gates so far

Path A passed in 53.0043165 seconds in the independently installed second clone:
official BTCUSDT January 1 ingestion/readback, same-key replay and fresh-key source
recheck reused version 0754cbedca540cf372ee8d0f11b5ba9cf15f5b91536d33ec2187d02a2aec4d53.
Its database was dumped, verified quiescent, renamed to marketlab_path_a and
preserved; a separate empty marketlab database was created for Path B. No
publication timestamps or terminal states were rewritten to match retained history.

The second-clone frontend passed locked type/lint/build, 18 component tests and
33 real Chromium/Firefox/WebKit cases (12.7 seconds browser test report), with
the documented process-only physical browser-cache path. These results remain
separate from subsequent live browser and data/model evidence.

The shorter third clone is artifacts/c/76e0e0ae. It received a newly installed
locked Python environment and locked frontend dependencies. Its offline suite
passed 1012 cases, with 200 integration cases deselected, in 69.69 seconds;
real PostgreSQL verification passed 196 cases with four explicit historical-input
skips (1012 deselected) in 148.16 seconds. The separate four-case historical-source
gate was still required at that checkpoint; its subsequent pass is recorded below. Runtime source
identity remains the unchanged adopted 66069d6a fingerprint; each harness revision
and source overlay is recorded separately.

The isolated Remotion setup produced a three-second labelled test-pattern render,
verified local media playback and process-scoped external-network rejection.
These were tooling prerequisites only; final product footage/render acceptance
was pending then and is recorded in the final closeout below. The first failed
network probe is retained separately.

## Mandatory gates

The finalized harness checkpoint passed lint, format over 184 files, strict mypy,
1013 offline cases (200 deselected, 64.52 seconds), and 196 real PostgreSQL cases
(four explicit historical-input skips, 1013 deselected, 154.05 seconds). The
separate six-case source-compatibility pass supplies the external historical-input
coverage; it is not folded into a fictional 200-pass bare-checkout result.

`r9-failure-first` passed: cache HIT became BYPASS during the exact owned Redis
outage, Redis recovered, and manual numerical results/summary remained exact.
The unavailable-model memo entered native retry_wait after attempt one; this is
an observed safe failure, not a successful memo. No retry deadline was forced.

`r9-manual-worker-first` passed normal bounded CLI execution of the browser-created
run, with one attempted run and numerical attempt one. Result hash
3669b7e1e136f778e045bd274b274bb77b8de4f725e5bfa1555fc92f44c62619 and summary hash
72ed7f5d14a770ac58be86816f8a95e5733a79d321e9c6cbe80c377878592dd7 match the exact
independent full BTC profile reference. Worker execution took 138.8024325 seconds;
the whole inspect/execute/readback wrapper took 143.7031805 seconds.

`r9-model-first` passed the prospectively frozen clear-01, adversarial-01 and
complete-answer clarification cases with four actual copilot responses and one
fresh memo response. Clear submitted; adversarial was unsupported with no run;
clarification advanced from needs_clarification revision zero to submitted revision
one. Every revision and the ready memo used one attempt/call. Create/answer replay
assertions preserved their durable identities. This is targeted integration
evidence, not a new model-quality estimate. Independent review matched every memo
number and all three grounded paragraphs to the supplied numerical summary.

`r9-manual-ui-second` passed exact form submission (201), reload without a second
mutation, and same-key/body replay (200) to the same run. Its separate bounded
worker execution is recorded independently. `r9-retained-ui-first` passed five
retained scenario/memo readbacks and exact bounded cross-day chart checks.

`r9-packaged-first` passed in 10.8576835 seconds: 1,151,908 rows, twelve five-minute
bars, exact native reference hashes, closed verifier and no remaining children.
Its exact owned container and image were removed and separately confirmed absent
by ID. Existing images and original services were not modified.

`r9-research-first` passed ten retained run readbacks covering five scenarios,
then three fresh executions covering market_profile, cross_asset and
volatility_cluster. All fresh numerical payloads and hashes matched independent
references. `r9-retained-memos-first` passed five retained three-paragraph memo
hash/readback checks with zero model calls.

`r9-observe-first` passed live/ready/API metrics, durable collector and separate
normal inference CLI-worker telemetry. The bounded CLI worker reported one job;
its model result is distinct from this telemetry gate. `r9-legacy-first` passed
actual legacy HTTP/CLI preservation using synthetic records in the owned database.

The first manual UI invocation received 503 before durable submission: the owned
API bootstrap lacked a Windows spawn main guard, so verifier children attempted
to bind the API port again. Read-only reconciliation found zero submissions for
the recorded key. The prescribed coder repaired only the ignored bootstrap;
independent review cleared it. The original helper, failed browser receipt and
logs remain retained. Production source was unchanged.

`r9-source-compat-second` passed all six actual PostgreSQL cases in 48.61 seconds,
including four required external historical-source cases. The separate 196-case
bare-checkout result above remains 196 passes plus four skips.

`r9-cold-first` passed in 262.699995999923 seconds including its service-close
boundary. All 62 partitions reconciled 230,311,900 trades and exact reference
hashes, with one numerical attempt. Memo remained queued with zero attempts/calls;
active children after close were empty. Cold means fresh application/verifier
state and empty owned Redis, not a flushed operating-system cache. No video
capture, rendering or model workload ran concurrently with this gate.

The first separate source-compatibility invocation passed two cases and failed
four fixture setups because the generated module was outside tests/conftest.py's
scope. A reviewed harness-only import exposes the original dataset_engine fixture;
the original identity, retry, no-dispatch and readback assertions remain unchanged.
Its regression reverse-reconstructs the original source and resolves fixtures with
real pytest setup-plan. The failed invocation remains retained.

The first empty UI invocation received an actual 503: the isolated launch script
overrode its private database URL password with an empty password. Correcting the
launch environment and restarting only identity-checked owned API/UI/collector
processes produced r9-empty-ui-second, which passed the real empty-catalog check
with no mutations or browser errors. Two conservative PowerShell timestamp checks
refused the restart without stopping processes; the existing Python guard compared
the exact normalized birth timestamps successfully. Original services were untouched.

All five final capture invocations passed their real browser readback checks.
They record accepted completed R9 states, with the catalog explicitly using
restored retained inputs; they do not replay inference live. Final Remotion
composition/export and complete playback/visual QA were still pending at this
capture checkpoint; their subsequent passes are recorded below.

All 287 protected artifact/configuration hashes matched the original baseline
both after acceptance and after application-resource cleanup.

The first cleanup invocation failed preflight on four unrecognized Windows
console-host descendants, with no process stops or container removals. A read-only
diagnostic pinned their exact child/parent/root identities and birth times. The
prescribed coder prepared a separate helper, independently reviewed before the
second invocation; the first script, failed receipt and log remain unchanged.
`r9-final-cleanup-second` passed: thirteen exact owned process identities verified
ended (five explicit stops; eight exited after their guarded parent stops),
two owned containers and their disjoint anonymous volumes removed, all seven owned
ports absent, and prior worker/API launcher identities verified absent or safely
distinguished from later PID reuse. No images, networks or disk evidence were pruned.

The final binary database dump is 83,321 bytes, SHA256
05d6c8b9fddebf876458ae6add62f30e1ebe7e71293c0c042902f08fc243c788; pg_restore listing
verification passed. The earlier Path A dump remained byte-identical. Original
API/PostgreSQL/Redis container IDs, images, mounts, start times, restart counts,
health and endpoints matched before/after, as did the original image-ID set.
This measured interval does not erase the historical uptime gap.

The first full Remotion export encoded 5,400 frames at 1920x1080/30fps (180 seconds),
7,454,339 bytes, SHA256
47de60c7897b0b90282f43f59a00c26cf4438e93edebb420dd9874e04eadbb78.
Its complete playback passed with all 5,400 frames decoded, zero dropped frames,
no media errors and closed browser/server resources. Visual review of the complete
sampled timeline found an actual crop-mask defect: source pixels outside declared
crop rectangles could show, and provenance had an asymmetric black area. Independent
review confirmed it. This first export remains playback-passed but visual-QA-failed;
its media, receipts and frames are preserved. A corrected video-only render and
final video-process/independent closeout results are recorded below.

The user subsequently requested the dedicated GPU for rendering/export. The
installed RTX 4070 Laptop GPU and driver 596.36 were detected without changing
drivers or global settings. A local bundled-FFmpeg probe actually initialized
NVENC 13.0 on GPU 0 and encoded thirty 1080p frames. Its first synthetic color
probe failed because the bundled build lacked that filter; the second used the
existing local setup clip and passed. A subsequent actual-footage GPU preview
passed in 6.1057119 seconds: the same render browser reported the RTX 4070 through
ANGLE/Direct3D11 in SystemInfo and WebGL, with GPU compositing/rasterization enabled;
actual encoder arguments selected h264_nvenc, GPU 0 and 8M bitrate. Required hardware
acceleration rejects silent software fallback. Independent review cleared the
corrected crop mask and this process-local GPU path. The full corrected export and
its QA are tracked separately; these probes do not establish an end-to-end speedup.

The corrected full GPU export encoded successfully as
`artifacts/r9-20261027/r9-demo-final-gpu-second.mp4`: 180 seconds,
1920x1080 at 30fps, 5,400 rendered/encoded frames, 23,116,608 bytes, SHA256
184a6fb2ae1c6c6166c5cef6c1d63736ced9cef3520fe321e15b20b33bd3bf4f.
Its receipt records the actual NVIDIA render-browser adapter, NVENC GPU 0 encoder
arguments, required hardware acceleration, and eighteen demo source/lock hashes
unchanged across rendering. Elapsed time was 284.4113429 seconds versus the first
software export's 268.5894343 seconds. Different crops and bitrate make that an
uncontrolled comparison; no end-to-end speedup is claimed.

Corrected-video playback passed all 180 seconds/5,400 frames with zero dropped
frames, no media errors and closed review browser/server resources. Some
browser-canvas sample views appeared to omit header/disclosure text; later views
were inconsistent and the exact underlying cause is not established. Direct
native decoding confirmed the MP4 contains that text. The final QA path therefore
uses native PNG samples rather than relying on browser-canvas video extraction.
A default native null-output invocation failed on the unavailable wrapped_avframe
encoder and a standalone select-filter sampling invocation also failed; their
logs remain retained. Explicit rawvideo/null decoding passed all 5,400 frames.
Reviewed reuse of the prior playback receipt requires the identical MP4 hash,
completed playback without errors, and closed resources. Native sampled visual
review and final media-process cleanup subsequently passed as recorded below.

After the GPU export, another read-only original-service/image comparison passed,
and all 287 protected hashes again matched the baseline. No driver, global GPU,
clock, Docker/WSL or original-service configuration changed.

## Final video QA and closeout

`r9-demo-review-native-fourth/playback.json` passed: identical final MP4 and
hash-pinned prior full playback, all 5,400 frames natively decoded, 192 native PNG
samples (every second and both sides of chapter cuts), sixteen contact sheets,
closed browser/server resources and no cleanup errors. All sixteen sheets and
six full-resolution chapter frames were visually reviewed. Caption/evidence
mapping, readable numbers, three memo paragraphs, framing and disclosures passed;
independent review confirmed representative native frames and image hashes.
This is full automated playback plus sampled visual review, not a claim of
continuous human viewing of every frame. The three later QA-source pins remain
separate from the eighteen render-time pins; only the QA extraction script changed
after export, not the composition, encoder or final MP4. Additional native-frame
sandbox/retry and probe failures remain in the [demo evidence account](r9-demo-research.md).

`r9-demo-visual-review-gpu-second.json` records the final visual pass.
`r9-video-process-closeout-reconciled-final.json` records media-process cleanup.
Its preceding needs-inspection receipt is preserved: historical PID 23396 had been
reused by an unrelated Codex node_repl.exe, with a later birth time and different
executable. That unrelated process was not terminated. Recorded render/QA process
identities and owned media listeners were absent after closeout; fast native QA
processes that exited before birth sampling use explicit post-exit command-absence
evidence rather than invented PID identities.

Independent final technical review found no unresolved blocking finding. The
prescribed coder/reviewer workflow reviewed source, actual acceptance, model/memo
facts, video mapping, GPU/crop corrections and ownership cleanup. All R1–R8 runtime
code, application locks, schemas, model/prompt settings and protected artifacts
remain unchanged. All historical limits and failed invocation identities remain
explicit. The deliverable was uncommitted and unpushed at local closeout; the later
authorized publication and exact-SHA hosted results are recorded above.
