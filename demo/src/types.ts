export type Caption = {
  text: string;
  startMs: number;
  endMs: number;
  timestampMs: number | null;
  confidence: number | null;
};

export type Shot = {
  id: string;
  title: string;
  from: number;
  duration: number;
  file: string;
  sha256: string;
  trimBefore: number;
  sourceState: "fresh" | "retained";
  evidence: { path: string; sha256: string }[];
  disclosure: string;
  crop?: { x: number; y: number; width: number; height: number };
  captions: Caption[];
};

export type DemoManifest = {
  schema: "marketlab-demo-v1";
  sourceFingerprint: string;
  capturedAfterTimedAcceptance: true;
  reviewed: true;
  shots: Shot[];
};
