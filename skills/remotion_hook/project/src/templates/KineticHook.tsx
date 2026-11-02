import {chromaticAberration} from '@remotion/effects/chromatic-aberration';
import {lightTrail} from '@remotion/effects/light-trail';
import {noise} from '@remotion/effects/noise';
import {Trail} from '@remotion/motion-blur';
import {
  AbsoluteFill,
  Easing,
  interpolate,
  Solid,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {
  fitFontSize,
  Palette,
  PALETTES,
  pickAccent,
  SANS,
  splitChars,
  TemplateProps,
} from './theme';

type Streak = {
  color: string;
  x: number;
  speed: number;
  delay: number;
  w: number;
  h: number;
};

const buildStreaks = (accent: string, accent2: string): Streak[] => [
  {color: accent, x: 12, speed: 34, delay: 0, w: 10, h: 0.42},
  {color: '#ff5f9e', x: 78, speed: -30, delay: 3, w: 6, h: 0.28},
  {color: accent2, x: 30, speed: 26, delay: 6, w: 14, h: 0.62},
  {color: '#ffc75f', x: 64, speed: -22, delay: 9, w: 8, h: 0.2},
  {color: '#ffffff', x: 46, speed: 40, delay: 1, w: 3, h: 0.78},
  {color: '#8b5bff', x: 88, speed: -36, delay: 5, w: 8, h: 0.36},
];

const Streaks: React.FC<{streaks: Streak[]}> = ({streaks}) => {
  const frame = useCurrentFrame();
  const {width, height, durationInFrames} = useVideoConfig();

  return (
    <AbsoluteFill>
      {streaks.map((s, i) => {
        const local = frame - s.delay;
        const travel = width * 1.6;
        const x = interpolate(
          local,
          [0, durationInFrames],
          [
            (s.x / 100) * width - travel * 0.5,
            (s.x / 100) * width + travel * 0.5 * Math.sign(s.speed),
          ],
          {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
            easing: Easing.bezier(0.35, 0, 0.25, 1),
          },
        );
        const enter = interpolate(local, [0, 10], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        const exit = interpolate(frame, [durationInFrames - 20, durationInFrames], [1, 0], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        const barH = height * s.h;
        return (
          <div
            key={i}
            style={{
              position: 'absolute',
              left: x,
              top: (height - barH) / 2,
              width: s.w,
              height: barH,
              borderRadius: s.w / 2,
              background: `linear-gradient(180deg, rgba(255,255,255,0) 0%, ${s.color} 22%, #ffffff 50%, ${s.color} 78%, rgba(255,255,255,0) 100%)`,
              opacity: enter * exit,
              boxShadow: `0 0 26px ${s.color}`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

const Word: React.FC<{text: string; palette: Palette; accent: string}> = ({
  text,
  palette,
  accent,
}) => {
  const frame = useCurrentFrame();
  const {width} = useVideoConfig();
  const chars = splitChars(text);
  const fontSize = Math.min(
    fitFontSize(text, width, 0.115, width * 0.16),
    (width * 0.78) / Math.max(4, chars.length),
  );
  const sweepAmp = width * 0.08;
  const sweep = interpolate(frame, [46, 96], [-sweepAmp, sweepAmp], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.5, 0, 0.2, 1),
  });
  const reveal = interpolate(frame, [16, 44], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });

  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', padding: '0 64px'}}>
      <div style={{display: 'flex', translate: `${sweep}px 0px`, maxWidth: '100%'}}>
        <div
          style={{
            position: 'relative',
            display: 'flex',
            fontFamily: SANS,
            fontWeight: 900,
            fontSize,
            lineHeight: 1,
            letterSpacing: '-0.01em',
            color: palette.fg,
            opacity: reveal,
            scale: interpolate(frame, [16, 44], [1.14, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            }),
            textShadow: `0 0 36px ${accent}66`,
          }}
        >
          {chars.map((c, i) => {
            const start = 16 + i * Math.max(1.2, 2.4 - chars.length * 0.04);
            const p = interpolate(frame, [start, start + 20], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            });
            return (
              <span
                key={i}
                style={{
                  display: 'inline-block',
                  translate: `0px ${(1 - p) * -52}px`,
                  opacity: p,
                  filter: `blur(${(1 - p) * 10}px)`,
                }}
              >
                {c === ' ' ? '\u00A0' : c}
              </span>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const AccentTrail: React.FC<{accent: string}> = ({accent}) => {
  const frame = useCurrentFrame();
  const {width, height} = useVideoConfig();
  const x = interpolate(frame, [0, 60], [-width * 0.4, width * 1.1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.6, 0, 0.2, 1),
  });
  const opacity = interpolate(frame, [0, 8, 54, 68], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });

  return (
    <div style={{position: 'absolute', left: x, top: height * 0.24, opacity, mixBlendMode: 'screen'}}>
      <Solid
        width={340}
        height={4}
        color={accent}
        effects={[
          lightTrail({distance: 220, intensity: 3.2, color: accent, threshold: 0.05}),
          chromaticAberration({amount: 14, angle: 0}),
        ]}
      />
    </div>
  );
};

export const KineticHook: React.FC<TemplateProps> = ({text, kicker, sub, accent}) => {
  const frame = useCurrentFrame();
  const {width, height, durationInFrames} = useVideoConfig();
  const palette = PALETTES.kinetic;
  const accentColor = pickAccent(palette, accent);
  const streaks = buildStreaks(accentColor, palette.accent2);
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  const label = (kicker || 'OPENING HOOK').toUpperCase();

  return (
    <AbsoluteFill style={{backgroundColor: palette.bg}}>
      <AbsoluteFill
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.028) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.028) 1px, transparent 1px)',
          backgroundSize: '120px 120px',
        }}
      />
      <AbsoluteFill
        style={{
          background: `radial-gradient(circle at 50% 50%, ${accentColor}28 0%, rgba(0,0,0,0) 55%)`,
        }}
      />

      <Trail layers={14} lagInFrames={2} trailOpacity={0.32}>
        <Streaks streaks={streaks} />
      </Trail>
      <AbsoluteFill>
        <AccentTrail accent={accentColor} />
      </AbsoluteFill>

      <Word text={text} palette={palette} accent={accentColor} />

      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: height * 0.14,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 16,
          fontFamily: SANS,
          color: palette.muted,
        }}
      >
        <div
          style={{
            fontSize: 16,
            letterSpacing: '0.42em',
            textTransform: 'uppercase',
            opacity: interpolate(frame, [54, 84], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
          }}
        >
          {label}
        </div>
        {sub ? (
          <div
            style={{
              maxWidth: width * 0.76,
              textAlign: 'center',
              fontSize: 22,
              letterSpacing: '0.14em',
              color: palette.muted,
              opacity: interpolate(frame, [64, 92], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              }),
            }}
          >
            {sub}
          </div>
        ) : null}
      </div>

      <AbsoluteFill
        style={{
          background:
            'radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 42%, rgba(0,0,0,0.6) 82%, rgba(0,0,0,0.95) 100%)',
        }}
      />
      <AbsoluteFill style={{opacity: 0.11, mixBlendMode: 'overlay'}}>
        <Solid width={width} height={height} color="#808080" effects={[noise({amount: 0.85, seed: frame})]} />
      </AbsoluteFill>
      <AbsoluteFill style={{backgroundColor: '#000', opacity: fadeOut}} />
    </AbsoluteFill>
  );
};
