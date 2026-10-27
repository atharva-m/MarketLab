# R9 short demo production proposal

Prepared October 27, 2026. Produce a 2–3 minute professional overview using real
MarketLab footage, with longer original recordings and run evidence retained
separately. This replaces the earlier proposed 10–15 minute final viewing cut.
R9 implementation and acceptance were subsequently approved under the
[pre-code contract](r9-handoff.md); commit/push and public publication remain excluded.
The user selected local Remotion composition and rendering. The complete scope,
implementation sequence and acceptance gates are in [the R9 plan](r9-plan.md).

## Privacy requirement

The user declined the Descript direction because of account/data-access concerns.
Use local capture, local media assets and local editing/rendering. No connected
video service, cloud transcription, remote fonts/assets or footage uploads are
part of the proposed workflow. Software installation may require downloads;
that is separate from processing recordings. No new connection was authorized.

Local video processing does not make this Codex conversation offline: screenshots
or content submitted to the assistant still pass through the assistant service.
Avoid sending sensitive footage for inspection; use sanitized frames if needed.

## Production options

| Option                   | Role                                                                                 | Availability and tradeoff                                                                                                                                                                           |
| ------------------------ | ------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Shotcut                  | Local timeline editing, titles, audio and export                                     | Researched alternative; superseded by the user's Remotion selection.                                                                                                                                |
| Descript plugin          | Cloud-connected editing                                                              | Excluded following the user's privacy preference. No connection confirmed.                                                                                                                          |
| Official Remotion skills | Compose precise titles, overlays, transitions, captions and repeatable video renders | Selected workflow. Separate demo/ project uses Remotion 4.0.539 and reviewed skills pinned to commit 30d4553ecd46fbc5212fd0ff006ae43af522158b. No global skill installation.                        |
| OBS Studio               | Capture the actual Windows browser/application and narration                         | Official documentation supports window/display capture, audio sources and local recording. This is a capture application, not a verified connected plugin. Local installation has not been checked. |
| Canva plugin             | Optional cover, title cards and brand assets                                         | Found in the directory but not connected. Its advertised connector capabilities support design work; end-to-end video editing/export through the connector was not verified.                        |
| Runway or HeyGen plugins | Optional generated introductions or narration                                        | Both appeared in the directory, unconnected. Generated footage is unnecessary for demonstrating this working application and must not stand in for observed UI/results.                             |

Selected workflow: local capture followed by Remotion composition, preview and
rendering, with local narration or designed on-screen text and reviewed captions.
Verify applicable licensing and the selected version's local prerequisites before
setup. Account-free operation is a requirement; if sign-in or remote processing is
required, report the conflict rather than connecting a service. Verify representative
rendering without external network access after prerequisites are installed.
Canva, Runway and HeyGen are research findings, not recommended connections under
the privacy requirement. Avoid combining several editors for a single short cut.
Keep any Remotion project and its dependencies separate from MarketLab's runtime
and existing lockfiles. The isolated video dependencies/browser were acquired
after R9 approval; existing application dependencies remain unchanged.

The available computer-use skill can help operate native Windows apps. The
presentations and imagegen skills could supply optional title/storyboard artwork,
but their outputs do not replace screen capture or a video editor. None was
invoked for production here.

## Storyboard

| Time            | Visual                                                        | Message                                                                       |
| --------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 0–12 seconds    | Clean title and real result screen                            | Reproducible local market research from explicit data to inspectable results. |
| 12–35 seconds   | Catalog, selected January versions and provenance             | Choose exact datasets; retain source identity.                                |
| 35–70 seconds   | Manual request, durable job state, numerical result and chart | Deterministic analysis with visible execution and exact values.               |
| 70–110 seconds  | Actual copilot request and clarification                      | Natural language reaches the same validated research workflow.                |
| 110–140 seconds | Memo beside independently available numerical output          | Generated commentary remains grounded and separate from numerical success.    |
| 140–165 seconds | Provenance and brief operational view                         | Inspect results, job history and worker activity.                             |
| 165–180 seconds | Closing title and documentation pointer                       | Local, reproducible and bounded; direct viewers to setup and evidence.        |

Target 1920×1080, 16:9, 30 fps, readable UI crops, restrained transitions,
consistent typography, clear narration and reviewed captions. Use short zooms
only to focus on controls or values. Aim for roughly 320–380 narrated words.
Record a short sample first to check text readability, audio and capture load.

## Evidence and production boundaries

Use actual product footage and values. Do not synthesize successful model output,
replace a failed response with an invented response, or present a restored result
as a newly executed run. Label time compression and transitions between fresh and
retained environments. Keep source/run IDs in an accompanying evidence index
rather than filling the viewing cut with technical logs.

Keep full takes and failed invocation records. Editing narration or pauses is
acceptable; selecting a successful model take must not become a new quality claim.
Record separately from performance/resource acceptance to avoid adding capture
load to measured benchmarks. The polished video does not replace acceptance gates.

Deliver a local MP4, reviewed caption file, transcript, shot/evidence index and
editable source project. Record final checksums and retain originals outside Git.
Check exports for legible text, caption timing, clipped audio, unintended secrets
and truthful claims. No upload or public sharing is included; nothing was uploaded
in this research. Store footage outside cloud-synchronized folders.

## Sources

- [Remotion official agent skills](https://www.remotion.dev/docs/ai/skills): creation, markup, Studio, rendering and captions; supports coding-agent workflows.
- [OBS official quick start](https://obsproject.com/kb/quick-start-guide): scene sources, window/display capture, audio and test recordings.
- [Shotcut FAQ](https://shotcut.org/FAQ/): local operation without network activation, subscription checks or usage analytics.
- [Shotcut features](https://www.shotcut.org/features/): native timeline editing and video export capabilities.
- [Remotion rendering](https://www.remotion.dev/docs/render): rendering workflow; local execution is an option, not a blanket guarantee that every composition avoids network requests.
- [Descript screen recording](https://www.descript.com/screen-recording): recording and transcript-based editing.
- [Descript features](https://www.descript.com/features): captions, audio cleanup, editing and integration capabilities.
- [Descript captions](https://www.descript.com/tools/video-caption-generator): subtitle and burned-in caption exports.
- Plugin directory search on October 27, 2026: Descript, Canva, Runway and HeyGen listings were available and uninstalled. Search results are not exhaustive; see the [plugin directory](https://chatgpt.com/plugins).

The Descript sources remain a record of the initial comparison, not a request
to connect.

## Implementation and setup verification

[demo/README.md](../demo/README.md) contains installation, local preview,
capture manifest, verified media preparation and rendering commands. The final
composition requires five real clips, reviewed captions and hashed evidence
references. Native title graphics are distinct from recorded product footage.

A three-second 1080p30 setup render passed without an account or activation and
its sample frame was visually inspected. It is labeled as setup-only and is not
the final product demo. The first network probe failed on a premature synchronous
assertion and an overly loose null-path guard; both were corrected, with the
failure retained. A new probe verified local browser navigation and rejected
Node/Chromium external requests with process-scoped controls. This does not prove
host-wide network isolation.

The scaffold's transitive Zod 4.5.4 had an npm audit finding. Isolated override
4.6.6 yields zero findings; Remotion's expected-version warning and compatibility
checks are explicit in demo/provenance.json. Actual footage and complete final
video/evidence review were still required at this setup checkpoint; the completed
delivery and review are recorded below.

## Recorded R9 delivery and review

The implemented delivery uses five genuine browser recordings of completed R9
states and history, after timed acceptance. Catalog footage uses restored retained
inputs; the other chapters inspect fresh accepted R9 executions over explicitly
restored inputs. Captions and the disclosure line state this context. The manual
chapter shows the numerical summary, without claiming its recording shows a chart.
The operations chapter shows actual run provenance and links separately captured
API, collector and normal CLI-worker telemetry; it does not claim a live Grafana
deployment. There is no synthetic product UI, cloud narration, account connection
or media upload. The actual cut is caption-led and muted.

The corrected final export is the ignored local
`artifacts/r9-20261027/r9-demo-final-gpu-second.mp4`: 180 seconds, 1920×1080,
30 fps, 5,400 frames, SHA256
`184a6fb2ae1c6c6166c5cef6c1d63736ced9cef3520fe321e15b20b33bd3bf4f`.
Its receipt records actual NVIDIA RTX 4070 Laptop ANGLE/Direct3D11 adapter
verification and required H.264 NVENC on GPU 0, with 284.4113429 seconds elapsed.
This is not a controlled speed comparison with the earlier export. No driver or
system GPU settings were changed. Official
[GPU rendering](https://www.remotion.dev/docs/gpu) and
[hardware acceleration](https://www.remotion.dev/docs/hardware-acceleration)
guidance informed the process-local options.

The first full export and playback remain retained: encoding/playback succeeded,
but visual review rejected crop overscan and asymmetric letterboxing. The second
export uses reviewed exact crop masks. Its entire 180-second local browser
playback passed with zero reported errors/dropped frames. All 16 browser-derived
contact sheets were inspected. An inconsistent visual result during browser
canvas/display review prompted independent native FFmpeg decoding. Direct native
frames show complete branding, completed-state disclosures and readable UI;
the exact underlying cause of the inconsistent review display is unestablished.
The reusable QA command now decodes native PNGs and constructs contact sheets from
them, while preserving full browser playback as separate evidence. Export remains
GPU accelerated; native QA CPU decoding does not alter the MP4.

Every failed native QA attempt remains identifiable: the default null encoder was
unavailable in the bundled FFmpeg; explicit rawvideo/null decoded all 5,400 frames;
a subsequent select-expression sampling attempt failed before image extraction.
The replacement uses separately verified per-timestamp native PNG decoding.
The replacement native QA passed all 5,400 decoded frames and produced 192 native
samples and 16 contact sheets. All 16 sheets and full-resolution chapter/caption
frames were visually reviewed; the final visual receipt passed. This is automated
full playback/decode plus sampled visual inspection, not continuous human viewing
or semantic inspection of every frame. A bitmap-region check independently found
the branding and disclosure pixels in all five chapter samples.

Exact recorded render/QA process identities were absent after normal closure, with
no matching owned video processes/listeners. One old PID had been reused by an
unrelated Codex CUA process born later; its new executable and birth were recorded
and it was left untouched. The initial inspection-needed receipt and subsequent
reconciliation both remain retained. The quick native QA finished before its
requested birth inventory ran, so that invocation relies on its normal exit,
guarded browser/server closure and independent post-exit command/path absence;
no process identity was invented. Actual final review and cleanup receipts are
mapped in the R9 verification report. Render-time source pins and later QA-only
source pins remain distinct.
