import {noise} from '@remotion/effects/noise';
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
  TemplateProps,
  UI_SANS,
} from './theme';

const BARS = [0.32, 0.44, 0.38, 0.56, 0.5, 0.68, 0.62, 0.79, 0.72, 0.9, 0.84, 1];
const ROWS = ['Aurora workspace', 'Signal review', 'Render queue'];

const Backdrop: React.FC<{palette: Palette; accent: string}> = ({palette, accent}) => {
  const frame = useCurrentFrame();
  return (
    <>
      <AbsoluteFill style={{backgroundColor: palette.bg}} />
      <AbsoluteFill
        style={{
          background: `radial-gradient(ellipse at 18% 8%, ${accent}3d 0%, rgba(6,7,13,0) 52%),
            radial-gradient(ellipse at 86% 82%, ${palette.accent2}30 0%, rgba(6,7,13,0) 48%)`,
          filter: 'blur(30px)',
          translate: `${Math.sin(frame * 0.008) * 26}px ${Math.cos(frame * 0.011) * 18}px`,
          scale: 1.2,
        }}
      />
      <AbsoluteFill
        style={{
          backgroundImage:
            'linear-gradient(rgba(255,255,255,0.026) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.026) 1px, transparent 1px)',
          backgroundSize: '90px 90px',
        }}
      />
    </>
  );
};

const BrowserChrome: React.FC<{palette: Palette}> = ({palette}) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: 10,
      height: 42,
      padding: '0 18px',
      borderBottom: '1px solid rgba(255,255,255,0.08)',
      background: 'rgba(255,255,255,0.025)',
      fontFamily: UI_SANS,
      fontSize: 12,
      color: 'rgba(190,205,232,0.55)',
      letterSpacing: '0.08em',
    }}
  >
    <span style={{width: 9, height: 9, borderRadius: 99, background: '#ff6b6b'}} />
    <span style={{width: 9, height: 9, borderRadius: 99, background: '#ffc75f'}} />
    <span style={{width: 9, height: 9, borderRadius: 99, background: '#4be1c4'}} />
    <span style={{marginLeft: 14, color: palette.fg, opacity: 0.7}}>hook.local / opening</span>
  </div>
);

const Sidebar: React.FC<{palette: Palette; accent: string}> = ({palette, accent}) => {
  const frame = useCurrentFrame();
  return (
    <div
      style={{
        width: 196,
        borderRight: '1px solid rgba(255,255,255,0.07)',
        padding: '22px 18px',
        display: 'flex',
        flexDirection: 'column',
        gap: 22,
        fontFamily: UI_SANS,
        fontSize: 12,
        color: palette.muted,
      }}
    >
      <div
        style={{
          fontFamily: UI_SANS,
          fontWeight: 700,
          fontSize: 13,
          letterSpacing: '0.18em',
          color: palette.fg,
        }}
      >
        SIGMA
      </div>
      {['Overview', 'Signals', 'Timeline', 'Review'].map((item, i) => {
        const on = i === 1;
        const p = interpolate(frame, [18 + i * 5, 40 + i * 5], [0, 1], {
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        return (
          <div
            key={item}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              opacity: p,
              color: on ? palette.fg : palette.muted,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                background: on ? accent : 'rgba(255,255,255,0.16)',
              }}
            />
            {item}
          </div>
        );
      })}
    </div>
  );
};

const StatCard: React.FC<{
  label: string;
  index: number;
  palette: Palette;
  accent: string;
}> = ({label, index, palette, accent}) => {
  const frame = useCurrentFrame();
  const p = interpolate(frame, [32 + index * 8, 62 + index * 8], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const bar = [0.42, 0.66, 0.54][index % 3];
  return (
    <div
      style={{
        flex: 1,
        padding: '18px 20px',
        borderRadius: 14,
        border: '1px solid rgba(255,255,255,0.08)',
        background: 'linear-gradient(180deg, rgba(255,255,255,0.055), rgba(255,255,255,0.015))',
        opacity: p,
        translate: `0px ${(1 - p) * 22}px`,
        fontFamily: UI_SANS,
      }}
    >
      <div style={{fontSize: 11, letterSpacing: '0.18em', color: palette.muted, textTransform: 'uppercase'}}>
        {label}
      </div>
      <div style={{display: 'flex', alignItems: 'flex-end', gap: 6, marginTop: 14, height: 36}}>
        <div
          style={{
            width: 34,
            height: 22 + bar * 22,
            borderRadius: 5,
            background: `linear-gradient(180deg, ${accent}, ${accent}55)`,
            scale: `1 ${p}`,
            transformOrigin: 'bottom',
          }}
        />
        <div
          style={{
            width: 18,
            height: 14 + bar * 12,
            borderRadius: 4,
            background: 'rgba(255,255,255,0.16)',
            scale: `1 ${p}`,
            transformOrigin: 'bottom',
          }}
        />
        <div style={{fontSize: 12, color: palette.muted, marginLeft: 4}}>
          {`0${index + 1}`}
        </div>
      </div>
    </div>
  );
};

const Chart: React.FC<{palette: Palette; accent: string}> = ({palette, accent}) => {
  const frame = useCurrentFrame();
  const grow = interpolate(frame, [46, 96], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const points = BARS.map((v, i) => {
    const x = 22 + i * 58;
    const y = 168 - v * 132;
    return `${x},${y}`;
  }).join(' ');

  return (
    <div
      style={{
        flex: 1,
        borderRadius: 16,
        border: '1px solid rgba(255,255,255,0.08)',
        background: 'linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.012))',
        padding: '18px 22px 14px',
        fontFamily: UI_SANS,
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline'}}>
        <div style={{fontSize: 11, letterSpacing: '0.2em', color: palette.muted, textTransform: 'uppercase'}}>
          Opening signal
        </div>
        <div style={{fontSize: 11, color: palette.muted}}>LIVE</div>
      </div>

      <svg width="100%" height="200" viewBox="0 0 720 200" preserveAspectRatio="none" style={{marginTop: 10}}>
        <defs>
          <linearGradient id="hookLine" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={palette.accent2} />
            <stop offset="100%" stopColor={accent} />
          </linearGradient>
          <linearGradient id="hookFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity={0.22} />
            <stop offset="100%" stopColor={accent} stopOpacity={0} />
          </linearGradient>
        </defs>
        {[40, 80, 120, 160].map((y) => (
          <line key={y} x1="0" y1={y} x2="720" y2={y} stroke="rgba(255,255,255,0.06)" strokeWidth="1" />
        ))}
        <polyline points={`22,168 ${points} 700,168`} fill="url(#hookFill)" stroke="none" opacity={grow} />
        <polyline
          points={points}
          fill="none"
          stroke="url(#hookLine)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
          pathLength={1}
          strokeDasharray="1"
          strokeDashoffset={1 - grow}
        />
      </svg>

      <div style={{display: 'flex', gap: 18, marginTop: 4}}>
        {ROWS.map((row, i) => (
          <div key={row} style={{flex: 1, fontSize: 11, color: palette.muted, opacity: 0.7 + i * 0.1}}>
            <span style={{color: accent}}>0{i + 1}</span> {row}
          </div>
        ))}
      </div>
    </div>
  );
};

export const UIHook: React.FC<TemplateProps> = ({text, kicker, sub, accent}) => {
  const frame = useCurrentFrame();
  const {width, height, durationInFrames} = useVideoConfig();
  const palette = PALETTES.ui;
  const accentColor = pickAccent(palette, accent);
  const windowIn = interpolate(frame, [0, 26], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.bezier(0.16, 1, 0.3, 1),
  });
  const headlineSize = fitFontSize(text, width, 0.052, 72);
  const fadeOut = interpolate(
    frame,
    [durationInFrames - 14, durationInFrames],
    [0, 1],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );

  return (
    <AbsoluteFill style={{backgroundColor: palette.bg}}>
      <Backdrop palette={palette} accent={accentColor} />

      <AbsoluteFill style={{padding: '56px 72px 48px', justifyContent: 'center'}}>
        <div
          style={{
            fontFamily: UI_SANS,
            fontSize: 14,
            letterSpacing: '0.28em',
            textTransform: 'uppercase',
            color: accentColor,
            opacity: interpolate(frame, [8, 30], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
            marginBottom: 18,
          }}
        >
          {kicker || 'OPENING HOOK'}
        </div>

        <div
          style={{
            fontFamily: UI_SANS,
            fontWeight: 800,
            fontSize: headlineSize,
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
            color: palette.fg,
            maxWidth: width * 0.78,
            opacity: interpolate(frame, [10, 38], [0, 1], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
            }),
            translate: `0px ${interpolate(frame, [10, 44], [24, 0], {
              extrapolateLeft: 'clamp',
              extrapolateRight: 'clamp',
              easing: Easing.bezier(0.16, 1, 0.3, 1),
            })}px`,
          }}
        >
          {text}
        </div>

        {sub ? (
          <div
            style={{
              fontFamily: UI_SANS,
              fontSize: 19,
              lineHeight: 1.5,
              color: palette.muted,
              marginTop: 16,
              maxWidth: width * 0.62,
              opacity: interpolate(frame, [28, 54], [0, 1], {
                extrapolateLeft: 'clamp',
                extrapolateRight: 'clamp',
              }),
            }}
          >
            {sub}
          </div>
        ) : null}

        <div
          style={{
            marginTop: 34,
            borderRadius: 18,
            border: '1px solid rgba(255,255,255,0.09)',
            background: 'rgba(12,15,24,0.78)',
            boxShadow: '0 40px 120px rgba(0,0,0,0.55)',
            overflow: 'hidden',
            opacity: windowIn,
            scale: 0.96 + windowIn * 0.04,
            translate: `0px ${(1 - windowIn) * 34}px`,
          }}
        >
          <BrowserChrome palette={palette} />
          <div style={{display: 'flex', height: 360}}>
            <Sidebar palette={palette} accent={accentColor} />
            <div style={{flex: 1, padding: '22px 24px', display: 'flex', flexDirection: 'column', gap: 14}}>
              <div style={{display: 'flex', gap: 12}}>
                {['Signal', 'Momentum', 'Clarity'].map((label, i) => (
                  <StatCard key={label} label={label} index={i} palette={palette} accent={accentColor} />
                ))}
              </div>
              <Chart palette={palette} accent={accentColor} />
            </div>
          </div>
        </div>
      </AbsoluteFill>

      <div
        style={{
          position: 'absolute',
          left: 96,
          right: 96,
          bottom: 42,
          display: 'flex',
          justifyContent: 'space-between',
          fontFamily: UI_SANS,
          fontSize: 12,
          letterSpacing: '0.18em',
          color: 'rgba(170,186,214,0.5)',
        }}
      >
        <span>REMOTION HOOK</span>
        <span>{`${width} × ${height}`}</span>
        <span>01 / OPENING</span>
      </div>

      <AbsoluteFill
        style={{
          opacity: 0.08,
          mixBlendMode: 'overlay',
          pointerEvents: 'none',
        }}
      >
        <Solid width={width} height={height} color="#808080" effects={[noise({amount: 0.8, seed: frame})]} />
      </AbsoluteFill>
      <AbsoluteFill style={{backgroundColor: '#000', opacity: fadeOut}} />
    </AbsoluteFill>
  );
};
