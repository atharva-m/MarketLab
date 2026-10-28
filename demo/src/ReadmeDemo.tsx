import { useMemo } from "react";
import {
  AbsoluteFill,
  Easing,
  interpolate,
  OffthreadVideo,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import {
  cameraTrack,
  contentScale,
  pointerAt,
  STAGE,
  toStage,
  WINDOW,
  windowHeight,
} from "./readmeCamera";
import type { ReadmeProps, ReadmeTimeline } from "./readmeTypes";

const font = '"Segoe UI", "Inter", system-ui, sans-serif';
// Colors follow frontend/src/styles.css: black canvas, titanium accents.
const accent = "#e0eaf4";
// A looping cut ends on a black card with the UI wordmark, so the restart reads
// as a new pass rather than a jump.
export const END_FRAMES = 60;
const WORDMARK = [
  "█▀▄▀█ ▄▀█ █▀█ █▄▀ █▀▀ ▀█▀ █   ▄▀█ █▄▄",
  "█ ▀ █ █▀█ █▀▄ █ █ ██▄  █  █▄▄ █▀█ █▄█",
].join("\n");

const fade = (frame: number, from: number, to: number, edge = 8) =>
  interpolate(frame, [from, from + edge, to - edge, to], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const Screen = ({ timeline }: { timeline: ReadmeTimeline }) => (
  <OffthreadVideo
    src={staticFile(timeline.video)}
    muted
    style={{ width: "100%", height: "100%", display: "block" }}
  />
);

const BrowserWindow = ({ timeline }: { timeline: ReadmeTimeline }) => {
  const frame = useCurrentFrame();
  let url = timeline.urls.length ? timeline.urls[0].url : "";
  for (const entry of timeline.urls) if (entry.f <= frame) url = entry.url;
  const height = windowHeight(timeline);
  return (
    <div
      style={{
        position: "absolute",
        left: WINDOW.left,
        top: WINDOW.top,
        width: WINDOW.width,
        height,
        borderRadius: 14,
        overflow: "hidden",
        background: "#050506",
        boxShadow:
          "0 0 0 1px rgba(255,255,255,0.08), 0 30px 80px rgba(0,0,0,0.45), 0 8px 24px rgba(0,0,0,0.25)",
      }}
    >
      <div
        style={{
          height: WINDOW.bar,
          background: "#0c0d0f",
          borderBottom: "1px solid #1d1f24",
          display: "flex",
          alignItems: "center",
          padding: "0 16px",
          gap: 8,
        }}
      >
        {["#ff5f57", "#febc2e", "#28c840"].map((color) => (
          <span
            key={color}
            style={{
              width: 12,
              height: 12,
              borderRadius: 6,
              background: color,
            }}
          />
        ))}
        <div
          style={{
            margin: "0 auto",
            width: 560,
            height: 26,
            borderRadius: 7,
            background: "#18191d",
            color: "#b3b8bf",
            fontFamily: font,
            fontSize: 14,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            letterSpacing: 0.2,
          }}
        >
          {url.replace(/^https?:\/\//, "")}
        </div>
        <span style={{ width: 52 }} />
      </div>
      <div style={{ position: "relative", height: height - WINDOW.bar }}>
        <Screen timeline={timeline} />
      </div>
    </div>
  );
};

const Cursor = ({ timeline }: { timeline: ReadmeTimeline }) => {
  const frame = useCurrentFrame();
  const css = pointerAt(timeline.pointer, frame);
  const at = toStage(timeline, css.x, css.y);
  const k = contentScale(timeline);
  let press = 1;
  const ripples = [];
  for (const click of timeline.clicks) {
    const age = frame - click.f;
    if (age >= -1 && age < 5)
      press = Math.min(
        press,
        interpolate(age, [-1, 1, 5], [1, 0.8, 1], {
          extrapolateRight: "clamp",
        }),
      );
    if (age >= 0 && age < 16) {
      const p = age / 16;
      const point = toStage(timeline, click.x, click.y);
      ripples.push(
        <div
          key={click.f}
          style={{
            position: "absolute",
            left: point.x,
            top: point.y,
            width: 2,
            height: 2,
            borderRadius: "50%",
            transform: `translate(-50%, -50%) scale(${(10 + 26 * Easing.out(Easing.cubic)(p)) * k})`,
            background: `rgba(141, 169, 196, ${0.28 * (1 - p)})`,
            boxShadow: `0 0 0 0.12px rgba(224, 234, 244, ${0.9 * (1 - p)})`,
          }}
        />,
      );
    }
  }
  return (
    <>
      {ripples}
      <svg
        width={30}
        height={30}
        viewBox="0 0 30 30"
        style={{
          position: "absolute",
          left: at.x - 6 * k,
          top: at.y - 3 * k,
          overflow: "visible",
          transform: `scale(${k * 1.05 * press})`,
          transformOrigin: "6px 3px",
          filter: "drop-shadow(0 2px 3px rgba(0,0,0,0.35))",
        }}
      >
        <path
          d="M6 3 L6 23.5 L11.2 18.6 L14.8 26.6 L18.3 25.1 L14.8 17.3 L21.6 17.3 Z"
          fill="#111814"
          stroke="#ffffff"
          strokeWidth={1.7}
          strokeLinejoin="round"
        />
      </svg>
    </>
  );
};

const Caption = ({ timeline }: { timeline: ReadmeTimeline }) => {
  const frame = useCurrentFrame();
  return (
    <>
      {timeline.chapters.map((chapter, index) => {
        const opacity = fade(frame, chapter.from, chapter.to);
        if (opacity <= 0) return null;
        return (
          <div
            key={chapter.from}
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              bottom: 44,
              display: "flex",
              justifyContent: "center",
              opacity,
              transform: `translateY(${(1 - opacity) * 14}px)`,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 16,
                padding: "13px 28px 13px 14px",
                borderRadius: 999,
                background: "rgba(12, 13, 15, 0.9)",
                border: "1px solid #2a2d33",
                boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
                color: "#f5f6f7",
                fontFamily: font,
                fontSize: 30,
                fontWeight: 600,
                letterSpacing: -0.2,
              }}
            >
              <span
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 19,
                  background: accent,
                  color: "#050506",
                  fontSize: 21,
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                {index + 1}
              </span>
              {chapter.label}
            </div>
          </div>
        );
      })}
    </>
  );
};

const EndCard = ({ frame }: { frame: number }) => {
  const opacity = fade(frame, 6, END_FRAMES - 4, 14);
  return (
    <AbsoluteFill
      style={{
        background: "#050506",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <pre
        style={{
          margin: 0,
          opacity,
          transform: `scale(${0.96 + 0.04 * opacity})`,
          fontFamily: '"Geist Mono", Consolas, ui-monospace, monospace',
          fontSize: 44,
          lineHeight: 1.05,
          whiteSpace: "pre",
          background:
            "linear-gradient(100deg, #f5f6f7 0%, #bdeeff 18%, #e3d5ff 36%, #ffe3cc 54%, #c7f5e2 72%, #f5f6f7 90%)",
          WebkitBackgroundClip: "text",
          backgroundClip: "text",
          color: "transparent",
        }}
      >
        {WORDMARK}
      </pre>
    </AbsoluteFill>
  );
};

export const ReadmeDemo = ({ timeline }: ReadmeProps) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!timeline)
    throw new Error(
      "Prepare a README timeline with scripts/prepare-readme.mjs",
    );
  const track = useMemo(() => cameraTrack(timeline, fps), [timeline, fps]);
  const end = frame - timeline.durationInFrames;
  if (end >= 0) return <EndCard frame={end} />;
  const camera = track[Math.min(frame, track.length - 1)];
  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(ellipse 80% 70% at 30% 20%, #1b222c 0%, transparent 60%), radial-gradient(ellipse 70% 60% at 85% 90%, #18191d 0%, transparent 65%), linear-gradient(140deg, #0c0d0f 0%, #121316 55%, #050506 100%)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          width: STAGE.width,
          height: STAGE.height,
          transformOrigin: "0 0",
          transform: `translate(${STAGE.width / 2 - camera.x * camera.s}px, ${STAGE.height / 2 - camera.y * camera.s}px) scale(${camera.s})`,
        }}
      >
        <BrowserWindow timeline={timeline} />
        <Cursor timeline={timeline} />
      </div>
      <Caption timeline={timeline} />
      {timeline.loop && (
        <AbsoluteFill
          style={{
            background: "#050506",
            opacity: interpolate(end, [-12, -1], [0, 1], {
              extrapolateLeft: "clamp",
              extrapolateRight: "clamp",
            }),
          }}
        />
      )}
    </AbsoluteFill>
  );
};
