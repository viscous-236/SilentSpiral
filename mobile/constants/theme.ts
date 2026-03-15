/**
 * Below are the colors that are used in the app. The colors are defined in the light and dark mode.
 * There are many other ways to style your app. For example, [Nativewind](https://www.nativewind.dev/), [Tamagui](https://tamagui.dev/), [unistyles](https://reactnativeunistyles.vercel.app), etc.
 */

import { Platform } from 'react-native';

const tintColorLight = '#0a7ea4';
const tintColorDark = '#fff';

export const Colors = {
  light: {
    text: '#11181C',
    background: '#fff',
    tint: tintColorLight,
    icon: '#687076',
    tabIconDefault: '#687076',
    tabIconSelected: tintColorLight,
  },
  dark: {
    text: '#ECEDEE',
    background: '#151718',
    tint: tintColorDark,
    icon: '#9BA1A6',
    tabIconDefault: '#9BA1A6',
    tabIconSelected: tintColorDark,
  },
};

// ─── Reflectra Design System ────────────────────────────────────────────────

export const SpiralColorsDark = {
  midnight:        '#0B0F1A',
  surface:         '#131929',
  surfaceElevated: '#1A2236',
  border:          '#1E2D45',

  amber:     '#F4A261',
  amberDim:  'rgba(244,162,97,0.15)',
  violet:    '#A78BFA',
  violetDim: 'rgba(167,139,250,0.15)',
  teal:      '#5EEAD4',
  tealDim:   'rgba(94,234,212,0.15)',

  textPrimary:   '#E8EDF5',
  textSecondary: '#8B9CC8',
  textMuted:     '#4A5578',
  overlay:       'rgba(11,15,26,0.8)',
};

export const SpiralColorsLight = {
  midnight:        '#FAF7F2',
  surface:         '#FFFFFF',
  surfaceElevated: '#F0EBE0',
  border:          '#E8DDD0',

  amber:     '#C96A1E',
  amberDim:  'rgba(201,106,30,0.10)',
  violet:    '#6B46C0',
  violetDim: 'rgba(107,70,192,0.10)',
  teal:      '#0B7A6E',
  tealDim:   'rgba(11,122,110,0.10)',

  textPrimary:   '#1C1408',
  textSecondary: '#5C4B35',
  textMuted:     '#A08C75',
  overlay:       'rgba(250,247,242,0.90)',
};

/** Backward-compat alias — points to dark palette */
export const SpiralColors = SpiralColorsDark;

/** Maps emotion names → brand color */
export const EmotionColors: Record<string, string> = {
  joy:     '#F4A261',
  calm:    '#5EEAD4',
  sadness: '#60A5FA',
  anxiety: '#A78BFA',
  anger:   '#F87171',
  neutral: '#8B9CC8',
};

export const SpiralSpacing = {
  xs:  4,
  sm:  8,
  md:  16,
  lg:  24,
  xl:  32,
  xxl: 48,
} as const;

export const SpiralRadius = {
  sm:   8,
  md:   12,
  lg:   16,
  xl:   24,
  pill: 100,
} as const;

export const Fonts = Platform.select({
  ios: {
    /** iOS `UIFontDescriptorSystemDesignDefault` */
    sans: 'system-ui',
    /** iOS `UIFontDescriptorSystemDesignSerif` */
    serif: 'ui-serif',
    /** iOS `UIFontDescriptorSystemDesignRounded` */
    rounded: 'ui-rounded',
    /** iOS `UIFontDescriptorSystemDesignMonospaced` */
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif",
    serif: "Georgia, 'Times New Roman', serif",
    rounded: "'SF Pro Rounded', 'Hiragino Maru Gothic ProN', Meiryo, 'MS PGothic', sans-serif",
    mono: "SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace",
  },
});
