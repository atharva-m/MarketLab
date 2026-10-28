import { Composition, type CalculateMetadataFunction } from "remotion";
import { MarketLabDemo, SetupPreview, MediaSetupCheck } from "./MarketLabDemo";
import { END_FRAMES, ReadmeDemo } from "./ReadmeDemo";
import type { ReadmeProps } from "./readmeTypes";
import type { DemoManifest } from "./types";

const readmeLength: CalculateMetadataFunction<ReadmeProps> = ({ props }) => ({
  durationInFrames: props.timeline
    ? props.timeline.durationInFrames + (props.timeline.loop ? END_FRAMES : 0)
    : 150,
});

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
      {["ReadmeHero", "ReadmeHighlight"].map((id) => (
        <Composition
          key={id}
          id={id}
          component={ReadmeDemo}
          durationInFrames={150}
          fps={30}
          width={1920}
          height={1080}
          defaultProps={{ timeline: null } as ReadmeProps}
          calculateMetadata={readmeLength}
        />
      ))}
    </>
  );
};
