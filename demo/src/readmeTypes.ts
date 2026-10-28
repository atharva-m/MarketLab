// Output-frame timeline produced by scripts/prepare-readme.mjs from a real
// capture log. Coordinates are CSS pixels of the recorded browser viewport.
export type Point = { f: number; x: number; y: number };

export type ReadmeTimeline = {
  schema: "marketlab-readme-timeline-v1";
  video: string;
  durationInFrames: number;
  viewport: { width: number; height: number };
  loop: boolean;
  pointer: Point[];
  clicks: (Point & { zoom?: number })[];
  // Reading moments chosen in the cut list, zoomed like a click.
  focus: { from: number; to: number; x: number; y: number; zoom: number }[];
  typing: { from: number; to: number }[];
  scrolls: { from: number; to: number }[];
  chapters: { from: number; to: number; label: string }[];
  urls: { f: number; url: string }[];
};

export type ReadmeProps = { timeline: ReadmeTimeline | null };
