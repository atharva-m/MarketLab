import { Composition } from "remotion";
import { MarketLabDemo, SetupPreview, MediaSetupCheck } from "./MarketLabDemo";
import type { DemoManifest } from "./types";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="MarketLabR9"
        component={MarketLabDemo}
        durationInFrames={5400}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ manifest: null as DemoManifest | null }}
      />
      <Composition
        id="SetupPreview"
        component={SetupPreview}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
      />
      <Composition
        id="MediaSetupCheck"
        component={MediaSetupCheck}
        durationInFrames={90}
        fps={30}
        width={1920}
        height={1080}
        defaultProps={{ setupFile: null as string | null }}
      />
    </>
  );
};
