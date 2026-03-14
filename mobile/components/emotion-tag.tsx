import React from "react";
import { StyleSheet, Text, View, type ViewStyle } from "react-native";

import { useSpiralTheme } from "@/context/theme-context";
import {
  EmotionColors,
  SpiralRadius,
  SpiralSpacing,
} from "@/constants/theme";

interface EmotionTagProps {
  emotion: string;
  style?: ViewStyle;
}

export function EmotionTag({ emotion, style }: EmotionTagProps) {
  const { C } = useSpiralTheme();
  const color = EmotionColors[emotion.toLowerCase()] ?? C.textMuted;
  const label = emotion.charAt(0).toUpperCase() + emotion.slice(1);

  return (
    <View
      style={[
        styles.tag,
        { backgroundColor: color + "22", borderColor: color + "66" },
        style,
      ]}
    >
      <View style={[styles.dot, { backgroundColor: color }]} />
      <Text style={[styles.label, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  tag: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: SpiralSpacing.sm,
    paddingVertical: SpiralSpacing.xs,
    borderRadius: SpiralRadius.pill,
    borderWidth: 1,
    gap: 4,
  },
  dot: {
    width: 6,
    height: 6,
    borderRadius: 3,
  },
  label: {
    fontSize: 11,
    fontWeight: "600",
    letterSpacing: 0.3,
  },
});
