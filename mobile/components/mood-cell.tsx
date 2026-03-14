import React from "react";
import { StyleSheet, Text, View, type ViewStyle } from "react-native";

import { useSpiralTheme } from "@/context/theme-context";
import { EmotionColors } from "@/constants/theme";

interface MoodCellProps {
  date?: number;
  emotion?: string;
  style?: ViewStyle;
}

export function MoodCell({ date, emotion, style }: MoodCellProps) {
  const { C } = useSpiralTheme();
  const color = emotion
    ? (EmotionColors[emotion] ?? C.textMuted)
    : undefined;

  return (
    <View
      style={[
        styles.cell,
        {
          backgroundColor: color ? color + "33" : C.surface,
          borderColor: color ? color + "77" : C.border,
        },
        style,
      ]}
    >
      {date !== undefined && (
        <Text style={[styles.date, { color: color ?? C.textMuted }]}>
          {date}
        </Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  cell: {
    width: 36,
    height: 36,
    borderRadius: 6,
    borderWidth: 1,
    alignItems: "center",
    justifyContent: "center",
    margin: 2,
  },
  date: {
    fontSize: 11,
    fontWeight: "600",
  },
});
