import React, { createContext, useCallback, useContext, useState } from 'react';

import { SpiralColorsDark, SpiralColorsLight } from '@/constants/theme';

export type SpiralColorSet = typeof SpiralColorsDark;

type ThemeContextType = {
  isDark: boolean;
  toggleTheme: () => void;
  C: SpiralColorSet;
};

const ThemeContext = createContext<ThemeContextType>({
  isDark: true,
  toggleTheme: () => {},
  C: SpiralColorsDark,
});

export function SpiralThemeProvider({ children }: { children: React.ReactNode }) {
  const [isDark, setIsDark] = useState(true);
  const toggleTheme = useCallback(() => setIsDark((d) => !d), []);
  const C = isDark ? SpiralColorsDark : SpiralColorsLight;

  return (
    <ThemeContext.Provider value={{ isDark, toggleTheme, C }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useSpiralTheme() {
  return useContext(ThemeContext);
}
