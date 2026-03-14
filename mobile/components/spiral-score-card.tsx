/**
 * components/spiral-score-card.tsx
 * ==================================
 * Animated ring card that displays the user's Spiral Score (0–100).
 *
 * Changes
 * -------
 * - Added an ⓘ info button next to the title.
 * - Tapping it opens a Modal with a plain-language explanation of what
 *   the Spiral Score is and how each tier maps to a meaning.
 * - Modal matches the app's dark/light theme via useSpiralTheme().
 */

import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  Animated,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";

import { SpiralColorSet, useSpiralTheme } from "@/context/theme-context";
import { SpiralRadius, SpiralSpacing } from "@/constants/theme";

interface SpiralScoreCardProps {
  score: number; // 0–100
  label?: string;
}

const SCORE_THRESHOLDS = {
  thriving: 85,
  balanced: 70,
  wavering: 50,
  struggling: 30,
} as const;

function getScoreColor(score: number, C: SpiralColorSet) {
  if (score >= SCORE_THRESHOLDS.balanced) return C.teal;
  if (score >= SCORE_THRESHOLDS.wavering) return C.amber;
  return C.violet;
}

function getScoreStatus(score: number) {
  if (score >= SCORE_THRESHOLDS.thriving) return "Thriving";
  if (score >= SCORE_THRESHOLDS.balanced) return "Balanced";
  if (score >= SCORE_THRESHOLDS.wavering) return "Wavering";
  if (score >= SCORE_THRESHOLDS.struggling) return "Struggling";
  return "Spiraling";
}

const RING = 156;

// ── Score tiers shown in the explainer modal ──────────────────────────────────
const TIERS = [
  { range: "85 – 100", label: "Thriving", desc: "Your emotional signal is strong and steady. Supportive emotions and consistency are showing up clearly." },
  { range: "70 – 84",  label: "Balanced", desc: "You're mostly steady. There are normal ups and downs, but your overall pattern remains grounded." },
  { range: "50 – 69",  label: "Wavering", desc: "A mixed window. Helpful and difficult emotions are both present, and your signal is still settling." },
  { range: "30 – 49",  label: "Struggling", desc: "Difficult emotions or irregular patterns are taking more space right now. Noticing this is meaningful progress." },
  { range: "0 – 29",   label: "Spiraling",  desc: "This window looks heavy and unstable. Use the insights gently and focus on one small step at a time." },
];

export function SpiralScoreCard({ score, label }: SpiralScoreCardProps) {
  const { C } = useSpiralTheme();
  const styles = useMemo(() => makeStyles(C), [C]);
  const glowAnim = useRef(new Animated.Value(0.35)).current;
  const color = getScoreColor(score, C);
  const [showInfo, setShowInfo] = useState(false);

  useEffect(() => {
    Animated.loop(
      Animated.sequence([
        Animated.timing(glowAnim, { toValue: 1, duration: 2200, useNativeDriver: true }),
        Animated.timing(glowAnim, { toValue: 0.35, duration: 2200, useNativeDriver: true }),
      ]),
    ).start();
  }, [glowAnim]);

  return (
    <>
      <View style={styles.wrap}>
        {/* Title row */}
        <View style={styles.titleRow}>
          <Text style={styles.cardLabel}>{label ?? "Reflection Consistency Score"}</Text>
          <Pressable
            onPress={() => setShowInfo(true)}
            hitSlop={10}
            style={styles.infoBtn}
          >
            <Ionicons name="information-circle-outline" size={18} color={C.textMuted} />
          </Pressable>
        </View>

        {/* Animated ring */}
        <View style={styles.ringWrap}>
          <Animated.View
            style={[styles.glow, { borderColor: color, opacity: glowAnim }]}
          />
          <View style={[styles.ring, { borderColor: color }]}>
            <Text style={[styles.number, { color }]}>{score}</Text>
            <Text style={[styles.status, { color: C.textSecondary }]}>
              {getScoreStatus(score)}
            </Text>
          </View>
        </View>
      </View>

      {/* ── Explainer Modal ───────────────────────────────────────────────── */}
      <Modal
        visible={showInfo}
        transparent
        animationType="fade"
        statusBarTranslucent
        onRequestClose={() => setShowInfo(false)}
      >
        <Pressable style={styles.modalBackdrop} onPress={() => setShowInfo(false)} />

        <View style={[styles.sheet, { backgroundColor: C.surface, borderColor: C.border }]}>
          {/* Handle + header */}
          <View style={[styles.sheetHandle, { backgroundColor: C.border }]} />
          <View style={styles.sheetHeader}>
            <Text style={[styles.sheetTitle, { color: C.textPrimary }]}>
              What is the Spiral Score?
            </Text>
            <Pressable onPress={() => setShowInfo(false)} hitSlop={8}>
              <Ionicons name="close" size={22} color={C.textMuted} />
            </Pressable>
          </View>

          <ScrollView showsVerticalScrollIndicator={false}>
            <Text style={[styles.sheetBody, { color: C.textSecondary }]}>
              The{" "}
              <Text style={{ fontWeight: "700", color: C.textPrimary }}>Spiral Score</Text>
              {" "}is a single number (0–100) that reflects your journal emotion vectors, consistency of entries, and emotional stability.{"\n\n"}
              It is{" "}
              <Text style={{ fontWeight: "600" }}>not a clinical measure</Text>
              {" "}— it&apos;s a mirror. It helps you notice trends in how you&apos;ve been feeling, so you can understand yourself better over time.
            </Text>

            {/* Tier breakdown */}
            <Text style={[styles.tierHeading, { color: C.textPrimary }]}>
              Score Tiers
            </Text>
            {TIERS.map((tier) => {
              const tierColor = getScoreColor(parseInt(tier.range), C);
              return (
                <View
                  key={tier.label}
                  style={[styles.tier, { backgroundColor: tierColor + "18", borderColor: tierColor + "55" }]}
                >
                  <View style={styles.tierTop}>
                    <Text style={[styles.tierLabel, { color: tierColor }]}>
                      {tier.label}
                    </Text>
                    <Text style={[styles.tierRange, { color: C.textMuted }]}>
                      {tier.range}
                    </Text>
                  </View>
                  <Text style={[styles.tierDesc, { color: C.textSecondary }]}>
                    {tier.desc}
                  </Text>
                </View>
              );
            })}

            {/* How it's calculated */}
            <Text style={[styles.tierHeading, { color: C.textPrimary }]}>
              How it&apos;s calculated
            </Text>
            <Text style={[styles.sheetBody, { color: C.textSecondary }]}>
              Your entries are analysed for emotion and intensity using an AI emotion model. Joy/calm signals raise the score, while sadness/anger/anxiety signals lower it. Entry frequency adds confidence, and higher volatility lowers stability. The score uses your available history and updates as new entries are analysed.
            </Text>

            <View style={{ height: SpiralSpacing.xl }} />
          </ScrollView>
        </View>
      </Modal>
    </>
  );
}

function makeStyles(C: SpiralColorSet) {
  return StyleSheet.create({
  wrap: {
    alignItems: "center",
    paddingVertical: SpiralSpacing.lg,
  },
  titleRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    marginBottom: SpiralSpacing.lg,
  },
  cardLabel: {
    color: C.textMuted,
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 1.8,
    textTransform: "uppercase",
  },
  infoBtn: {
    marginTop: 1,
  },
  ringWrap: {
    width: RING,
    height: RING,
    alignItems: "center",
    justifyContent: "center",
  },
  glow: {
    position: "absolute",
    width: RING + 20,
    height: RING + 20,
    borderRadius: (RING + 20) / 2,
    borderWidth: 14,
  },
  ring: {
    width: RING,
    height: RING,
    borderRadius: RING / 2,
    borderWidth: 3,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: C.surface,
  },
  number: {
    fontSize: 52,
    fontWeight: "700",
    lineHeight: 58,
  },
  status: {
    fontSize: 13,
    fontWeight: "500",
    marginTop: 2,
  },

  // Modal
  modalBackdrop: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: "rgba(0,0,0,0.55)",
  },
  sheet: {
    position: "absolute",
    bottom: 0,
    left: 0,
    right: 0,
    borderTopLeftRadius: SpiralRadius.xl,
    borderTopRightRadius: SpiralRadius.xl,
    borderWidth: 1,
    borderBottomWidth: 0,
    maxHeight: "85%",
    paddingHorizontal: SpiralSpacing.lg,
    paddingBottom: SpiralSpacing.xl,
  },
  sheetHandle: {
    width: 40,
    height: 4,
    borderRadius: 2,
    alignSelf: "center",
    marginTop: SpiralSpacing.sm,
    marginBottom: SpiralSpacing.sm,
  },
  sheetHeader: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingVertical: SpiralSpacing.sm,
    marginBottom: SpiralSpacing.sm,
  },
  sheetTitle: {
    fontSize: 18,
    fontWeight: "700",
  },
  sheetBody: {
    fontSize: 14,
    lineHeight: 22,
    marginBottom: SpiralSpacing.md,
  },
  tierHeading: {
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.5,
    marginBottom: SpiralSpacing.sm,
    marginTop: SpiralSpacing.xs ?? 4,
  },
  tier: {
    borderRadius: SpiralRadius.md,
    borderWidth: 1,
    padding: SpiralSpacing.sm,
    marginBottom: SpiralSpacing.sm,
  },
  tierTop: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: 4,
  },
  tierLabel: {
    fontSize: 13,
    fontWeight: "700",
  },
  tierRange: {
    fontSize: 11,
    fontWeight: "600",
  },
  tierDesc: {
    fontSize: 12,
    lineHeight: 18,
  },
  });
}
