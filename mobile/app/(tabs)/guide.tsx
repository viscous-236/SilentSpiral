import React, { useMemo } from "react";
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";

import { AtmosphericBackground } from "@/components/atmospheric-background";
import { SpiralRadius, SpiralSpacing } from "@/constants/theme";
import { SpiralColorSet, useSpiralTheme } from "@/context/theme-context";

type GuideStep = {
  title: string;
  userAction: string;
  appAction: string;
  purpose: string;
};

const STEPS: GuideStep[] = [
  {
    title: "Journal entry",
    userAction: "Write freely or use voice input.",
    appAction: "Saves your entry and runs emotion analysis.",
    purpose: "Capture your day with low effort and high honesty.",
  },
  {
    title: "Emotion labels",
    userAction: "Review top emotions and intensity.",
    appAction: "Maps text to emotional signals with NLP.",
    purpose: "Turn vague feelings into clear language.",
  },
  {
    title: "Reflection prompts",
    userAction: "Answer one or two follow-up questions.",
    appAction: "Generates gentle questions from your entry context.",
    purpose: "Help you understand the " +
      "why behind the emotion, not just the label.",
  },
  {
    title: "Insights tab",
    userAction: "Open Insights to view trends.",
    appAction: "Calculates mood timeline, volatility, and patterns.",
    purpose: "Reveal repeating cycles across days and weeks.",
  },
  {
    title: "Coach suggestions",
    userAction: "Try one micro-step for tomorrow.",
    appAction: "Suggests a tiny challenge when a dip is detected.",
    purpose: "Convert awareness into action without pressure.",
  },
  {
    title: "10-minute private listening",
    userAction: "Open Check-in, start session, and share freely for up to 10 minutes.",
    appAction:
      "Runs a private timed listening flow with warm replies, then closes gently when time ends.",
    purpose: "Create a safe, structured space to release emotional pressure in the moment.",
  },
];

const QUICK_NAV = [
  { label: "Go to Journal", route: "./journal" as const, icon: "create-outline" as const },
  {
    label: "Go to Insights",
    route: "./dashboard" as const,
    icon: "analytics-outline" as const,
  },
  {
    label: "Go to Check-in",
    route: "./silent" as const,
    icon: "radio-button-on-outline" as const,
  },
];

export default function GuideScreen() {
  const { C, isDark, toggleTheme } = useSpiralTheme();
  const styles = useMemo(() => makeStyles(C), [C]);
  const router = useRouter();

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <AtmosphericBackground variant="insights" />

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.pageTitle}>How to use Silent Spiral</Text>
            <Text style={styles.pageSubtitle}>
              What to do, what happens, and why it matters
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

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Start here</Text>
          <Text style={styles.cardText}>
            Daily flow: Journal to Reflect to Insights to Coach to Check-in when needed.
          </Text>
          <Text style={styles.cardHint}>
            Aim for one short entry per day. Consistency gives better patterns than long occasional entries.
          </Text>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>How the 10-minute private listening works</Text>
          <Text style={styles.cardText}>
            The Check-in tab includes a private listening session designed for intense moments.
            It is time-boxed to 10 minutes, replies in a warm tone, and ends with a closing message.
          </Text>
          <Text style={styles.cardHint}>
            Best use: when writing feels hard and you need immediate emotional release and grounding.
          </Text>
        </View>

        {STEPS.map((step, index) => (
          <View key={step.title} style={styles.stepCard}>
            <View style={styles.stepHeader}>
              <View style={styles.stepBadge}>
                <Text style={styles.stepBadgeText}>{index + 1}</Text>
              </View>
              <Text style={styles.stepTitle}>{step.title}</Text>
            </View>

            <View style={styles.stepRow}>
              <Text style={styles.stepLabel}>You do</Text>
              <Text style={styles.stepValue}>{step.userAction}</Text>
            </View>
            <View style={styles.stepRow}>
              <Text style={styles.stepLabel}>App does</Text>
              <Text style={styles.stepValue}>{step.appAction}</Text>
            </View>
            <View style={styles.stepRow}>
              <Text style={styles.stepLabel}>Purpose</Text>
              <Text style={styles.stepValue}>{step.purpose}</Text>
            </View>
          </View>
        ))}

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Quick navigation</Text>
          <View style={styles.navGrid}>
            {QUICK_NAV.map((item) => (
              <Pressable
                key={item.label}
                style={({ pressed }) => [
                  styles.navBtn,
                  { opacity: pressed ? 0.85 : 1 },
                ]}
                onPress={() => router.push(item.route)}
              >
                <Ionicons name={item.icon} size={18} color={C.amber} />
                <Text style={styles.navBtnText}>{item.label}</Text>
              </Pressable>
            ))}
          </View>
        </View>

        <View style={styles.card}>
          <Text style={styles.cardTitle}>Important boundary</Text>
          <Text style={styles.cardText}>
            This app supports reflection and emotional awareness. It does not provide medical diagnosis.
          </Text>
          <Text style={styles.cardHint}>
            If someone is in immediate danger, contact emergency or crisis services.
          </Text>
        </View>

        <View style={{ height: 100 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

function makeStyles(C: SpiralColorSet) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: C.midnight },
    scroll: { flex: 1 },
    content: {
      paddingHorizontal: SpiralSpacing.lg,
      paddingTop: SpiralSpacing.md,
    },
    headerRow: {
      flexDirection: "row",
      alignItems: "flex-start",
      justifyContent: "space-between",
      marginBottom: SpiralSpacing.lg,
      gap: SpiralSpacing.md,
    },
    pageTitle: {
      fontSize: 28,
      fontWeight: "700",
      color: C.textPrimary,
      letterSpacing: -0.5,
    },
    pageSubtitle: {
      fontSize: 14,
      color: C.textSecondary,
      marginTop: 4,
      lineHeight: 20,
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
    },

    card: {
      backgroundColor: C.surface,
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.xl,
      padding: SpiralSpacing.lg,
      marginBottom: SpiralSpacing.md,
    },
    cardTitle: {
      fontSize: 16,
      fontWeight: "700",
      color: C.textPrimary,
      marginBottom: 8,
    },
    cardText: {
      fontSize: 14,
      lineHeight: 22,
      color: C.textSecondary,
    },
    cardHint: {
      fontSize: 12,
      lineHeight: 18,
      color: C.textMuted,
      marginTop: 8,
    },

    stepCard: {
      backgroundColor: C.surface,
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.xl,
      padding: SpiralSpacing.lg,
      marginBottom: SpiralSpacing.md,
      gap: 10,
    },
    stepHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: 10,
      marginBottom: 2,
    },
    stepBadge: {
      width: 24,
      height: 24,
      borderRadius: 12,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: C.amberDim,
      borderWidth: 1,
      borderColor: C.amber + "55",
    },
    stepBadgeText: {
      fontSize: 12,
      fontWeight: "700",
      color: C.amber,
    },
    stepTitle: {
      flex: 1,
      fontSize: 15,
      fontWeight: "700",
      color: C.textPrimary,
    },
    stepRow: {
      gap: 2,
    },
    stepLabel: {
      fontSize: 11,
      fontWeight: "700",
      letterSpacing: 0.8,
      textTransform: "uppercase",
      color: C.textMuted,
    },
    stepValue: {
      fontSize: 14,
      lineHeight: 21,
      color: C.textSecondary,
    },

    navGrid: {
      gap: 10,
      marginTop: 2,
    },
    navBtn: {
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surfaceElevated,
      borderRadius: SpiralRadius.md,
      paddingVertical: 12,
      paddingHorizontal: 14,
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
    },
    navBtnText: {
      fontSize: 13,
      fontWeight: "600",
      color: C.textPrimary,
    },
  });
}