import { Video } from "@remotion/media";
import {
  AbsoluteFill,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import type { Caption, DemoManifest, Shot } from "./types";

const palette = {
  background: "#0b111b",
  ink: "#eef3fa",
  muted: "#a7b5ca",
  accent: "#79e3c7",
};
const base = {
  background: palette.background,
  color: palette.ink,
  fontFamily: "Arial, sans-serif",
};

const CaptionLine = ({ captions }: { captions: Caption[] }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const text = captions
    .filter(
      (caption) =>
        (frame * 1000) / fps >= caption.startMs &&
        (frame * 1000) / fps < caption.endMs,
    )
    .map((caption) => caption.text)
    .join("");
  return text ? (
    <div
      style={{
        position: "absolute",
        bottom: 39,
        left: 160,
        right: 160,
        textAlign: "center",
        fontSize: 34,
        lineHeight: 1.3,
        color: palette.ink,
      }}
    >
      {text}
    </div>
  ) : null;
};

const SourceVideo = ({ shot }: { shot: Shot }) => {
  const crop = shot.crop ?? { x: 0, y: 0, width: 1920, height: 1080 };
  const scale = Math.min(1752 / crop.width, 758 / crop.height);
  return (
    <div
      style={{
        position: "absolute",
        overflow: "hidden",
        width: crop.width * scale,
        height: crop.height * scale,
        left: (1752 - crop.width * scale) / 2,
        top: (758 - crop.height * scale) / 2,
      }}
    >
      <Video
        src={staticFile(shot.file)}
        trimBefore={shot.trimBefore}
        muted
        objectFit="fill"
        style={{
          position: "absolute",
          width: 1920 * scale,
          height: 1080 * scale,
          left: -crop.x * scale,
          top: -crop.y * scale,
          background: "#fff",
        }}
      />
    </div>
  );
};

const Footage = ({ shot }: { shot: Shot }) => (
  <AbsoluteFill style={base}>
    <div
      style={{
        position: "absolute",
        top: 42,
        left: 84,
        fontSize: 19,
        letterSpacing: 5,
        color: palette.accent,
      }}
    >
      MARKETLAB / LOCAL RESEARCH
    </div>
    <div
      style={{
        position: "absolute",
        top: 87,
        left: 84,
        fontSize: 44,
        fontWeight: 700,
      }}
    >
      {shot.title}
    </div>
    <div
      style={{
        position: "absolute",
        top: 165,
        left: 84,
        right: 84,
        height: 758,
        overflow: "hidden",
        borderRadius: 12,
        border: "1px solid #29364a",
        boxShadow: "0 20px 70px #0008",
      }}
    >
      <SourceVideo shot={shot} />
    </div>
    <div
      style={{
        position: "absolute",
        top: 941,
        left: 84,
        fontSize: 20,
        color: palette.muted,
      }}
    >
      {shot.sourceState === "retained"
        ? "Retained evidence environment"
        : "Fresh execution environment"}
      {shot.disclosure ? ` · ${shot.disclosure}` : ""}
    </div>
    <CaptionLine captions={shot.captions} />
  </AbsoluteFill>
);

const Title = ({ closing = false }: { closing?: boolean }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <AbsoluteFill style={{ ...base, padding: 100, justifyContent: "center" }}>
      <div
        style={{
          position: "absolute",
          width: 670,
          height: 670,
          right: -170,
          top: -160,
          borderRadius: "50%",
          border: "1px solid #79e3c744",
        }}
      />
      <div
        style={{
          opacity: interpolate(frame, [0, fps], [0, 1], {
            extrapolateRight: "clamp",
          }),
          translate: `0 ${interpolate(frame, [0, fps], [20, 0], { extrapolateRight: "clamp" })}px`,
        }}
      >
        <div
          style={{
            fontSize: 24,
            letterSpacing: 7,
            color: palette.accent,
            marginBottom: 45,
          }}
        >
          MARKETLAB
        </div>
        <div
          style={{
            fontSize: 92,
            fontWeight: 700,
            lineHeight: 1.08,
            maxWidth: 1430,
            whiteSpace: "pre-line",
          }}
        >
          {closing
            ? "Inspect the evidence.\nReproduce the research."
            : "From explicit data\nto inspectable research."}
        </div>
        <div
          style={{
            fontSize: 34,
            color: palette.muted,
            lineHeight: 1.5,
            marginTop: 46,
            maxWidth: 1380,
          }}
        >
          {closing
            ? "Local setup and verification instructions accompany this demo."
            : "Immutable datasets. Deterministic results. Grounded commentary."}
        </div>
        <div style={{ fontSize: 23, color: palette.muted, marginTop: 65 }}>
          January 2025 · Binance Spot · BTCUSDT / ETHUSDT
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const MarketLabDemo = ({
  manifest,
}: {
  manifest: DemoManifest | null;
}) => {
  const { fps } = useVideoConfig();
  if (
    !manifest?.reviewed ||
    !manifest.capturedAfterTimedAcceptance ||
    manifest.shots.length !== 5
  ) {
    throw new Error(
      "Final demo requires five validated evidence-backed local shots. Use SetupPreview for setup QA.",
    );
  }
  return (
    <AbsoluteFill style={base}>
      <Sequence name="Opening" durationInFrames={12 * fps}>
        <Title />
      </Sequence>
      <Sequence
        name="Catalog and versions"
        from={12 * fps}
        durationInFrames={23 * fps}
      >
        <Footage shot={manifest.shots[0]} />
      </Sequence>
      <Sequence
        name="Manual research"
        from={35 * fps}
        durationInFrames={35 * fps}
      >
        <Footage shot={manifest.shots[1]} />
      </Sequence>
      <Sequence
        name="Copilot clarification"
        from={70 * fps}
        durationInFrames={40 * fps}
      >
        <Footage shot={manifest.shots[2]} />
      </Sequence>
      <Sequence
        name="Independent memo"
        from={110 * fps}
        durationInFrames={30 * fps}
      >
        <Footage shot={manifest.shots[3]} />
      </Sequence>
      <Sequence
        name="Provenance and monitoring"
        from={140 * fps}
        durationInFrames={25 * fps}
      >
        <Footage shot={manifest.shots[4]} />
      </Sequence>
      <Sequence name="Closing" from={165 * fps} durationInFrames={15 * fps}>
        <Title closing />
      </Sequence>
    </AbsoluteFill>
  );
};

export const SetupPreview = () => (
  <AbsoluteFill style={base}>
    <Title />
    <div
      style={{
        position: "absolute",
        top: 30,
        right: 60,
        color: "#ffcf7c",
        fontSize: 28,
      }}
    >
      SETUP CHECK · NO PRODUCT FOOTAGE
    </div>
  </AbsoluteFill>
);

export const MediaSetupCheck = ({
  setupFile,
}: {
  setupFile: string | null;
}) => {
  if (!setupFile) throw new Error("Local setup clip required");
  return (
    <AbsoluteFill style={base}>
      <Video
        src={staticFile(setupFile)}
        muted
        style={{ width: "100%", height: "100%" }}
        objectFit="contain"
      />
      <div
        style={{
          position: "absolute",
          top: 30,
          left: 60,
          fontSize: 28,
          color: "#ffcf7c",
        }}
      >
        LOCAL VIDEO PLAYBACK CHECK · NO PRODUCT FOOTAGE
      </div>
    </AbsoluteFill>
  );
};
