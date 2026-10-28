import { useMemo } from "react";
import {
  AbsoluteFill,
  Easing,
  Freeze,
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
const accent = "#5fd4ad";
const LOOP_FRAMES = 14;

const fade = (frame: number, from: number, to: number, edge = 8) =>
  interpolate(frame, [from, from + edge, to - edge, to], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

const loopProgress = (timeline: ReadmeTimeline, frame: number) =>
  timeline.loop
    ? interpolate(
        frame,
        [
          timeline.durationInFrames - LOOP_FRAMES,
          timeline.durationInFrames - 1,
        ],
        [0, 1],
        {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.inOut(Easing.cubic),
        },
      )
    : 0;

const Screen = ({ timeline }: { timeline: ReadmeTimeline }) => (
  <OffthreadVideo
    src={staticFile(timeline.video)}
    muted
    style={{ width: "100%", height: "100%", display: "block" }}
  />
);

const BrowserWindow = ({ timeline }: { timeline: ReadmeTimeline }) => {
  const frame = useCurrentFrame();
  const loop = loopProgress(timeline, frame);
  let url = timeline.urls.length ? timeline.urls[0].url : "";
  if (loop < 0.5)
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
        background: "#f3f5f0",
        boxShadow:
          "0 0 0 1px rgba(255,255,255,0.08), 0 30px 80px rgba(0,0,0,0.45), 0 8px 24px rgba(0,0,0,0.25)",
      }}
    >
      <div
        style={{
          height: WINDOW.bar,
          background: "#e4e9e3",
          borderBottom: "1px solid #d3dad2",
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
            background: "#f7f9f6",
            color: "#55645c",
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
        {loop > 0 && (
          <div style={{ position: "absolute", inset: 0, opacity: loop }}>
            <Freeze frame={0}>
              <Screen timeline={timeline} />
            </Freeze>
          </div>
        )}
      </div>
    </div>
  );
};

const Cursor = ({ timeline }: { timeline: ReadmeTimeline }) => {
  const frame = useCurrentFrame();
  const loop = loopProgress(timeline, frame);
  const now = pointerAt(timeline.pointer, frame);
  const first = pointerAt(timeline.pointer, 0);
  const css = {
    x: now.x + (first.x - now.x) * loop,
    y: now.y + (first.y - now.y) * loop,
  };
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
            background: `rgba(95, 212, 173, ${0.28 * (1 - p)})`,
            boxShadow: `0 0 0 0.12px rgba(47, 143, 111, ${0.9 * (1 - p)})`,
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
                background: "rgba(8, 26, 21, 0.86)",
                border: "1px solid rgba(95, 212, 173, 0.35)",
                boxShadow: "0 10px 30px rgba(0,0,0,0.35)",
                color: "#eef5f0",
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
                  color: "#08201a",
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

export const ReadmeDemo = ({ timeline }: ReadmeProps) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  if (!timeline)
    throw new Error(
      "Prepare a README timeline with scripts/prepare-readme.mjs",
    );
  const track = useMemo(() => cameraTrack(timeline, fps), [timeline, fps]);
  // A looping cut eases the camera back to rest so the last frame meets the first.
  const shot = track[Math.min(frame, track.length - 1)];
  const loop = loopProgress(timeline, frame);
  const camera = {
    s: shot.s + (1 - shot.s) * loop,
    x: shot.x + (STAGE.width / 2 - shot.x) * loop,
    y: shot.y + (STAGE.height / 2 - shot.y) * loop,
  };
  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(ellipse 80% 70% at 30% 20%, #1d5444 0%, transparent 60%), radial-gradient(ellipse 70% 60% at 85% 90%, #164336 0%, transparent 65%), linear-gradient(140deg, #0b231d 0%, #0f2f27 55%, #081a15 100%)",
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
    </AbsoluteFill>
  );
};
