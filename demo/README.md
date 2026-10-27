# MarketLab local R9 video

An isolated Remotion 4.0.539 project for a 180-second, 1920×1080, 30 fps demo.
The final composition uses actual local UI recordings. It refuses to render
without a reviewed manifest, five clips and hashed evidence references. The
SetupPreview composition is marked as setup-only and earns no product/demo credit.

## Install and preview

Use Node.js matching package.json engines. From this folder:

```powershell
npm ci --ignore-scripts
npx remotion browser ensure
npm run lint
npm test
npm run dev
```

Installation/browser acquisition can use the network. Preview and rendering use
the process-scoped local-only preloader. Studio is requested on port 59130 and
the preloader binds Node servers to 127.0.0.1 regardless of its printed network
URL. Inspect exact ownership before stopping a process. Open the printed local
URL and select SetupPreview. MarketLabR9 reports missing footage until supplied
with prepared props. Do not publish or connect Studio.

## Capture and prepare

Capture after timed acceptance in a separate recording invocation. Keep full
original recordings outside Git and outside cloud-synchronized folders. Existing
local Playwright recording can capture the actual browser; OBS is optional.
Use a 1920×1080 viewport and avoid displaying credentials/private configuration.
Preserve source/run identities and the states actually observed. Do not
reconstruct product screens from invented values.

Copy manifest.example.json into the ignored evidence directory. Replace every
placeholder with actual values and mark reviewed only after footage/captions
are checked. The five files must be at least the indicated length after trim:

| ID         | Composition time | Required source length |
| ---------- | ---------------- | ---------------------- |
| catalog    | 12–35s           | 23s                    |
| manual     | 35–70s           | 35s                    |
| copilot    | 70–110s          | 40s                    |
| memo       | 110–140s         | 30s                    |
| monitoring | 140–165s         | 25s                    |

The opening is 12 seconds; closing is 15 seconds. File paths are relative to
the capture root and must remain inside it. Evidence paths are relative to
the evidence root and must hash to the declared SHA256. Disclose time compression,
cuts or transitions between fresh and retained environments. Clips are muted;
reviewed on-screen captions carry the explanation without cloud narration.
Caption milliseconds are relative to the displayed shot, not its raw source
timestamp. Adjust caption text/timing to the observed footage.
An optional crop object contains integer x/y/width/height coordinates within the
original 1920×1080 source. It changes framing only; original capture bytes remain
unchanged. Preparation records original dimensions and crop in the asset receipt.
Use crops to make actual controls/values readable, and disclose focused framing.
When recording already completed R9 states, disclose that the clip inspects
completed execution/history. Do not imply that the video shows live inference,
job execution or memo generation. Link the actual acceptance receipts for those
operations in the evidence index.

```powershell
npm run prepare:media -- ../artifacts/r9-20261027/video-manifest.json ../artifacts/r9-20261027/capture ../artifacts/r9-20261027 ../artifacts/r9-20261027/r9-video-prepared-1
npm run render:local -- ../artifacts/r9-20261027/r9-video-prepared-1/props.json ../artifacts/r9-20261027/r9-demo-final-1.mp4
npm run review:local -- ../artifacts/r9-20261027/r9-demo-final-1.mp4 ../artifacts/r9-20261027/r9-demo-review-1
```

Preparation verifies hashes, path containment, evidence and source duration,
copies hash-addressed assets into ignored public/media, and exports props,
captions.srt, transcript.txt and an asset receipt into a fresh directory.
Rendering rechecks prepared clip hashes and refuses output overwrite.
Preserve source media/evidence; prepared media is a derived copy.

## Local operation and QA

Final renders use the dedicated NVIDIA GPU as requested: process-local ANGLE
Direct3D11/high-performance selection, actual Chromium SystemInfo and WebGL
NVIDIA adapter verification, plus required H.264 NVENC on CUDA device 0 at 8M.
The current machine's device 0 is the RTX 4070 Laptop GPU. The renderer fails
instead of silently falling back to CPU encoding. The receipt records actual
adapter strings, feature status, encoder arguments and elapsed time. GPU support
does not mean every operation runs on GPU, and timing across different crops or
settings is not a controlled speed comparison. No driver or global GPU setting
is changed.

Before a full export, use a short actual-footage compatibility probe:

```powershell
npm run render:local -- ../artifacts/r9-20261027/r9-video-prepared-2/props.json ../artifacts/r9-20261027/r9-video-gpu-check-new.mp4 gpu-probe
```

This produces 30 encoded frames plus memo/provenance preview stills and receives
no final-demo acceptance credit. Setup checks retain their explicitly separate
scope. GPU selection is per process; neither accounts nor media uploads are used.

The wrapper uses local bundle/renderer APIs, blocks Node nonloopback socket
connections, and gives Chromium a loopback-only proxy/DNS configuration with
background networking disabled. This is process-level control, not packet
capture or a guarantee about unrelated software. No system firewall, account,
cloud render, remote font, online transcription or production API request is
part of the composition. Only sanitized review frames should be supplied to
the assistant; this conversation itself is not offline.

For an account-free setup check with no product footage:

```powershell
npm run render:local -- unused ../artifacts/r9-20261027/r9-video-setup-new.mp4 setup-check
```

Final acceptance requires full export playback and checking readable UI,
cuts/captions, numerical labels, disclosures, source/evidence mapping and absence
of unintended sensitive content. The render receipt records output hash,
dimensions, duration, source/props identity and process-control limitations.
Successful encoding leaves visual review pending. Keep originals, MP4, samples,
captions and evidence outside Git. Reproduction requires identical assets/props
and toolchain; byte-identical MP4 across platforms is not promised.
The review command plays the encoded video fully in local Chromium, records
playback/errors/frame drops, then uses the bundled FFmpeg CPU decoder to verify
all 5,400 frames and extract every-second PNGs plus samples around chapter cuts.
Native PNGs are used for contact sheets. Direct browser video-to-canvas samples
showed inconsistent visual results during review; their exact cause is unknown.
Native decoding independently verifies the encoded artifact. This QA decoding
does not change the required GPU export path.
Inspect every sheet and full-resolution chapter/caption/boundary frames. This
method is full playback plus sampled visual review, not manual continuous viewing
or semantic inspection of every encoded frame.
An optional third review argument names an already passed playback.json for the
same SHA256, allowing only native decoding/extraction to be repeated. Its full
playback, terminal state, clean closure and hash are checked before reuse. The
new receipt links that immutable playback receipt and pins its own QA source;
the original render-time source pins remain separate.

## README hero and highlight

The ReadmeHero (looping GIF) and ReadmeHighlight (short MP4) compositions are
built from one scripted recording of the real workspace. Run the API, UI on
127.0.0.1:5173 and Ollama against an owned database/storage pair, then record:

```powershell
npm run capture:readme -- ../artifacts/rd/connection-private.json ../artifacts/rd/capture-2
```

The capture drives Chrome at 2x density through Playwright and records the
page with Chrome's screencast. It logs every pointer position, click, typing
burst, scroll and the bounded CLI worker commands it runs, with timestamps.
No cursor is drawn into the page. The compositions draw the cursor, click
ripples and click-driven zooms from that log, so each on-screen interaction is
an actual input. Worker commands appear as toasts while they run, and segments
that a cut list speeds up carry a visible speed badge.

A cut list (`cuts/hero.json`, `cuts/highlight.json`) chooses capture segments in
seconds since the first frame, optional speeds, chapter captions, per-click
zoom overrides and extra reading zooms (`focus`). Prepare, render and encode:

```powershell
npm run prepare:readme -- ../artifacts/rd/capture-2 cuts/hero.json ../artifacts/rd/hero-props.json
npm run render:readme -- ../artifacts/rd/hero-props.json ../artifacts/rd/out/hero-master.mp4 ReadmeHero
npm run encode:readme -- gif ../artifacts/rd/out/hero-master.mp4 ../docs/assets/marketlab-demo.gif --no-limit
npm run prepare:readme -- ../artifacts/rd/capture-2 cuts/highlight.json ../artifacts/rd/highlight-props.json
npm run render:readme -- ../artifacts/rd/highlight-props.json ../artifacts/rd/out/highlight-master.mp4 ReadmeHighlight
npm run encode:readme -- mp4 ../artifacts/rd/out/highlight-master.mp4 ../artifacts/rd/out/marketlab-highlight.mp4
```

Preparation and encoding need a full FFmpeg build on PATH (or `FFMPEG_PATH`); the
Remotion compositor build lacks the fps/setpts filters. The README embeds the
repository GIF (`--no-limit`: 1200 px, 15 fps). Without that flag the GIF steps
down until it fits GitHub's 10 MB attachment upload. The highlight MP4 is sized for
that upload too; GitHub plays a video inline only from a user-attachments URL.
Captures, masters and prepared media stay in ignored folders.

## Versions and provenance

provenance.json pins the official skill commit and reviewed file blobs. Skills
were read from an ignored local repository snapshot, not installed globally.
Remotion 4 allows individual/evaluation use and requires a company license
outside its free eligibility. This setup does not establish licensing for a
larger organization. The selected CLI rendered locally without sign-in/activation.

The scaffold resolved Zod 4.5.4, which npm audit flagged for
[GHSA-mrhx-c7xc-m3w5](https://github.com/advisories/GHSA-mrhx-c7xc-m3w5).
The isolated Zod 4.6.6 override removes the audit finding. Remotion warns it
expects 4.5.4; the override requires actual local render compatibility checks
and remains explicit in provenance. Main application dependencies are unchanged.
No forced npm audit upgrade was used.

Official references: [skills](https://www.remotion.dev/docs/ai/skills),
[rendering](https://www.remotion.dev/docs/render),
[license](https://www.remotion.dev/license).
