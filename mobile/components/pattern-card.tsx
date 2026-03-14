/**
 * components/pattern-card.tsx
 * ============================
 * A tappable pattern insight card.
 *
 * Behaviour
 * ---------
 * - Body text is clamped to 3 lines by default.
 * - A single tap expands the card to show the full text (no modal needed).
 * - When expanded, a "Show less" chevron appears — tapping again collapses it.
 * - The card entrance animation is preserved.
 */

import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import Animated, { FadeInDown } from "react-native-reanimated";
import { Ionicons } from "@expo/vector-icons";

import { useSpiralTheme } from "@/context/theme-context";
import { EmotionColors, SpiralRadius, SpiralSpacing } from "@/constants/theme";

export interface PatternCardData {
  id: string;
  icon: keyof typeof Ionicons.glyphMap;
  title: string;
  body: string;
  /** Maps to EmotionColors for accent */
  emotion: string;
  timeframe: string;
}

interface PatternCardProps {
  card: PatternCardData;
  index: number;
}

export function PatternCard({ card, index }: PatternCardProps) {
  const { C } = useSpiralTheme();
  const accent = EmotionColors[card.emotion] ?? C.amber;
  const [expanded, setExpanded] = useState(false);

  return (
    <Animated.View
      entering={FadeInDown.delay(index * 130).springify().damping(18)}
      style={[
        styles.card,
        {
          backgroundColor: C.surface,
          borderColor: C.border,
          borderLeftColor: accent,
        },
      ]}
    >
      <View style={[styles.iconWrap, { backgroundColor: accent + "22" }]}>
        <Ionicons name={card.icon} size={22} color={accent} />
      </View>

      <View style={styles.content}>
        <Text style={[styles.timeframe, { color: accent }]}>
          {card.timeframe}
        </Text>
        <Text style={[styles.title, { color: C.textPrimary }]}>
          {card.title}
        </Text>

        {/* Body — expands / collapses on tap */}
        <Pressable onPress={() => setExpanded((e) => !e)} hitSlop={6}>
          <Text
            style={[styles.body, { color: C.textSecondary }]}
            numberOfLines={expanded ? undefined : 3}
          >
            {card.body}
          </Text>

          {/* Tap hint only when collapsed */}
          {!expanded && (
            <View style={styles.readMoreRow}>
              <Text style={[styles.readMoreLabel, { color: accent }]}>
                Read more
              </Text>
              <Ionicons
                name="chevron-down"
                size={12}
                color={accent}
                style={{ marginTop: 1 }}
              />
            </View>
          )}

          {/* Collapse affordance when expanded */}
          {expanded && (
            <View style={styles.readMoreRow}>
              <Text style={[styles.readMoreLabel, { color: C.textMuted }]}>
                Show less
              </Text>
              <Ionicons
                name="chevron-up"
                size={12}
                color={C.textMuted}
                style={{ marginTop: 1 }}
              />
            </View>
          )}
        </Pressable>
      </View>
    </Animated.View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: SpiralRadius.lg,
    borderWidth: 1,
    borderLeftWidth: 3,
    padding: SpiralSpacing.md,
    marginBottom: SpiralSpacing.sm,
    flexDirection: "row",
    gap: SpiralSpacing.md,
    alignItems: "flex-start",
  },
  iconWrap: {
    width: 44,
    height: 44,
    borderRadius: SpiralRadius.md,
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
    marginTop: 2,
  },
  content: {
    flex: 1,
    gap: 4,
  },
  timeframe: {
    fontSize: 10,
    fontWeight: "700",
    letterSpacing: 1.4,
    textTransform: "uppercase",
  },
  title: {
    fontSize: 15,
    fontWeight: "700",
    lineHeight: 20,
  },
  body: {
    fontSize: 13,
    lineHeight: 19,
  },
  readMoreRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 3,
    marginTop: 4,
  },
  readMoreLabel: {
    fontSize: 12,
    fontWeight: "600",
  },
});
