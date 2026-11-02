import {lightLeak} from '@remotion/effects/light-leak';
import {noise} from '@remotion/effects/noise';
import {scanlines} from '@remotion/effects/scanlines';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  Solid,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {
  clamp,
  fitFontSize,
  Palette,
  PALETTES,
  pickAccent,
  SERIF,
  SANS,
  splitChars,
  TemplateProps,
} from './theme';

const Blobs: React.FC<{palette: Palette; accent: string}> = ({palette, accent}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const colors = [accent, palette.accent2, '#ff965a', '#28bec8'];
  const specs = [
    {x: 22, y: 32, r: 42, phase: 0, speed: 0.011, opacity: 0.5},
    {x: 72, y: 26, r: 38, phase: 1.7, speed: 0.014, opacity: 0.4},
    {x: 84, y: 70, r: 30, phase: 3.1, speed: 0.009, opacity: 0.16},
    {x: 28, y: 80, r: 34, phase: 4.6, speed: 0.013, opacity: 0.28},
  ];

  return (
    <AbsoluteFill style={{overflow: 'hidden'}}>
      {specs.map((s, i) => {
        const dx = Math.sin(frame * s.speed + s.phase) * 90;
        const dy = Math.cos(frame * s.speed * 0.8 + s.phase) * 70;
        const scale = 1 + Math.sin(frame * s.speed * 0.6 + s.phase) * 0.12;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: (s.x / 100) * width + dx - (s.r / 100) * width,
              top: (s.y / 100) * height + dy - (s.r / 100) * width,
              width: (s.r / 100) * width * 2,
              height: (s.r / 100) * width * 0.98,
              borderRadius: '50%',
              background: `radial-gradient(closest-side, ${colors[i % colors.length]} 0%, rgba(0,0,0,0) 100%)`,
              filter: 'blur(58px)',
              mixBlendMode: 'screen',
              opacity: s.opacity,
              rotate: `${Math.sin(frame * 0.004 + s.phase) * 12}deg`,
              scale,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

const LightSweep: React.FC<{accent: string}> = ({accent}) => {
  const frame = useCurrentFrame();
  const {width, height, durationInFrames} = useVideoConfig();
  const progress = interpolate(frame, [0, durationInFrames], [0.15, 0.92], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const intensity = interpolate(
    frame,
    [0, 18, durationInFrames - 30, durationInFrames],
    [0, 0.6, 0.42, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

  return (
    <AbsoluteFill style={{opacity: intensity, mixBlendMode: 'screen', pointerEvents: 'none'}}>
      <Solid
        width={width}
        height={height}
        color="#000000"
        effects={[lightLeak({seed: 12, hueShift: 212, progress})]}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at 24% 22%, ${accent}33 0%, rgba(0,0,0,0) 48%)`,
        }}
      />
    </AbsoluteFill>
  );
};

const FilmGrain: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{opacity: 0.16, mixBlendMode: 'overlay', pointerEvents: 'none'}}>
      <Solid width={width} height={height} color="#808080" effects={[noise({amount: 0.9, seed: frame})]} />
    </AbsoluteFill>
  );
};

const Scanlines: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  return (
    <AbsoluteFill style={{opacity: 0.09, mixBlendMode: 'overlay', pointerEvents: 'none'}}>
      <Solid
        width={width}
        height={height}
        color="#a0a0a0"
        effects={[scanlines({amount: 0.6, spacing: 3, thickness: 1, offset: frame * 0.5})]}
      />
    </AbsoluteFill>
  );
};

const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      pointerEvents: 'none',
      background:
        'radial-gradient(ellipse at 50% 48%, rgba(0,0,0,0) 38%, rgba(0,0,0,0.55) 78%, rgba(0,0,0,0.92) 100%)',
    }}
  />
);

export const TitleHook: React.FC<TemplateProps> = ({text, kicker, sub, accent}) => {
  const frame = useCurrentFrame();
  const {width, height, fps, durationInFrames} = useVideoConfig();
  const palette = PALETTES.title;
  const accentColor = pickAccent(palette, accent);
  const chars = splitChars(text);
  const fontSize = fitFontSize(text, width, 0.135, width * 0.15);
  const crowd = clamp(chars.length / 10, 0, 1);

  const camera = interpolate(frame, [0, durationInFrames], [1.06, 1.0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.4, 0, 0.3, 1),
  });
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 16, durationInFrames],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

  return (
    <AbsoluteFill style={{backgroundColor: palette.bg}}>
      <AbsoluteFill style={{scale: camera}}>
        <Blobs palette={palette} accent={accentColor} />
        <LightSweep accent={accentColor} />
        <AbsoluteFill style={{backgroundColor: 'rgba(3,5,12,0.18)'}} />
        <AbsoluteFill
          style={{
            background:
              'radial-gradient(ellipse at 50% 50%, rgba(3,5,12,0.64) 0%, rgba(3,5,12,0.34) 46%, rgba(3,5,12,0) 74%)',
          }}
        />

        <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', padding: '0 72px'}}>
          <div
            style={{
              fontFamily: SANS,
              fontSize: 20 + (1 - crowd) * 4,
              fontWeight: 600,
              letterSpacing: interpolate(frame, [6, 34], ['0.3em', '0.62em'], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
              color: 'rgba(214,226,255,0.82)',
              marginBottom: 30,
              textTransform: 'uppercase',
              opacity: interpolate(frame, [6, 28], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              }),
            }}
          >
            {kicker || 'OPENING HOOK'}
          </div>

          <div style={{display: 'flex', alignItems: 'baseline', flexWrap: 'nowrap'}}>
            {chars.map((char, i) => {
              const start = 16 + i * Math.max(1.6, 3.2 - crowd);
              const p = interpolate(frame, [start, start + 26], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              });
              return (
                <span
                  key={i}
                  style={{
                    display: 'inline-block',
                    fontFamily: SERIF,
                    fontSize,
                    lineHeight: 1,
                    fontWeight: 600,
                    color: palette.fg,
                    letterSpacing: interpolate(frame, [start, start + 34], ['0.18em', '0.01em'], {
                      extrapolateLeft: 'clamp',
                      extrapolateRight: 'clamp',
                      easing: Easing.bezier(0.16, 1, 0.3, 1),
                    }),
                    translate: `0px ${(1 - p) * 74}px`,
                    opacity: p,
                    filter: `blur(${(1 - p) * 14}px)`,
                    textShadow: `0 0 60px ${accentColor}55`,
                  }}
                >
                  {char === ' ' ? '\u00A0' : char}
                </span>
              );
            })}
          </div>

          <div
            style={{
              height: 1,
              marginTop: 42,
              width: interpolate(frame, [40, 68], [0, width * 0.3], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
                easing: Easing.bezier(0.16, 1, 0.3, 1),
              }),
              background: `linear-gradient(90deg, rgba(255,255,255,0) 0%, ${accentColor} 50%, rgba(255,255,255,0) 100%)`,
            }}
          />

          {sub ? (
            <div
              style={{
                fontFamily: SANS,
                fontSize: 24,
                fontWeight: 300,
                letterSpacing: '0.18em',
                color: palette.muted,
                marginTop: 36,
                maxWidth: width * 0.78,
                textAlign: 'center',
                opacity: interpolate(frame, [58, 88], [0, 1], {
                  extrapolateLeft: 'clamp',
                  extrapolateRight: 'clamp',
                  easing: Easing.bezier(0.16, 1, 0.3, 1),
                }),
              }}
            >
              {sub}
            </div>
          ) : null}
        </AbsoluteFill>

        <div
          style={{
            position: 'absolute',
            bottom: 56,
            left: 90,
            right: 90,
            display: 'flex',
            justifyContent: 'space-between',
            fontFamily: SANS,
            fontSize: 14,
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            color: 'rgba(170,186,214,0.62)',
            opacity: interpolate(frame, [96, 124], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
          }}
        >
          <span>Remotion Hook</span>
          <span>{`${width} × ${height} · ${fps}fps`}</span>
          <span>Opening</span>
        </div>
      </AbsoluteFill>

      <Vignette />
      <Scanlines />
      <FilmGrain />
      <AbsoluteFill style={{backgroundColor: '#000', opacity: fadeOut}} />
    </AbsoluteFill>
  );
};
