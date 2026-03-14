import AsyncStorage from "@react-native-async-storage/async-storage";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { AtmosphericBackground } from "@/components/atmospheric-background";
import { SpiralRadius, SpiralSpacing } from "@/constants/theme";
import { useAuth } from "@/context/auth-context";
import { SpiralColorSet, useSpiralTheme } from "@/context/theme-context";

const QUOTE_CATEGORY_OPTIONS = [
  { value: "all", label: "All" },
  { value: "calm", label: "Calm" },
  { value: "resilience", label: "Resilience" },
  { value: "self-compassion", label: "Self-Compassion" },
] as const;

type QuoteCategory = (typeof QUOTE_CATEGORY_OPTIONS)[number]["value"];

type InspirationQuote = {
  text: string;
  author: string;
  category: Exclude<QuoteCategory, "all">;
};

type MindfulExercise = {
  id: string;
  title: string;
  durationSeconds: number;
  guidance: string;
  steps: string[];
};

type GuideStep = {
  title: string;
  userAction: string;
  appAction: string;
  purpose: string;
};

const QUOTE_PREF_KEY_PREFIX = "spiral_quote_category_v1";

const INSPIRATION_QUOTES: InspirationQuote[] = [
  {
    text: "Feelings are visitors. You do not have to become every emotion that knocks.",
    author: "Quiet Mind Practice",
    category: "self-compassion",
  },
  {
    text: "Small steady care, repeated daily, can change the shape of a hard week.",
    author: "Silent Spiral",
    category: "resilience",
  },
  {
    text: "Breathe where your body is tight. Name what is true. Begin from there.",
    author: "Grounding Notes",
    category: "calm",
  },
  {
    text: "You are not behind. You are arriving at your own pace.",
    author: "Mindful Reminder",
    category: "self-compassion",
  },
  {
    text: "Calm is not the absence of emotion. Calm is your ability to stay with it.",
    author: "Compassion Training",
    category: "calm",
  },
  {
    text: "A hard moment is not a hard identity. Let the moment pass through you.",
    author: "Resilience Notes",
    category: "resilience",
  },
  {
    text: "You can rest and still be moving forward.",
    author: "Quiet Progress",
    category: "self-compassion",
  },
  {
    text: "Exhale slowly. Your nervous system learns safety from repetition.",
    author: "Breathwork Lab",
    category: "calm",
  },
];

const MINDFUL_EXERCISES: MindfulExercise[] = [
  {
    id: "box-breath",
    title: "Box Breath Reset",
    durationSeconds: 120,
    guidance:
      "Use this when your mind feels scattered, rushed, or overstimulated.",
    steps: [
      "Inhale through the nose for 4 counts.",
      "Hold gently for 4 counts.",
      "Exhale slowly for 4 counts.",
      "Pause for 4 counts, then repeat at your pace.",
    ],
  },
  {
    id: "five-senses",
    title: "5-4-3-2-1 Grounding",
    durationSeconds: 180,
    guidance: "Use this when anxiety rises and your thoughts begin to spiral.",
    steps: [
      "Name 5 things you can see around you.",
      "Name 4 things you can feel physically.",
      "Name 3 things you can hear right now.",
      "Name 2 things you can smell.",
      "Name 1 thing you are grateful for in this moment.",
    ],
  },
  {
    id: "body-scan",
    title: "Micro Body Scan",
    durationSeconds: 240,
    guidance: "Use this when emotions feel heavy or stuck in your body.",
    steps: [
      "Sit comfortably and soften your shoulders.",
      "Scan from forehead to jaw, then neck to chest.",
      "Notice where you feel heat, tightness, or heaviness.",
      "Breathe into one tense spot for 3 slow breaths.",
      "End with one hand on chest and one on belly.",
    ],
  },
];

const GUIDE_STEPS: GuideStep[] = [
  {
    title: "Journal entry",
    userAction: "Write freely or use voice input.",
    appAction: "Saves your entry and runs emotion analysis.",
    purpose: "Capture your day with low effort and high honesty.",
  },
  {
    title: "Emotion labels",
    userAction: "Review top emotions and intensity.",
    appAction: "Maps your text into emotional signals.",
    purpose: "Turn vague feelings into clearer language.",
  },
  {
    title: "Reflection prompts",
    userAction: "Answer one or two follow-up prompts.",
    appAction: "Generates gentle questions from your entry context.",
    purpose: "Understand the why behind the feeling.",
  },
  {
    title: "Insights",
    userAction: "Open Insights to view trends.",
    appAction: "Calculates timeline, volatility, and patterns.",
    purpose: "Reveal repeating cycles across days and weeks.",
  },
  {
    title: "Coach suggestions",
    userAction: "Try one tiny step for tomorrow.",
    appAction: "Suggests a lightweight challenge when needed.",
    purpose: "Convert awareness into gentle action.",
  },
];

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function isQuoteCategory(value: string): value is QuoteCategory {
  return QUOTE_CATEGORY_OPTIONS.some((option) => option.value === value);
}

function getDayOfYear() {
  const now = new Date();
  const startOfYear = new Date(now.getFullYear(), 0, 0);
  return Math.floor((now.getTime() - startOfYear.getTime()) / 86_400_000);
}

function getDailyQuote(category: QuoteCategory) {
  const source =
    category === "all"
      ? INSPIRATION_QUOTES
      : INSPIRATION_QUOTES.filter((quote) => quote.category === category);

  const quotePool = source.length > 0 ? source : INSPIRATION_QUOTES;
  return quotePool[getDayOfYear() % quotePool.length];
}

function formatSeconds(totalSeconds: number) {
  const safeSeconds = Math.max(totalSeconds, 0);
  const minutes = Math.floor(safeSeconds / 60)
    .toString()
    .padStart(2, "0");
  const seconds = (safeSeconds % 60).toString().padStart(2, "0");
  return `${minutes}:${seconds}`;
}

function formatDurationLabel(durationSeconds: number) {
  const minutes = Math.round(durationSeconds / 60);
  return `${minutes} min`;
}

export default function LandingScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const { C, isDark, toggleTheme } = useSpiralTheme();
  const styles = useMemo(() => makeStyles(C), [C]);

  const [quoteCategory, setQuoteCategory] = useState<QuoteCategory>("all");
  const [quotePreferenceReady, setQuotePreferenceReady] = useState(false);

  const [selectedExerciseId, setSelectedExerciseId] = useState(
    MINDFUL_EXERCISES[0].id,
  );

  const [timerVisible, setTimerVisible] = useState(false);
  const [isTimerRunning, setIsTimerRunning] = useState(false);
  const [guideVisible, setGuideVisible] = useState(false);
  const [activeExerciseId, setActiveExerciseId] = useState(
    MINDFUL_EXERCISES[0].id,
  );
  const [elapsedSeconds, setElapsedSeconds] = useState(0);

  const quotePreferenceKey = useMemo(
    () => `${QUOTE_PREF_KEY_PREFIX}_${user?.id ?? "guest"}`,
    [user?.id],
  );

  useEffect(() => {
    let isMounted = true;

    const hydratePreference = async () => {
      try {
        const storedCategory = await AsyncStorage.getItem(quotePreferenceKey);
        if (isMounted && storedCategory && isQuoteCategory(storedCategory)) {
          setQuoteCategory(storedCategory);
        }
      } finally {
        if (isMounted) {
          setQuotePreferenceReady(true);
        }
      }
    };

    hydratePreference();

    return () => {
      isMounted = false;
    };
  }, [quotePreferenceKey]);

  useEffect(() => {
    if (!quotePreferenceReady) return;

    AsyncStorage.setItem(quotePreferenceKey, quoteCategory).catch(() => {
      // Best effort persistence; app behavior should not depend on storage availability.
    });
  }, [quoteCategory, quotePreferenceKey, quotePreferenceReady]);

  const quote = useMemo(() => getDailyQuote(quoteCategory), [quoteCategory]);

  const selectedExercise = useMemo(
    () =>
      MINDFUL_EXERCISES.find(
        (exercise) => exercise.id === selectedExerciseId,
      ) ?? MINDFUL_EXERCISES[0],
    [selectedExerciseId],
  );

  const activeExercise = useMemo(
    () =>
      MINDFUL_EXERCISES.find((exercise) => exercise.id === activeExerciseId) ??
      MINDFUL_EXERCISES[0],
    [activeExerciseId],
  );

  const remainingSeconds = Math.max(
    activeExercise.durationSeconds - elapsedSeconds,
    0,
  );

  const progressPercent =
    activeExercise.durationSeconds === 0
      ? 0
      : Math.min((elapsedSeconds / activeExercise.durationSeconds) * 100, 100);

  const currentStepIndex = Math.min(
    Math.floor(
      (elapsedSeconds / Math.max(activeExercise.durationSeconds, 1)) *
        activeExercise.steps.length,
    ),
    Math.max(activeExercise.steps.length - 1, 0),
  );

  const currentStepText =
    activeExercise.steps[currentStepIndex] ??
    "Breathe gently and stay in the present moment.";

  const sessionCompleted = remainingSeconds === 0;

  useEffect(() => {
    if (!timerVisible || !isTimerRunning) return;

    const intervalId = setInterval(() => {
      setElapsedSeconds((prev) => {
        const next = prev + 1;
        if (next >= activeExercise.durationSeconds) {
          setIsTimerRunning(false);
          return activeExercise.durationSeconds;
        }
        return next;
      });
    }, 1000);

    return () => clearInterval(intervalId);
  }, [activeExercise.durationSeconds, isTimerRunning, timerVisible]);

  const handleSelectExercise = useCallback(
    (exerciseId: string) => {
      setSelectedExerciseId(exerciseId);
      if (!timerVisible) {
        setActiveExerciseId(exerciseId);
        setElapsedSeconds(0);
        setIsTimerRunning(false);
      }
    },
    [timerVisible],
  );

  const handleStartExercise = useCallback((exerciseId: string) => {
    setActiveExerciseId(exerciseId);
    setElapsedSeconds(0);
    setTimerVisible(true);
    setIsTimerRunning(true);
  }, []);

  const handleCloseTimer = useCallback(() => {
    setTimerVisible(false);
    setIsTimerRunning(false);
    setElapsedSeconds(0);
  }, []);

  const handleRestartTimer = useCallback(() => {
    setElapsedSeconds(0);
    setIsTimerRunning(true);
  }, []);

  const handleOpenGuide = useCallback(() => {
    setGuideVisible(true);
  }, []);

  const handleCloseGuide = useCallback(() => {
    setGuideVisible(false);
  }, []);

  const toggleTimerRunning = useCallback(() => {
    if (sessionCompleted) return;
    setIsTimerRunning((prev) => !prev);
  }, [sessionCompleted]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <AtmosphericBackground variant="journal" />

      <Modal
        visible={timerVisible}
        animationType="slide"
        transparent
        onRequestClose={handleCloseTimer}
      >
        <View style={styles.timerOverlay}>
          <View style={styles.timerSheet}>
            <View style={styles.timerHeader}>
              <View>
                <Text style={styles.timerTitle}>{activeExercise.title}</Text>
                <Text style={styles.timerSubtitle}>
                  {formatDurationLabel(activeExercise.durationSeconds)} guided
                  practice
                </Text>
              </View>
              <Pressable
                style={({ pressed }) => [
                  styles.timerIconButton,
                  { opacity: pressed ? 0.8 : 1 },
                ]}
                onPress={handleCloseTimer}
              >
                <Ionicons
                  name="close-outline"
                  size={20}
                  color={C.textPrimary}
                />
              </Pressable>
            </View>

            <View style={styles.timerClockWrap}>
              <Text style={styles.timerClock}>
                {formatSeconds(remainingSeconds)}
              </Text>
              <Text style={styles.timerStatus}>
                {sessionCompleted
                  ? "Completed"
                  : isTimerRunning
                    ? "Session in progress"
                    : "Paused"}
              </Text>
            </View>

            <View style={styles.progressTrack}>
              <View
                style={[styles.progressFill, { width: `${progressPercent}%` }]}
              />
            </View>

            <View style={styles.timerStepCard}>
              <Text style={styles.timerStepLabel}>
                Step{" "}
                {Math.min(currentStepIndex + 1, activeExercise.steps.length)} of{" "}
                {activeExercise.steps.length}
              </Text>
              <Text style={styles.timerStepText}>{currentStepText}</Text>
            </View>

            {sessionCompleted && (
              <Text style={styles.timerCompleteText}>
                Beautiful work. Take one slow breath before returning.
              </Text>
            )}

            <View style={styles.timerActionsRow}>
              <Pressable
                style={({ pressed }) => [
                  styles.timerPrimaryAction,
                  { opacity: pressed ? 0.86 : 1 },
                ]}
                onPress={toggleTimerRunning}
                disabled={sessionCompleted}
              >
                <Ionicons
                  name={isTimerRunning ? "pause-outline" : "play-outline"}
                  size={16}
                  color={sessionCompleted ? C.textMuted : "#151515"}
                />
                <Text
                  style={[
                    styles.timerPrimaryActionText,
                    sessionCompleted && { color: C.textMuted },
                  ]}
                >
                  {isTimerRunning ? "Pause" : "Resume"}
                </Text>
              </Pressable>

              <Pressable
                style={({ pressed }) => [
                  styles.timerSecondaryAction,
                  { opacity: pressed ? 0.86 : 1 },
                ]}
                onPress={handleRestartTimer}
              >
                <Ionicons
                  name="refresh-outline"
                  size={16}
                  color={C.textPrimary}
                />
                <Text style={styles.timerSecondaryActionText}>Restart</Text>
              </Pressable>

              <Pressable
                style={({ pressed }) => [
                  styles.timerSecondaryAction,
                  { opacity: pressed ? 0.86 : 1 },
                ]}
                onPress={handleCloseTimer}
              >
                <Ionicons name="exit-outline" size={16} color={C.textPrimary} />
                <Text style={styles.timerSecondaryActionText}>End</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>

      <Modal
        visible={guideVisible}
        animationType="slide"
        transparent
        onRequestClose={handleCloseGuide}
      >
        <View style={styles.guideOverlay}>
          <View style={styles.guideSheet}>
            <View style={styles.guideHeader}>
              <View style={styles.guideTitleWrap}>
                <Text style={styles.guideTitle}>How to use Silent Spiral</Text>
                <Text style={styles.guideSubtitle}>
                  Journal, reflect, track patterns, then take one small next
                  step.
                </Text>
              </View>
              <Pressable
                style={({ pressed }) => [
                  styles.timerIconButton,
                  { opacity: pressed ? 0.8 : 1 },
                ]}
                onPress={handleCloseGuide}
              >
                <Ionicons
                  name="close-outline"
                  size={20}
                  color={C.textPrimary}
                />
              </Pressable>
            </View>

            <ScrollView
              style={styles.guideScroll}
              contentContainerStyle={styles.guideContent}
              showsVerticalScrollIndicator={false}
            >
              {GUIDE_STEPS.map((step, index) => (
                <View key={step.title} style={styles.guideStepCard}>
                  <View style={styles.guideStepHeader}>
                    <View style={styles.stepIndex}>
                      <Text style={styles.stepIndexText}>{index + 1}</Text>
                    </View>
                    <Text style={styles.guideStepTitle}>{step.title}</Text>
                  </View>

                  <Text style={styles.guideStepMeta}>
                    You do: {step.userAction}
                  </Text>
                  <Text style={styles.guideStepMeta}>
                    App does: {step.appAction}
                  </Text>
                  <Text style={styles.guideStepMeta}>
                    Purpose: {step.purpose}
                  </Text>
                </View>
              ))}

              <Pressable
                style={({ pressed }) => [
                  styles.startExerciseButton,
                  { opacity: pressed ? 0.88 : 1 },
                ]}
                onPress={handleCloseGuide}
              >
                <Ionicons name="checkmark-outline" size={18} color="#151515" />
                <Text style={styles.startExerciseButtonText}>Got it</Text>
              </Pressable>
            </ScrollView>
          </View>
        </View>
      </Modal>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.headerRow}>
          <View style={styles.headerCopy}>
            <Text style={styles.kicker}>{getGreeting()}</Text>
            <Text style={styles.title}>A softer start for your mind</Text>
            <Text style={styles.subtitle}>
              Arrive gently with one quote and one short practice, then journal
              when you feel ready.
            </Text>
          </View>
          <Pressable
            onPress={toggleTheme}
            style={styles.themeToggle}
            hitSlop={8}
          >
            <Ionicons
              name={isDark ? "sunny-outline" : "moon-outline"}
              size={20}
              color={C.amber}
            />
          </Pressable>
        </View>

        <View style={styles.primaryCard}>
          <View style={styles.primaryHeader}>
            <Ionicons name="sparkles-outline" size={18} color={C.amber} />
            <Text style={styles.primaryTitle}>Ease in before you write</Text>
          </View>
          <Text style={styles.primaryText}>
            Give yourself one mindful minute first. Your journal will be here
            when you want to go deeper.
          </Text>

          <View style={styles.primaryActions}>
            <Pressable
              style={({ pressed }) => [
                styles.primaryButton,
                { opacity: pressed ? 0.9 : 1 },
              ]}
              onPress={() => router.push("./journal")}
            >
              <Ionicons name="create-outline" size={16} color="#121212" />
              <Text style={styles.primaryButtonText}>Open Journal</Text>
            </Pressable>

            <Pressable
              style={({ pressed }) => [
                styles.secondaryButton,
                { opacity: pressed ? 0.86 : 1 },
              ]}
              onPress={() => router.push("./silent")}
            >
              <Ionicons
                name="radio-button-on-outline"
                size={16}
                color={C.textPrimary}
              />
              <Text style={styles.secondaryButtonText}>10 min Check-in</Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.card}>
          <View style={styles.cardHeading}>
            <Ionicons
              name="chatbox-ellipses-outline"
              size={16}
              color={C.amber}
            />
            <Text style={styles.cardTitle}>Inspiration Quotes</Text>
          </View>

          <View style={styles.quoteCategoryRow}>
            {QUOTE_CATEGORY_OPTIONS.map((option) => {
              const selected = option.value === quoteCategory;

              return (
                <Pressable
                  key={option.value}
                  onPress={() => setQuoteCategory(option.value)}
                  style={({ pressed }) => [
                    styles.quoteCategoryChip,
                    selected && styles.quoteCategoryChipSelected,
                    { opacity: pressed ? 0.86 : 1 },
                  ]}
                >
                  <Text
                    style={[
                      styles.quoteCategoryText,
                      selected && styles.quoteCategoryTextSelected,
                    ]}
                  >
                    {option.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <Text style={styles.quoteText}>{`"${quote.text}"`}</Text>
          <Text style={styles.quoteAuthor}>{quote.author}</Text>
          <Text style={styles.cardHint}>
            Your quote preference is saved on this device.
          </Text>
        </View>

        <View style={styles.card}>
          <View style={styles.cardHeading}>
            <Ionicons name="leaf-outline" size={16} color={C.teal} />
            <Text style={styles.cardTitle}>Mindful exercises</Text>
          </View>
          <Text style={styles.cardHint}>
            Pick one short practice and follow the steps before you start
            writing.
          </Text>

          <View style={styles.exerciseTabs}>
            {MINDFUL_EXERCISES.map((exercise) => {
              const selected = exercise.id === selectedExerciseId;

              return (
                <Pressable
                  key={exercise.id}
                  style={({ pressed }) => [
                    styles.exercisePill,
                    selected && styles.exercisePillSelected,
                    { opacity: pressed ? 0.86 : 1 },
                  ]}
                  onPress={() => handleSelectExercise(exercise.id)}
                >
                  <Text
                    style={[
                      styles.exercisePillText,
                      selected && styles.exercisePillTextSelected,
                    ]}
                  >
                    {exercise.title}
                  </Text>
                  <Text
                    style={[
                      styles.exercisePillTime,
                      selected && styles.exercisePillTimeSelected,
                    ]}
                  >
                    {formatDurationLabel(exercise.durationSeconds)}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          <View style={styles.exerciseDetail}>
            <Text style={styles.exerciseTitle}>{selectedExercise.title}</Text>
            <Text style={styles.exerciseGuidance}>
              {selectedExercise.guidance}
            </Text>
            {selectedExercise.steps.map((step, index) => (
              <View
                key={`${selectedExercise.id}-${index}`}
                style={styles.stepRow}
              >
                <View style={styles.stepIndex}>
                  <Text style={styles.stepIndexText}>{index + 1}</Text>
                </View>
                <Text style={styles.stepText}>{step}</Text>
              </View>
            ))}

            <Pressable
              style={({ pressed }) => [
                styles.startExerciseButton,
                { opacity: pressed ? 0.88 : 1 },
              ]}
              onPress={() => handleStartExercise(selectedExercise.id)}
            >
              <Ionicons name="play-circle-outline" size={18} color="#151515" />
              <Text style={styles.startExerciseButtonText}>
                Start Guided Practice
              </Text>
            </Pressable>
          </View>
        </View>

        <View style={styles.quickNavCard}>
          <Text style={styles.quickNavTitle}>Quick nav</Text>
          <View style={styles.quickNavRow}>
            <Pressable
              style={({ pressed }) => [
                styles.quickNavBtn,
                { opacity: pressed ? 0.84 : 1 },
              ]}
              onPress={() => router.push("./dashboard")}
            >
              <Ionicons name="analytics-outline" size={16} color={C.amber} />
              <Text style={styles.quickNavText}>Insights</Text>
            </Pressable>
            <Pressable
              style={({ pressed }) => [
                styles.quickNavBtn,
                { opacity: pressed ? 0.84 : 1 },
              ]}
              onPress={handleOpenGuide}
            >
              <Ionicons name="help-circle-outline" size={16} color={C.amber} />
              <Text style={styles.quickNavText}>Guide</Text>
            </Pressable>
          </View>
        </View>

        <View style={{ height: 108 }} />
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
      gap: SpiralSpacing.md,
    },

    timerOverlay: {
      flex: 1,
      justifyContent: "flex-end",
      backgroundColor: C.overlay,
    },
    timerSheet: {
      backgroundColor: C.surface,
      borderTopLeftRadius: SpiralRadius.xl,
      borderTopRightRadius: SpiralRadius.xl,
      borderWidth: 1,
      borderBottomWidth: 0,
      borderColor: C.border,
      padding: SpiralSpacing.lg,
      paddingBottom: SpiralSpacing.xl,
      gap: 12,
    },
    timerHeader: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      gap: SpiralSpacing.md,
    },
    timerTitle: {
      fontSize: 18,
      fontWeight: "700",
      color: C.textPrimary,
    },
    timerSubtitle: {
      marginTop: 4,
      fontSize: 13,
      lineHeight: 18,
      color: C.textSecondary,
    },
    timerIconButton: {
      width: 36,
      height: 36,
      borderRadius: SpiralRadius.pill,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surfaceElevated,
      alignItems: "center",
      justifyContent: "center",
    },
    timerClockWrap: {
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.lg,
      backgroundColor: C.surfaceElevated,
      alignItems: "center",
      paddingVertical: 14,
      gap: 2,
    },
    timerClock: {
      fontSize: 38,
      fontWeight: "700",
      color: C.textPrimary,
      letterSpacing: 1.2,
    },
    timerStatus: {
      fontSize: 12,
      color: C.textSecondary,
      fontWeight: "600",
      textTransform: "uppercase",
      letterSpacing: 0.8,
    },
    progressTrack: {
      width: "100%",
      height: 8,
      borderRadius: 999,
      overflow: "hidden",
      backgroundColor: C.amberDim,
      borderWidth: 1,
      borderColor: C.border,
    },
    progressFill: {
      height: "100%",
      borderRadius: 999,
      backgroundColor: C.amber,
    },
    timerStepCard: {
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.lg,
      backgroundColor: C.surfaceElevated,
      padding: SpiralSpacing.md,
      gap: 6,
    },
    timerStepLabel: {
      fontSize: 11,
      textTransform: "uppercase",
      letterSpacing: 0.8,
      fontWeight: "700",
      color: C.textMuted,
    },
    timerStepText: {
      fontSize: 15,
      lineHeight: 22,
      color: C.textPrimary,
      fontWeight: "600",
    },
    timerCompleteText: {
      fontSize: 13,
      lineHeight: 20,
      color: C.teal,
      fontWeight: "600",
      textAlign: "center",
    },
    timerActionsRow: {
      flexDirection: "row",
      flexWrap: "wrap",
      gap: 10,
      marginTop: 2,
    },
    timerPrimaryAction: {
      minHeight: 44,
      borderRadius: SpiralRadius.md,
      paddingHorizontal: 14,
      backgroundColor: C.amber,
      flexDirection: "row",
      alignItems: "center",
      gap: 6,
    },
    timerPrimaryActionText: {
      color: "#151515",
      fontSize: 13,
      fontWeight: "700",
    },
    timerSecondaryAction: {
      minHeight: 44,
      borderRadius: SpiralRadius.md,
      paddingHorizontal: 12,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surfaceElevated,
      flexDirection: "row",
      alignItems: "center",
      gap: 6,
    },
    timerSecondaryActionText: {
      fontSize: 13,
      color: C.textPrimary,
      fontWeight: "600",
    },
    guideOverlay: {
      flex: 1,
      justifyContent: "flex-end",
      backgroundColor: C.overlay,
    },
    guideSheet: {
      maxHeight: "84%",
      backgroundColor: C.surface,
      borderTopLeftRadius: SpiralRadius.xl,
      borderTopRightRadius: SpiralRadius.xl,
      borderWidth: 1,
      borderBottomWidth: 0,
      borderColor: C.border,
      padding: SpiralSpacing.lg,
      paddingBottom: SpiralSpacing.xl,
      gap: 12,
    },
    guideHeader: {
      flexDirection: "row",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: SpiralSpacing.md,
    },
    guideTitleWrap: {
      flex: 1,
      gap: 6,
    },
    guideTitle: {
      fontSize: 20,
      fontWeight: "700",
      color: C.textPrimary,
    },
    guideSubtitle: {
      fontSize: 13,
      lineHeight: 19,
      color: C.textSecondary,
    },
    guideScroll: {
      flexGrow: 0,
    },
    guideContent: {
      gap: 10,
      paddingBottom: 4,
    },
    guideStepCard: {
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.lg,
      backgroundColor: C.surfaceElevated,
      padding: SpiralSpacing.md,
      gap: 8,
    },
    guideStepHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: 10,
    },
    guideStepTitle: {
      flex: 1,
      fontSize: 14,
      fontWeight: "700",
      color: C.textPrimary,
    },
    guideStepMeta: {
      fontSize: 13,
      lineHeight: 20,
      color: C.textSecondary,
    },

    headerRow: {
      flexDirection: "row",
      alignItems: "flex-start",
      justifyContent: "space-between",
      gap: SpiralSpacing.md,
    },
    headerCopy: { flex: 1 },
    kicker: {
      fontSize: 13,
      letterSpacing: 0.8,
      color: C.textMuted,
      textTransform: "uppercase",
      marginBottom: 6,
      fontWeight: "700",
    },
    title: {
      fontSize: 30,
      lineHeight: 36,
      fontWeight: "700",
      color: C.textPrimary,
      letterSpacing: -0.6,
    },
    subtitle: {
      marginTop: 10,
      fontSize: 14,
      lineHeight: 22,
      color: C.textSecondary,
      maxWidth: 560,
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
    primaryCard: {
      backgroundColor: C.surface,
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.xl,
      padding: SpiralSpacing.lg,
      gap: 12,
    },
    primaryHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
    },
    primaryTitle: {
      fontSize: 16,
      fontWeight: "700",
      color: C.textPrimary,
    },
    primaryText: {
      fontSize: 14,
      lineHeight: 22,
      color: C.textSecondary,
    },
    primaryActions: {
      flexDirection: "row",
      flexWrap: "wrap",
      gap: 10,
      marginTop: 2,
    },
    primaryButton: {
      minHeight: 44,
      borderRadius: SpiralRadius.md,
      paddingHorizontal: 14,
      backgroundColor: C.amber,
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
    },
    primaryButtonText: {
      fontSize: 13,
      fontWeight: "700",
      color: "#151515",
      letterSpacing: 0.2,
    },
    secondaryButton: {
      minHeight: 44,
      borderRadius: SpiralRadius.md,
      paddingHorizontal: 14,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surfaceElevated,
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
    },
    secondaryButtonText: {
      fontSize: 13,
      fontWeight: "600",
      color: C.textPrimary,
    },
    card: {
      backgroundColor: C.surface,
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.xl,
      padding: SpiralSpacing.lg,
      gap: 10,
    },
    cardHeading: {
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
    },
    cardTitle: {
      fontSize: 16,
      fontWeight: "700",
      color: C.textPrimary,
    },
    cardHint: {
      fontSize: 12,
      lineHeight: 18,
      color: C.textMuted,
    },
    quoteCategoryRow: {
      flexDirection: "row",
      gap: 8,
      flexWrap: "wrap",
      marginTop: 2,
    },
    quoteCategoryChip: {
      minHeight: 36,
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.pill,
      paddingHorizontal: 12,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: C.surfaceElevated,
    },
    quoteCategoryChipSelected: {
      borderColor: C.amber + "88",
      backgroundColor: C.amberDim,
    },
    quoteCategoryText: {
      fontSize: 12,
      fontWeight: "700",
      color: C.textSecondary,
    },
    quoteCategoryTextSelected: {
      color: C.amber,
    },
    quoteText: {
      fontSize: 17,
      lineHeight: 27,
      color: C.textPrimary,
      fontWeight: "600",
    },
    quoteAuthor: {
      fontSize: 13,
      color: C.textSecondary,
      fontWeight: "600",
    },
    exerciseTabs: {
      gap: 8,
      marginTop: 2,
    },
    exercisePill: {
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surfaceElevated,
      borderRadius: SpiralRadius.md,
      paddingHorizontal: 12,
      paddingVertical: 10,
      minHeight: 44,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 10,
    },
    exercisePillSelected: {
      borderColor: C.teal + "88",
      backgroundColor: C.tealDim,
    },
    exercisePillText: {
      flex: 1,
      fontSize: 13,
      fontWeight: "600",
      color: C.textPrimary,
    },
    exercisePillTextSelected: {
      color: C.teal,
    },
    exercisePillTime: {
      fontSize: 12,
      color: C.textMuted,
      fontWeight: "700",
    },
    exercisePillTimeSelected: {
      color: C.teal,
    },
    exerciseDetail: {
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surfaceElevated,
      borderRadius: SpiralRadius.lg,
      padding: SpiralSpacing.md,
      gap: 8,
      marginTop: 6,
    },
    exerciseTitle: {
      fontSize: 14,
      fontWeight: "700",
      color: C.textPrimary,
    },
    exerciseGuidance: {
      fontSize: 13,
      lineHeight: 20,
      color: C.textSecondary,
      marginBottom: 2,
    },
    stepRow: {
      flexDirection: "row",
      alignItems: "flex-start",
      gap: 10,
    },
    stepIndex: {
      width: 20,
      height: 20,
      borderRadius: SpiralRadius.pill,
      alignItems: "center",
      justifyContent: "center",
      borderWidth: 1,
      borderColor: C.amber + "66",
      backgroundColor: C.amberDim,
      marginTop: 1,
    },
    stepIndexText: {
      fontSize: 11,
      fontWeight: "700",
      color: C.amber,
    },
    stepText: {
      flex: 1,
      fontSize: 13,
      lineHeight: 20,
      color: C.textSecondary,
    },
    startExerciseButton: {
      minHeight: 44,
      marginTop: 8,
      borderRadius: SpiralRadius.md,
      backgroundColor: C.amber,
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: 8,
      paddingHorizontal: 14,
    },
    startExerciseButtonText: {
      fontSize: 13,
      fontWeight: "700",
      color: "#151515",
    },
    quickNavCard: {
      backgroundColor: C.surface,
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.xl,
      padding: SpiralSpacing.lg,
      gap: 12,
    },
    quickNavTitle: {
      fontSize: 15,
      fontWeight: "700",
      color: C.textPrimary,
    },
    quickNavRow: {
      flexDirection: "row",
      gap: 10,
      flexWrap: "wrap",
    },
    quickNavBtn: {
      minHeight: 44,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surfaceElevated,
      borderRadius: SpiralRadius.md,
      paddingHorizontal: 12,
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
    },
    quickNavText: {
      fontSize: 13,
      color: C.textPrimary,
      fontWeight: "600",
    },
  });
}
