import {CalculateMetadataFunction, Composition} from 'remotion';
import {defaultHookProps, Hook, HookProps} from './Hook';

const calculateHookMetadata: CalculateMetadataFunction<HookProps> = ({props}) => {
  const fps = Math.max(1, Math.round(Number(props.fps) || 30));
  // 时长由导演给定（开场钩子至少 10 秒），不再固定 3~5 秒。
  const seconds = Math.max(3, Number(props.duration) || 10);
  return {
    durationInFrames: Math.max(1, Math.round(seconds * fps)),
    fps,
    width: Math.max(320, Math.round(Number(props.width) || 1920)),
    height: Math.max(240, Math.round(Number(props.height) || 1080)),
  };
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="Hook"
      component={Hook}
      durationInFrames={120}
      fps={30}
      width={1920}
      height={1080}
      defaultProps={defaultHookProps}
      calculateMetadata={calculateHookMetadata}
    />
  );
};
