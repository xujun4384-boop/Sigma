import {AbsoluteFill} from 'remotion';
import {KineticHook} from './templates/KineticHook';
import {TitleHook} from './templates/TitleHook';
import {TemplateId, TemplateProps} from './templates/theme';
import {UIHook} from './templates/UIHook';

export type HookProps = TemplateProps & {
  template: TemplateId;
  duration?: number;
  width?: number;
  height?: number;
  fps?: number;
};

export const defaultHookProps: HookProps = {
  template: 'title',
  text: 'AURORA',
  kicker: 'OPENING HOOK',
  sub: '',
  accent: '',
  duration: 4,
  width: 1920,
  height: 1080,
  fps: 30,
};

export const Hook: React.FC<HookProps> = ({template, ...rest}) => {
  const props: TemplateProps = {
    text: rest.text || '',
    kicker: rest.kicker || '',
    sub: rest.sub || '',
    accent: rest.accent || '',
  };
  if (template === 'kinetic') {
    return <KineticHook {...props} />;
  }
  if (template === 'ui') {
    return <UIHook {...props} />;
  }
  return (
    <AbsoluteFill style={{backgroundColor: '#04060c'}}>
      <TitleHook {...props} />
    </AbsoluteFill>
  );
};
