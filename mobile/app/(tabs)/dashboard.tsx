import React, { useMemo } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { AtmosphericBackground } from "@/components/atmospheric-background";
import { MoodCell } from "@/components/mood-cell";
import { SpiralScoreCard } from "@/components/spiral-score-card";
import { PatternCard } from "@/components/pattern-card";
import { SpiralColorSet, useSpiralTheme } from "@/context/theme-context";
import {
  EmotionColors,
  SpiralRadius,
  SpiralSpacing,
} from "@/constants/theme";
import { useDashboardData } from "@/hooks/use-dashboard-data";

// ─── Constants ────────────────────────────────────────────────────────────────
const WEEK_DAYS = ["S", "M", "T", "W", "T", "F", "S"];
const EMOTION_KEYS = [
  "joy",
  "calm",
  "sadness",
  "anxiety",
  "anger",
  "neutral",
] as const;
type Emotion = (typeof EMOTION_KEYS)[number];

const BAR_MAX_HEIGHT = 80;

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function DashboardScreen() {
  const { C, isDark, toggleTheme } = useSpiralTheme();
  const styles = useMemo(() => makeStyles(C), [C]);

  const {
    heatmap,
    timeline,
    spiralScore,
    patternCards,
    coachChallenge,
    coachSuggestions,
    anomaly,
    loading,
    patternLoading,
    coachLoading,
    hasData,
  } = useDashboardData();

  const anomalyLabel =
    anomaly === null
      ? "Stable window"
      : anomaly
          .toLowerCase()
          .replace(/_/g, " ")
          .replace(/\b\w/g, (s) => s.toUpperCase());

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <AtmosphericBackground variant="insights" />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Header ───────────────────────────────────────────────────── */}
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.pageTitle}>Your Insights</Text>
            <Text style={styles.pageSubtitle}>
              Patterns emerging from your journey
            </Text>
          </View>
          <Pressable onPress={toggleTheme} style={styles.themeToggle} hitSlop={8}>
            <Ionicons
              name={isDark ? "sunny-outline" : "moon-outline"}
              size={20}
              color={C.amber}
            />
          </Pressable>
        </View>

        <View style={[styles.pulseStrip, { backgroundColor: C.surface, borderColor: C.border }]}> 
          <View style={styles.pulseItem}>
            <Text style={[styles.pulseLabel, { color: C.textMuted }]}>Window Signal</Text>
            <Text style={[styles.pulseValue, { color: C.textPrimary }]}>{anomalyLabel}</Text>
          </View>
          <View style={[styles.pulseDivider, { backgroundColor: C.border }]} />
          <View style={styles.pulseItem}>
            <Text style={[styles.pulseLabel, { color: C.textMuted }]}>Data Points</Text>
            <Text style={[styles.pulseValue, { color: C.textPrimary }]}>{timeline.length}</Text>
          </View>
        </View>

        {/* ── Spiral Score ─────────────────────────────────────────────── */}
        <View style={styles.card}>
          <SpiralScoreCard score={spiralScore} />
        </View>

        {/* ── Micro-Commit Challenge ───────────────────────────────────── */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Tomorrow&apos;s Micro-Challenge</Text>
          <Text style={styles.cardSubtitle}>Tiny action, meaningful momentum</Text>

          {coachLoading ? (
            <View style={styles.patternLoadingRow}>
              <ActivityIndicator color={C.amber} />
              <Text style={[styles.emptyText, { color: C.textMuted }]}>Crafting your challenge…</Text>
            </View>
          ) : coachChallenge ? (
            <>
              <View style={[styles.challengeCard, { backgroundColor: C.surfaceElevated, borderColor: C.border }]}> 
                <Ionicons name="flag-outline" size={18} color={C.amber} style={{ marginTop: 2 }} />
                <Text style={[styles.challengeText, { color: C.textPrimary }]}>{coachChallenge}</Text>
              </View>
              {coachSuggestions.map((item, idx) => (
                <View key={`${item}-${idx}`} style={styles.suggestionRow}>
                  <View style={[styles.suggestionDot, { backgroundColor: C.teal }]} />
                  <Text style={[styles.suggestionText, { color: C.textSecondary }]}>{item}</Text>
                </View>
              ))}
            </>
          ) : (
            <Text style={[styles.emptyText, { color: C.textMuted }]}>No active challenge right now. Keep journaling to unlock personalized daily steps.</Text>
          )}
        </View>

        {/* ── Mood Heatmap ─────────────────────────────────────────────── */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Mood Heatmap</Text>
          <Text style={styles.cardSubtitle}>Last 5 weeks</Text>

          {loading ? (
            <ActivityIndicator color={C.amber} style={{ marginVertical: SpiralSpacing.md }} />
          ) : (
            <>
              <View style={styles.heatmapDayRow}>
                {WEEK_DAYS.map((d, i) => (
                  <Text key={i} style={styles.heatmapDayLabel}>
                    {d}
                  </Text>
                ))}
              </View>

              {heatmap.map((week, wi) => (
                <View key={wi} style={styles.heatmapRow}>
                  {week.map((emotion, di) => (
                    <MoodCell key={di} emotion={emotion as Emotion | undefined} />
                  ))}
                </View>
              ))}

              {/* Legend */}
              <View style={styles.legend}>
                {EMOTION_KEYS.map((e) => (
                  <View key={e} style={styles.legendItem}>
                    <View
                      style={[
                        styles.legendDot,
                        { backgroundColor: EmotionColors[e] },
                      ]}
                    />
                    <Text style={styles.legendLabel}>{e}</Text>
                  </View>
                ))}
              </View>
            </>
          )}
        </View>

        {/* ── Emotion Timeline ─────────────────────────────────────────── */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Emotion Timeline</Text>
          <Text style={styles.cardSubtitle}>
            Last 14 days · dominant feeling
          </Text>

          {loading ? (
            <ActivityIndicator color={C.amber} style={{ marginVertical: SpiralSpacing.md }} />
          ) : timeline.length === 0 ? (
            <Text style={[styles.emptyText, { color: C.textMuted }]}>
              Start journaling to see your emotional timeline.
            </Text>
          ) : (
            <ScrollView
              horizontal
              showsHorizontalScrollIndicator={false}
              style={styles.timelineScroll}
            >
              <View style={styles.timelineBars}>
                {timeline.map((item, i) => {
                  const barH = Math.round(item.intensity * BAR_MAX_HEIGHT);
                  const color = EmotionColors[item.emotion as Emotion] ?? C.border;
                  return (
                    <View key={i} style={styles.barColumn}>
                      <View
                        style={[
                          styles.bar,
                          {
                            height: barH,
                            backgroundColor: color + "BB",
                            borderColor: color,
                          },
                        ]}
                      />
                      <Text style={styles.barLabel}>{item.day}</Text>
                    </View>
                  );
                })}
              </View>
            </ScrollView>
          )}
        </View>

        {/* ── Temporal Pattern Cards ───────────────────────────────── */}
        <View style={styles.card}>
          <Text style={styles.cardTitle}>What We&apos;ve Noticed</Text>
          <Text style={styles.cardSubtitle}>
            Patterns surfaced by your entries
          </Text>

          {patternLoading ? (
            <View style={styles.patternLoadingRow}>
              <ActivityIndicator color={C.amber} />
              <Text style={[styles.emptyText, { color: C.textMuted }]}>
                Analysing your patterns…
              </Text>
            </View>
          ) : patternCards.length === 0 ? (
            <View style={styles.emptyStateBox}>
              <Ionicons
                name={hasData ? "sparkles-outline" : "journal-outline"}
                size={32}
                color={C.textMuted}
                style={{ marginBottom: SpiralSpacing.sm }}
              />
              <Text style={[styles.emptyText, { color: C.textPrimary, fontWeight: "600" }]}>
                {hasData ? "Almost there" : "Start your journey"}
              </Text>
              <Text style={[styles.emptyText, { color: C.textMuted, marginTop: 4 }]}>
                {hasData
                  ? "Add at least 2 journal entries so your AI companion can surface patterns."
                  : "Write your first journal entry or log a mood check-in to begin tracking your emotional patterns."}
              </Text>
            </View>
          ) : (
            patternCards.map((card, i) => (
              <PatternCard key={card.id} card={card} index={i} />
            ))
          )}
        </View>

        {/* Spacer for floating tab bar */}
        <View style={{ height: 100 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
function makeStyles(C: SpiralColorSet) {
  return StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.midnight },
  scroll: { flex: 1 },
  scrollContent: {
    paddingHorizontal: SpiralSpacing.lg,
    paddingTop: SpiralSpacing.md,
  },

  headerRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    justifyContent: "space-between",
    marginBottom: SpiralSpacing.lg,
  },
  pageTitle: {
    fontSize: 28,
    fontWeight: "700",
    color: C.textPrimary,
    letterSpacing: -0.5,
    marginBottom: 4,
  },
  pageSubtitle: {
    fontSize: 14,
    color: C.textSecondary,
  },
  themeToggle: {
    width: 40,
    height: 40,
    borderRadius: SpiralRadius.pill,
    backgroundColor: C.amberDim,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: C.amber + "44",
    marginTop: 2,
  },

  card: {
    backgroundColor: C.surface,
    borderRadius: SpiralRadius.xl,
    borderWidth: 1,
    borderColor: C.border,
    padding: SpiralSpacing.lg,
    marginBottom: SpiralSpacing.md,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: "700",
    color: C.textPrimary,
    marginBottom: 2,
  },
  cardSubtitle: {
    fontSize: 12,
    color: C.textMuted,
    marginBottom: SpiralSpacing.md,
  },

  pulseStrip: {
    borderWidth: 1,
    borderRadius: SpiralRadius.lg,
    paddingHorizontal: SpiralSpacing.md,
    paddingVertical: SpiralSpacing.sm,
    marginBottom: SpiralSpacing.md,
    flexDirection: "row",
    alignItems: "center",
  },
  pulseItem: {
    flex: 1,
  },
  pulseLabel: {
    fontSize: 11,
    textTransform: "uppercase",
    letterSpacing: 1.2,
    fontWeight: "700",
    marginBottom: 4,
  },
  pulseValue: {
    fontSize: 14,
    fontWeight: "700",
  },
  pulseDivider: {
    width: 1,
    alignSelf: "stretch",
    marginHorizontal: SpiralSpacing.md,
  },

  challengeCard: {
    borderWidth: 1,
    borderRadius: SpiralRadius.md,
    padding: SpiralSpacing.md,
    flexDirection: "row",
    gap: SpiralSpacing.sm,
    marginBottom: SpiralSpacing.sm,
  },
  challengeText: {
    flex: 1,
    fontSize: 15,
    lineHeight: 22,
    fontWeight: "600",
  },
  suggestionRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 8,
    marginTop: 8,
  },
  suggestionDot: {
    width: 6,
    height: 6,
    borderRadius: 3,
    marginTop: 7,
  },
  suggestionText: {
    flex: 1,
    fontSize: 13,
    lineHeight: 19,
  },

  // Heatmap
  heatmapDayRow: {
    flexDirection: "row",
    marginBottom: 4,
    paddingHorizontal: 2,
  },
  heatmapDayLabel: {
    width: 40,
    textAlign: "center",
    fontSize: 11,
    color: C.textMuted,
    fontWeight: "600",
  },
  heatmapRow: { flexDirection: "row", marginBottom: 0 },

  // Legend
  legend: {
    flexDirection: "row",
    flexWrap: "wrap",
    marginTop: SpiralSpacing.md,
    gap: 8,
  },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 4 },
  legendDot: { width: 8, height: 8, borderRadius: 4 },
  legendLabel: {
    fontSize: 11,
    color: C.textMuted,
    textTransform: "capitalize",
  },

  // Timeline
  timelineScroll: { marginTop: 4 },
  timelineBars: {
    flexDirection: "row",
    alignItems: "flex-end",
    gap: 6,
    paddingBottom: 8,
    minHeight: BAR_MAX_HEIGHT + 32,
  },
  barColumn: { alignItems: "center", gap: 6 },
  bar: { width: 28, borderRadius: SpiralRadius.sm, borderWidth: 1 },
  barLabel: { fontSize: 10, color: C.textMuted, fontWeight: "600" },

  // Empty / loading states
  emptyStateBox: {
    alignItems: "center",
    paddingVertical: SpiralSpacing.lg,
  },
  emptyText: {
    fontSize: 14,
    lineHeight: 20,
    textAlign: "center",
    paddingVertical: 2,
  },
  patternLoadingRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: SpiralSpacing.sm,
    paddingVertical: SpiralSpacing.md,
  },
  });
}
