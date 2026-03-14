import * as Haptics from "expo-haptics";
import React, { useCallback, useMemo, useRef, useState } from "react";
import {
  Animated,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { AtmosphericBackground } from "@/components/atmospheric-background";
import { ListeningSessionModal } from "@/components/listening-session-modal";
import { useAuth } from "@/context/auth-context";
import { SpiralColorSet, useSpiralTheme } from "@/context/theme-context";
import { SpiralSpacing } from "@/constants/theme";
import { addCheckin, toIsoDate, toDisplayDate } from "@/services/journal-store";

// ─── Mood Data ────────────────────────────────────────────────────────────────
const MOODS = [
  { emoji: "😔", label: "Low", color: "#60A5FA" },
  { emoji: "😟", label: "Uneasy", color: "#A78BFA" },
  { emoji: "😐", label: "Neutral", color: "#8B9CC8" },
  { emoji: "🙂", label: "Good", color: "#F4A261" },
  { emoji: "😄", label: "Great", color: "#5EEAD4" },
] as const;

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function SilentScreen() {
  const { C, isDark, toggleTheme } = useSpiralTheme();
  const { user } = useAuth();
  const styles = useMemo(() => makeStyles(C), [C]);

  const [selected, setSelected] = useState<number | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [sessionOpen, setSessionOpen] = useState(false);

  const scaleAnims = useRef(MOODS.map(() => new Animated.Value(1))).current;
  const ringAnims = useRef(MOODS.map(() => new Animated.Value(0))).current;
  const confirmAnim = useRef(new Animated.Value(0)).current;

  const handleSelect = useCallback(
    (index: number) => {
      if (confirmed) return;

      // Collapse previous ring
      if (selected !== null && selected !== index) {
        Animated.spring(ringAnims[selected], {
          toValue: 0,
          useNativeDriver: true,
        }).start();
      }

      setSelected(index);

      if (Platform.OS !== "web") {
        Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
      }

      // Bounce the emoji
      Animated.sequence([
        Animated.spring(scaleAnims[index], {
          toValue: 1.18,
          useNativeDriver: true,
          tension: 200,
          friction: 5,
        }),
        Animated.spring(scaleAnims[index], {
          toValue: 1,
          useNativeDriver: true,
        }),
      ]).start();

      // Show selection ring
      Animated.spring(ringAnims[index], {
        toValue: 1,
        useNativeDriver: true,
        tension: 150,
        friction: 8,
      }).start();
    },
    [selected, confirmed, scaleAnims, ringAnims],
  );

  const handleSubmit = useCallback(() => {
    if (selected === null || confirmed) return;

    if (Platform.OS !== "web") {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }

    // Persist the check-in to AsyncStorage
    const now = new Date();
    addCheckin({
      id: Date.now().toString(),
      isoDate: toIsoDate(now),
      date: toDisplayDate(now),
      moodIndex: selected,
      moodLabel: MOODS[selected].label,
      type: "checkin",
    }, user?.id).catch(() => {
      // Fire-and-forget; failure is non-blocking in a hackathon context
    });

    setConfirmed(true);
    Animated.sequence([
      Animated.timing(confirmAnim, {
        toValue: 1,
        duration: 280,
        useNativeDriver: true,
      }),
      Animated.delay(1600),
      Animated.timing(confirmAnim, {
        toValue: 0,
        duration: 380,
        useNativeDriver: true,
      }),
    ]).start(() => {
      setConfirmed(false);
      setSelected(null);
      ringAnims.forEach((r) =>
        Animated.timing(r, {
          toValue: 0,
          duration: 180,
          useNativeDriver: true,
        }).start(),
      );
    });
  }, [selected, confirmed, confirmAnim, ringAnims, user?.id]);

  const selectedMood = selected !== null ? MOODS[selected] : null;

  return (
    <SafeAreaView style={styles.safe} edges={["top", "bottom"]}>
      <AtmosphericBackground variant="silent" />
      <View style={styles.container}>
        <View style={styles.topControls}>
          {/* ── Theme toggle ──────────────────────────────────────────────── */}
          <View style={styles.themeToggleRow}>
            <Pressable onPress={toggleTheme} style={styles.themeToggle} hitSlop={8}>
              <Ionicons
                name={isDark ? "sunny-outline" : "moon-outline"}
                size={20}
                color={C.amber}
              />
            </Pressable>
          </View>

          {/* ── Burst entry — top of screen, always visible ───────────────── */}
          <Pressable
            style={({ pressed }) => [
              styles.burstEntry,
              pressed && { opacity: 0.7 },
            ]}
            onPress={() => {
              if (Platform.OS !== "web") {
                Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
              }
              setSessionOpen(true);
            }}
          >
            <Text style={styles.burstEntryEmoji}>💬</Text>
            <Text style={styles.burstEntryText}>Start 10-min private listening session</Text>
          </Pressable>
        </View>

        {/* ── Centered core ─────────────────────────────────────────────── */}
        <View style={styles.core}>

        {/* ── Title ─────────────────────────────────────────────────────── */}
        <View style={styles.header}>
          <Text style={styles.title}>How are you{"\n"}right now?</Text>
          <Text style={styles.subtitle}>No words needed.</Text>
          <Text style={styles.microcopy}>A 5-second check-in still counts as care.</Text>
        </View>

        {/* ── Emoji row ─────────────────────────────────────────────────── */}
        <View style={styles.emojiRow}>
          {MOODS.map((mood, i) => (
            <Pressable
              key={i}
              onPress={() => handleSelect(i)}
              style={styles.emojiWrapper}
            >
              {/* Animated selection ring */}
              <Animated.View
                style={[
                  styles.ring,
                  {
                    borderColor: mood.color,
                    opacity: ringAnims[i],
                    transform: [
                      {
                        scale: ringAnims[i].interpolate({
                          inputRange: [0, 1],
                          outputRange: [0.5, 1],
                        }),
                      },
                    ],
                  },
                ]}
              />
              <Animated.Text
                style={[
                  styles.emoji,
                  { transform: [{ scale: scaleAnims[i] }] },
                ]}
              >
                {mood.emoji}
              </Animated.Text>
            </Pressable>
          ))}
        </View>

        {/* ── Mood label ────────────────────────────────────────────────── */}
        <View style={styles.labelArea}>
          {selectedMood && !confirmed ? (
            <Text style={[styles.moodLabel, { color: selectedMood.color }]}>
              {selectedMood.label}
            </Text>
          ) : (
            <Text style={styles.moodLabelPlaceholder}> </Text>
          )}
        </View>

        {/* ── Submit button ─────────────────────────────────────────────── */}
        {selected !== null && !confirmed && (
          <Pressable
            style={({ pressed }) => [
              styles.submitButton,
              pressed && { opacity: 0.8 },
            ]}
            onPress={handleSubmit}
          >
            <Text style={styles.submitText}>Done</Text>
          </Pressable>
        )}

        {/* ── Confirmation flash ────────────────────────────────────────── */}
        <Animated.View
          pointerEvents="none"
          style={[styles.confirmOverlay, { opacity: confirmAnim }]}
        >
          <Text style={styles.confirmText}>Logged ✓</Text>
        </Animated.View>
        </View>{/* end core */}

      </View>

      {/* ── Session modal ───────────────────────────────────────────────── */}
      <ListeningSessionModal
        visible={sessionOpen}
        onClose={() => setSessionOpen(false)}
      />
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
function makeStyles(C: SpiralColorSet) {
  return StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.midnight },
  container: {
    flex: 1,
    paddingHorizontal: SpiralSpacing.xl,
    paddingBottom: SpiralSpacing.lg,
  },
  topControls: {
    paddingTop: SpiralSpacing.xs,
    marginBottom: SpiralSpacing.md,
  },
  themeToggleRow: {
    width: "100%",
    alignItems: "flex-end",
  },
  // core: flex:1 column, centers the emoji/label/submit vertically
  core: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },

  themeToggle: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: C.amberDim,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: C.amber + "44",
  },

  header: { alignItems: "center", marginBottom: SpiralSpacing.xxl },
  title: {
    fontSize: 36,
    fontWeight: "700",
    color: C.textPrimary,
    textAlign: "center",
    letterSpacing: -1,
    lineHeight: 42,
  },
  subtitle: {
    fontSize: 16,
    color: C.textMuted,
    marginTop: 10,
    letterSpacing: 0.3,
  },
  microcopy: {
    marginTop: 10,
    fontSize: 13,
    lineHeight: 19,
    color: C.textSecondary,
    textAlign: "center",
    maxWidth: 250,
  },

  emojiRow: { flexDirection: "row", gap: 12, alignItems: "center" },
  emojiWrapper: {
    width: 56,
    height: 56,
    alignItems: "center",
    justifyContent: "center",
  },
  ring: {
    position: "absolute",
    width: 66,
    height: 66,
    borderRadius: 33,
    borderWidth: 2,
  },
  emoji: { fontSize: 36 },

  labelArea: {
    height: 32,
    marginTop: SpiralSpacing.lg,
    alignItems: "center",
    justifyContent: "center",
  },
  moodLabel: { fontSize: 18, fontWeight: "600", letterSpacing: 0.5 },
  moodLabelPlaceholder: { fontSize: 18 },

  submitButton: {
    marginTop: SpiralSpacing.xl,
    backgroundColor: C.amber,
    paddingHorizontal: SpiralSpacing.xl,
    paddingVertical: SpiralSpacing.md,
    borderRadius: 100,
  },
  submitText: {
    fontSize: 16,
    fontWeight: "700",
    color: C.midnight,
    letterSpacing: 0.5,
  },

  confirmOverlay: {
    position: "absolute",
    bottom: 80,
    alignSelf: "center",
    backgroundColor: C.tealDim,
    borderWidth: 1,
    borderColor: C.teal + "88",
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 100,
  },
  confirmText: {
    color: C.teal,
    fontSize: 16,
    fontWeight: "700",
    letterSpacing: 0.5,
  },

  burstEntry: {
    alignSelf: "center",
    marginTop: SpiralSpacing.sm,
    marginBottom: 0,
    maxWidth: "96%",
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 20,
    paddingVertical: 11,
    borderRadius: 100,
    borderWidth: 1.5,
    borderColor: "rgba(139,92,246,0.6)",
    backgroundColor: "rgba(139,92,246,0.22)",
  },
  burstEntryEmoji: {
    fontSize: 16,
  },
  burstEntryText: {
    fontSize: 13,
    fontWeight: "600",
    color: C.violet,
    letterSpacing: 0.3,
    textAlign: "center",
    flexShrink: 1,
  },
  });
}
