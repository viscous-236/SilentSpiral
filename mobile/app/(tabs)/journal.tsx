import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { Audio } from "expo-av";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import Animated, { FadeInDown } from "react-native-reanimated";
import { useFocusEffect } from "expo-router";

import { AtmosphericBackground } from "@/components/atmospheric-background";
import { EmotionTag } from "@/components/emotion-tag";
import { SpiralColorSet, useSpiralTheme } from "@/context/theme-context";
import { SpiralRadius, SpiralSpacing } from "@/constants/theme";
import { useAnalyze } from "@/hooks/use-analyze";
import { useReflection } from "@/hooks/use-reflection";
import { useJournal } from "@/hooks/use-journal";
import { useAuth } from "@/context/auth-context";
import { emotionArrayToDict } from "@/services/emotion-service";
import {
  transcribeAudioUri,
  type VoiceLocale,
} from "@/services/transcription-service";
import { toIsoDate, toDisplayDate } from "@/services/journal-store";
import { getActiveApiBaseUrl } from "@/services/api";

// ─── Daily Prompts (cycled by day-of-year) ────────────────────────────────────
const DAILY_PROMPTS = [
  "What emotion has visited you most today — and what might it be trying to tell you?",
  "Describe one moment from today in vivid detail. What feeling lived inside it?",
  "If today had a weather forecast, what would it be? What brought that weather?",
  "What are you carrying right now that you haven't named yet?",
  "What small thing happened today that you almost didn't notice?",
  "Where in your body do you feel today's mood? Describe the sensation.",
  "If you could send a message to your morning self, what would you say?",
];

const VOCAB_EXPANDER: Record<
  "joy" | "calm" | "sadness" | "anxiety" | "anger" | "neutral",
  string[]
> = {
  joy: ["light", "energized", "content", "hopeful", "grateful"],
  calm: ["steady", "grounded", "centered", "unhurried", "soft"],
  sadness: ["heavy", "tender", "deflated", "isolated", "raw"],
  anxiety: ["uneasy", "restless", "overloaded", "on-edge", "uncertain"],
  anger: ["frustrated", "irritated", "resentful", "charged", "defensive"],
  neutral: ["flat", "mixed", "muted", "unclear", "in-between"],
};

const EMOTION_ALIAS: Record<
  string,
  "joy" | "calm" | "sadness" | "anxiety" | "anger" | "neutral"
> = {
  admiration: "joy",
  amusement: "joy",
  approval: "joy",
  caring: "joy",
  desire: "joy",
  excitement: "joy",
  gratitude: "joy",
  love: "joy",
  optimism: "joy",
  pride: "joy",
  relief: "joy",
  calm: "calm",
  curiosity: "calm",
  realization: "calm",
  surprise: "calm",
  sadness: "sadness",
  grief: "sadness",
  disappointment: "sadness",
  remorse: "sadness",
  fear: "anxiety",
  nervousness: "anxiety",
  confusion: "anxiety",
  anxiety: "anxiety",
  anger: "anger",
  annoyance: "anger",
  disapproval: "anger",
  disgust: "anger",
  embarrassment: "anger",
  neutral: "neutral",
};

function canonicalEmotion(label: string): keyof typeof VOCAB_EXPANDER {
  return EMOTION_ALIAS[label] ?? "neutral";
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

function getDailyPrompt(dateKey: string) {
  const [year, month, day] = dateKey.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  const start = new Date(year, 0, 0).getTime();
  const dayOfYear = Math.floor((date.getTime() - start) / 86_400_000);
  return DAILY_PROMPTS[dayOfYear % DAILY_PROMPTS.length];
}

function getLocalDateKey(d: Date = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

type SpeechModule = {
  start: (options: {
    lang?: string;
    interimResults?: boolean;
    addsPunctuation?: boolean;
    continuous?: boolean;
  }) => void;
  stop: () => void;
  requestPermissionsAsync: () => Promise<{ granted: boolean }>;
  isRecognitionAvailable: () => boolean;
  addListener: (
    eventName: "start" | "end" | "result" | "error",
    listener: (event: any) => void,
  ) => { remove: () => void };
};

const speechModule: SpeechModule | null = (() => {
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require("expo-speech-recognition")
      .ExpoSpeechRecognitionModule as SpeechModule;
  } catch {
    return null;
  }
})();

const VOICE_LOCALES: { code: VoiceLocale; label: string }[] = [
  { code: "en-US", label: "EN" },
  { code: "hi-IN", label: "HI" },
];

// ─── Screen ───────────────────────────────────────────────────────────────────
export default function JournalScreen() {
  const { C, isDark, toggleTheme } = useSpiralTheme();
  const { user } = useAuth();
  const styles = useMemo(() => makeStyles(C), [C]);

  const [text, setText] = useState("");
  const {
    entries,
    addEntry,
    updateEntry,
    loading: entriesLoading,
  } = useJournal();
  const inputRef = useRef<TextInput>(null);

  // ── API hooks ────────────────────────────────────────────────────────────
  const { analyze, loading: analyzing } = useAnalyze();
  const {
    fetchReflection,
    questions,
    loading: reflecting,
    reset: resetReflection,
  } = useReflection();

  // ── Reflection modal state ───────────────────────────────────────────────
  const [modalVisible, setModalVisible] = useState(false);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [speechError, setSpeechError] = useState<string | null>(null);
  const [isListening, setIsListening] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [voiceLocale, setVoiceLocale] = useState<VoiceLocale>("en-US");
  const [vocabEmotion, setVocabEmotion] =
    useState<keyof typeof VOCAB_EXPANDER>("neutral");
  const [vocabSuggestions, setVocabSuggestions] = useState<string[]>([]);
  const [promptDateKey, setPromptDateKey] = useState(() => getLocalDateKey());
  const speechBaseTextRef = useRef("");
  const recordingRef = useRef<Audio.Recording | null>(null);
  const stopFallbackRef = useRef<() => Promise<void>>(async () => { });
  const silenceSinceRef = useRef<number | null>(null);
  const autoStoppingRef = useRef(false);
  const speechDetectedRef = useRef(false);
  const recordingStartedAtRef = useRef<number>(0);

  useEffect(() => {
    const startSub = speechModule?.addListener("start", () => {
      setIsListening(true);
      setSpeechError(null);
    });

    const endSub = speechModule?.addListener("end", () => {
      setIsListening(false);
      speechBaseTextRef.current = "";
    });

    const resultSub = speechModule?.addListener("result", (event: any) => {
      const transcript = event?.results?.[0]?.transcript?.trim() ?? "";
      if (!transcript) return;

      const base = speechBaseTextRef.current.trimEnd();
      const separator = base.length > 0 ? " " : "";
      setText(`${base}${separator}${transcript}`);
    });

    const errorSub = speechModule?.addListener("error", (event: any) => {
      setIsListening(false);
      speechBaseTextRef.current = "";
      setSpeechError(event?.message || "Speech recognition failed.");
    });

    return () => {
      startSub?.remove();
      endSub?.remove();
      resultSub?.remove();
      errorSub?.remove();

      if (recordingRef.current) {
        recordingRef.current.stopAndUnloadAsync().catch(() => {
          // noop cleanup
        });
        recordingRef.current = null;
        Audio.setAudioModeAsync({ allowsRecordingIOS: false }).catch(() => {
          // best effort reset
        });
      }
    };
  }, []);

  const stopFallbackRecording = useCallback(async () => {
    const recording = recordingRef.current;
    if (!recording) return;

    setIsListening(false);
    setIsTranscribing(true);

    try {
      await recording.stopAndUnloadAsync();
      recordingRef.current = null;
      silenceSinceRef.current = null;
      autoStoppingRef.current = false;

      const elapsedMs = Date.now() - recordingStartedAtRef.current;
      if (!speechDetectedRef.current && elapsedMs < 1500) {
        setSpeechError(
          "No speech detected. Please try again and speak clearly.",
        );
        return;
      }

      const uri = recording.getURI();
      if (!uri) {
        setSpeechError("No audio captured. Please try again.");
        return;
      }

      const result = await transcribeAudioUri(uri, voiceLocale);
      const transcript = result.text.trim();
      if (!transcript) {
        setSpeechError("No clear speech detected. Try speaking a bit louder.");
        return;
      }

      const base = speechBaseTextRef.current.trimEnd();
      const separator = base.length > 0 ? " " : "";
      setText(`${base}${separator}${transcript}`);
      speechBaseTextRef.current = "";
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Transcription failed.";
      if (
        message.toLowerCase().includes("network") ||
        message.toLowerCase().includes("timeout")
      ) {
        setSpeechError(
          `${message}. Ensure backend is running and phone + laptop are on the same Wi-Fi.`,
        );
      } else {
        setSpeechError(message);
      }
    } finally {
      setIsTranscribing(false);
      await Audio.setAudioModeAsync({ allowsRecordingIOS: false }).catch(() => {
        // best effort reset
      });
    }
  }, [voiceLocale]);

  useEffect(() => {
    stopFallbackRef.current = stopFallbackRecording;
  }, [stopFallbackRecording]);

  // Refresh prompt when returning to this tab after date rollover.
  useFocusEffect(
    useCallback(() => {
      const nowKey = getLocalDateKey();
      setPromptDateKey((prev) => (prev === nowKey ? prev : nowKey));
    }, []),
  );

  // Also refresh while the app stays open across midnight.
  useEffect(() => {
    const now = new Date();
    const nextMidnight = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate() + 1,
      0,
      0,
      1,
    );
    const msUntilMidnight = nextMidnight.getTime() - now.getTime();
    const timer = setTimeout(
      () => setPromptDateKey(getLocalDateKey()),
      msUntilMidnight,
    );
    return () => clearTimeout(timer);
  }, [promptDateKey]);

  const wordCount = useMemo(
    () => text.trim().split(/\s+/).filter(Boolean).length,
    [text],
  );

  const prompt = useMemo(() => getDailyPrompt(promptDateKey), [promptDateKey]);

  const isBusy = analyzing || reflecting;

  const startFallbackRecording = useCallback(async () => {
    setSpeechError(null);

    const permission = await Audio.requestPermissionsAsync();
    if (!permission.granted) {
      setSpeechError("Microphone permission is required for voice input.");
      return;
    }

    try {
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
      });

      const recording = new Audio.Recording();
      await recording.prepareToRecordAsync({
        ...Audio.RecordingOptionsPresets.HIGH_QUALITY,
        isMeteringEnabled: true,
      });
      recording.setProgressUpdateInterval(250);
      recording.setOnRecordingStatusUpdate((status) => {
        if (!status.isRecording || autoStoppingRef.current) return;

        const meter =
          typeof status.metering === "number" ? status.metering : -160;
        if (meter > -45) {
          speechDetectedRef.current = true;
        }

        const isSilent = meter < -50;
        const nowMs = Date.now();

        if (!isSilent) {
          silenceSinceRef.current = null;
          return;
        }

        if (silenceSinceRef.current === null) {
          silenceSinceRef.current = nowMs;
          return;
        }

        const silentForMs = nowMs - silenceSinceRef.current;
        if (speechDetectedRef.current && silentForMs >= 1400) {
          autoStoppingRef.current = true;
          stopFallbackRef.current().catch(() => {
            autoStoppingRef.current = false;
          });
        }
      });
      await recording.startAsync();

      recordingRef.current = recording;
      speechBaseTextRef.current = text.trimEnd();
      silenceSinceRef.current = null;
      autoStoppingRef.current = false;
      speechDetectedRef.current = false;
      recordingStartedAtRef.current = Date.now();
      setIsListening(true);
    } catch {
      setSpeechError("Unable to start recording. Please try again.");
    }
  }, [text]);

  const handleVoiceToggle = useCallback(async () => {
    setSpeechError(null);

    if (isBusy || isTranscribing) return;

    if (!speechModule) {
      if (isListening) {
        await stopFallbackRecording();
      } else {
        await startFallbackRecording();
      }
      return;
    }

    if (isListening) {
      speechModule.stop();
      return;
    }

    try {
      const permission = await speechModule.requestPermissionsAsync();
      if (!permission.granted) {
        setSpeechError("Microphone permission is required for voice input.");
        return;
      }

      if (!speechModule.isRecognitionAvailable()) {
        setSpeechError("Speech recognition is unavailable on this device.");
        return;
      }

      speechBaseTextRef.current = text.trimEnd();
      speechModule.start({
        lang: voiceLocale,
        interimResults: true,
        addsPunctuation: true,
        continuous: false,
      });
    } catch {
      // Some environments may resolve the JS package but fail at native runtime.
      // Fallback to Expo Go-compatible recording/transcribe flow.
      if (isListening) {
        await stopFallbackRecording();
      } else {
        await startFallbackRecording();
      }
    }
  }, [
    isBusy,
    isListening,
    isTranscribing,
    startFallbackRecording,
    stopFallbackRecording,
    text,
    voiceLocale,
  ]);

  const handleSubmit = useCallback(async () => {
    if (!text.trim() || isBusy || isListening || isTranscribing || !user?.id)
      return;
    setAnalysisError(null);

    // Save entry immediately with optimistic emotions
    const savedText = text.trim();
    const now = new Date();
    const entryId = Date.now().toString();
    await addEntry({
      id: entryId,
      isoDate: toIsoDate(now),
      date: toDisplayDate(now),
      preview: savedText.slice(0, 160) + (savedText.length > 160 ? "…" : ""),
      emotions: ["neutral"],
      intensity: 0.5,
      emotionScores: {},
      type: "entry",
    });
    setText("");
    inputRef.current?.blur();

    // ── Step 1: Analyze emotions ─────────────────────────────────────────
    const { result, errorMessage } = await analyze(savedText);
    if (result) {
      // Update entry with real emotions from API
      const emotionScores = emotionArrayToDict(result.emotions);
      const canonical = canonicalEmotion(result.top_emotion);
      await updateEntry(entryId, {
        emotions: [result.top_emotion],
        intensity: result.intensity,
        emotionScores,
      });
      setVocabEmotion(canonical);
      setVocabSuggestions(VOCAB_EXPANDER[canonical]);

      // ── Step 2: Fetch reflection questions ────────────────────────────
      await fetchReflection({
        journal_text: savedText,
        emotions: result.emotions,
      });
      setModalVisible(true);
    } else {
      // Entry is already saved locally. Surface precise backend/network issue.
      const fallbackMessage = `Couldn't reach the server at ${getActiveApiBaseUrl()}. Entry saved locally.`;
      setAnalysisError(errorMessage ? `${errorMessage}. Entry saved locally.` : fallbackMessage);
    }
  }, [
    text,
    isBusy,
    isListening,
    isTranscribing,
    analyze,
    fetchReflection,
    addEntry,
    updateEntry,
    user?.id,
  ]);

  const handleCloseModal = useCallback(() => {
    setModalVisible(false);
    resetReflection();
  }, [resetReflection]);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <AtmosphericBackground variant="journal" />

      {/* ── Reflection Modal ─────────────────────────────────────────────── */}
      <Modal
        visible={modalVisible}
        animationType="slide"
        transparent
        onRequestClose={handleCloseModal}
      >
        <View style={styles.modalOverlay}>
          <View
            style={[
              styles.modalSheet,
              { backgroundColor: C.surface, borderColor: C.border },
            ]}
          >
            {/* Handle */}
            <View style={[styles.modalHandle, { backgroundColor: C.border }]} />

            <Animated.View entering={FadeInDown.springify()}>
              <View style={styles.modalHeader}>
                <View
                  style={[
                    styles.modalIconWrap,
                    { backgroundColor: C.amberDim },
                  ]}
                >
                  <Ionicons name="sparkles" size={20} color={C.amber} />
                </View>
                <Text style={[styles.modalTitle, { color: C.textPrimary }]}>
                  Reflect on this entry
                </Text>
              </View>
              <Text style={[styles.modalSubtitle, { color: C.textSecondary }]}>
                Your reflection companion noticed emotional threads. Sit with
                these questions.
              </Text>
            </Animated.View>

            {reflecting ? (
              <View style={styles.modalLoading}>
                <ActivityIndicator color={C.amber} />
                <Text style={[styles.modalLoadingText, { color: C.textMuted }]}>
                  Generating questions…
                </Text>
              </View>
            ) : (
              <ScrollView showsVerticalScrollIndicator={false}>
                {questions.map((q, i) => (
                  <Animated.View
                    key={i}
                    entering={FadeInDown.delay(i * 100).springify()}
                    style={[styles.questionRow, { borderColor: C.border }]}
                  >
                    <View
                      style={[
                        styles.questionNum,
                        { backgroundColor: C.amberDim },
                      ]}
                    >
                      <Text
                        style={[styles.questionNumText, { color: C.amber }]}
                      >
                        {i + 1}
                      </Text>
                    </View>
                    <Text
                      style={[styles.questionText, { color: C.textPrimary }]}
                    >
                      {q}
                    </Text>
                  </Animated.View>
                ))}
              </ScrollView>
            )}

            <Pressable
              onPress={handleCloseModal}
              style={({ pressed }) => [
                styles.modalClose,
                { backgroundColor: C.amber, opacity: pressed ? 0.8 : 1 },
              ]}
            >
              <Text style={[styles.modalCloseText, { color: C.midnight }]}>
                Done
              </Text>
            </Pressable>
          </View>
        </View>
      </Modal>

      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* ── Header ─────────────────────────────────────────────────── */}
          <View style={styles.header}>
            <View style={styles.headerRow}>
              <View>
                <Text style={styles.greeting}>{getGreeting()}</Text>
                <Text style={styles.dateText}>
                  {new Date().toLocaleDateString("en-US", {
                    weekday: "long",
                    month: "long",
                    day: "numeric",
                  })}
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
          </View>

          {/* ── Daily Prompt ────────────────────────────────────────────── */}
          <View style={styles.promptCard}>
            <View style={styles.promptAccentBar} />
            <View style={styles.promptContent}>
              <Text style={styles.promptLabel}>Today&apos;s Prompt</Text>
              <Text style={styles.promptText}>{prompt}</Text>
            </View>
          </View>

          {/* ── Editor ─────────────────────────────────────────────────── */}
          <View style={styles.editorContainer}>
            <TextInput
              ref={inputRef}
              style={styles.editor}
              value={text}
              onChangeText={setText}
              multiline
              placeholder="Begin writing… this is your private space."
              placeholderTextColor={C.textMuted}
              textAlignVertical="top"
              scrollEnabled={false}
            />
            <View style={styles.editorFooter}>
              <View style={styles.editorFooterLeft}>
                <Pressable
                  onPress={handleVoiceToggle}
                  disabled={isBusy || isTranscribing}
                  style={({ pressed }) => [
                    styles.micButton,
                    {
                      backgroundColor: isListening
                        ? C.tealDim
                        : C.surfaceElevated,
                      borderColor: isListening ? C.teal : C.border,
                      opacity: pressed || isBusy || isTranscribing ? 0.75 : 1,
                    },
                  ]}
                  accessibilityRole="button"
                  accessibilityLabel={
                    isListening ? "Stop voice input" : "Start voice input"
                  }
                >
                  {isTranscribing ? (
                    <ActivityIndicator size={14} color={C.teal} />
                  ) : (
                    <Ionicons
                      name={isListening ? "stop-circle-outline" : "mic-outline"}
                      size={16}
                      color={isListening ? C.teal : C.textSecondary}
                    />
                  )}
                </Pressable>
                <Text style={styles.wordCount}>{wordCount} words</Text>
              </View>
              <Pressable
                style={({ pressed }) => [
                  styles.submitButton,
                  (pressed || isBusy) && styles.submitButtonPressed,
                  (!text.trim() || isBusy || isListening || isTranscribing) &&
                  styles.submitButtonDisabled,
                ]}
                onPress={handleSubmit}
                disabled={
                  !text.trim() || isBusy || isListening || isTranscribing
                }
              >
                {isBusy ? (
                  <ActivityIndicator size={14} color={C.midnight} />
                ) : (
                  <Text style={styles.submitButtonText}>Save Entry</Text>
                )}
              </Pressable>
            </View>
            <View style={styles.voiceLocaleRow}>
              <Text style={[styles.voiceLabel, { color: C.textMuted }]}>
                Voice
              </Text>
              {VOICE_LOCALES.map((item) => {
                const active = item.code === voiceLocale;
                return (
                  <Pressable
                    key={item.code}
                    onPress={() => setVoiceLocale(item.code)}
                    style={({ pressed }) => [
                      styles.voiceLocaleChip,
                      {
                        borderColor: active ? C.amber : C.border,
                        backgroundColor: active ? C.amberDim : C.surface,
                        opacity: pressed ? 0.8 : 1,
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.voiceLocaleChipText,
                        { color: active ? C.amber : C.textSecondary },
                      ]}
                    >
                      {item.label}
                    </Text>
                  </Pressable>
                );
              })}
              {isTranscribing && (
                <Text style={[styles.voiceLabel, { color: C.teal }]}>
                  Transcribing…
                </Text>
              )}
            </View>
          </View>

          {!!speechError && (
            <View
              style={[
                styles.errorBanner,
                { backgroundColor: C.surface, borderColor: "#F87171" + "55" },
              ]}
            >
              <Ionicons name="mic-off-outline" size={14} color="#F87171" />
              <Text style={styles.errorBannerText}>{speechError}</Text>
            </View>
          )}

          {/* ── API error banner ────────────────────────────────────────── */}
          {!!analysisError && (
            <View
              style={[
                styles.errorBanner,
                { backgroundColor: C.surface, borderColor: "#F87171" + "55" },
              ]}
            >
              <Ionicons
                name="cloud-offline-outline"
                size={14}
                color="#F87171"
              />
              <Text style={styles.errorBannerText}>{analysisError}</Text>
            </View>
          )}

          {/* ── Analyzing indicator ──────────────────────────────────────── */}
          {analyzing && (
            <View
              style={[
                styles.analyzeRow,
                { backgroundColor: C.surface, borderColor: C.border },
              ]}
            >
              <ActivityIndicator size={14} color={C.amber} />
              <Text style={[styles.analyzeText, { color: C.textMuted }]}>
                Analyzing your entry…
              </Text>
            </View>
          )}

          {/* ── Emotional Vocabulary Expander ───────────────────────────── */}
          {vocabSuggestions.length > 0 && (
            <View
              style={[
                styles.vocabCard,
                { backgroundColor: C.surface, borderColor: C.border },
              ]}
            >
              <View style={styles.vocabHeader}>
                <View
                  style={[
                    styles.vocabIconWrap,
                    { backgroundColor: C.violetDim },
                  ]}
                >
                  <Ionicons
                    name="sparkles-outline"
                    size={16}
                    color={C.violet}
                  />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={[styles.vocabTitle, { color: C.textPrimary }]}>
                    Emotional Vocabulary
                  </Text>
                  <Text style={[styles.vocabSubtitle, { color: C.textMuted }]}>
                    Richer words for your {vocabEmotion} state
                  </Text>
                </View>
              </View>
              <View style={styles.vocabChips}>
                {vocabSuggestions.map((word) => (
                  <View
                    key={word}
                    style={[
                      styles.vocabChip,
                      {
                        borderColor: C.border,
                        backgroundColor: C.surfaceElevated,
                      },
                    ]}
                  >
                    <Text
                      style={[styles.vocabChipText, { color: C.textSecondary }]}
                    >
                      {word}
                    </Text>
                  </View>
                ))}
              </View>
              <Text style={[styles.vocabHint, { color: C.textMuted }]}>
                Use one word that feels truest in your next sentence.
              </Text>
            </View>
          )}

          {/* ── Past Entries ────────────────────────────────────────────── */}
          <Text style={styles.sectionTitle}>Past Entries</Text>
          {entriesLoading && entries.length === 0 ? (
            <ActivityIndicator
              color={C.amber}
              style={{ marginVertical: SpiralSpacing.md }}
            />
          ) : entries.length === 0 ? (
            <View
              style={[
                styles.entryCard,
                { alignItems: "center", paddingVertical: SpiralSpacing.lg },
              ]}
            >
              <Text
                style={[
                  styles.entryPreview,
                  { textAlign: "center", color: C.textMuted },
                ]}
              >
                Your entries will appear here after you write your first one.
              </Text>
            </View>
          ) : (
            entries.map((entry) => (
              <Pressable
                key={entry.id}
                style={({ pressed }) => [
                  styles.entryCard,
                  pressed && styles.entryCardPressed,
                ]}
              >
                <View style={styles.entryHeader}>
                  <Text style={styles.entryDate}>{entry.date}</Text>
                  <View style={styles.emotionRow}>
                    {entry.emotions.map((e) => (
                      <EmotionTag key={e} emotion={e} />
                    ))}
                  </View>
                </View>
                <Text style={styles.entryPreview} numberOfLines={2}>
                  {entry.preview}
                </Text>
              </Pressable>
            ))
          )}

          {/* Spacer for floating tab bar */}
          <View style={{ height: 100 }} />
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────
function makeStyles(C: SpiralColorSet) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: C.midnight },
    flex: { flex: 1 },
    scroll: { flex: 1 },
    scrollContent: {
      paddingHorizontal: SpiralSpacing.lg,
      paddingTop: SpiralSpacing.md,
    },

    header: { marginBottom: SpiralSpacing.lg },
    headerRow: {
      flexDirection: "row",
      alignItems: "flex-start",
      justifyContent: "space-between",
    },
    greeting: {
      fontSize: 28,
      fontWeight: "700",
      color: C.textPrimary,
      letterSpacing: -0.5,
    },
    dateText: { fontSize: 14, color: C.textSecondary, marginTop: 4 },
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

    quickGuideCard: {
      borderWidth: 1,
      borderColor: C.border,
      borderRadius: SpiralRadius.lg,
      backgroundColor: C.surface,
      padding: SpiralSpacing.md,
      marginBottom: SpiralSpacing.md,
    },
    quickGuideHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: SpiralSpacing.sm,
      marginBottom: 8,
    },
    quickGuideIconWrap: {
      width: 28,
      height: 28,
      borderRadius: 14,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: C.amberDim,
      borderWidth: 1,
      borderColor: C.amber + "44",
    },
    quickGuideTitle: {
      fontSize: 14,
      fontWeight: "700",
      color: C.textPrimary,
    },
    quickGuideText: {
      fontSize: 13,
      lineHeight: 20,
      color: C.textSecondary,
      marginBottom: 10,
    },
    quickGuideLinkRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: 6,
    },
    quickGuideLinkText: {
      fontSize: 12,
      fontWeight: "700",
      letterSpacing: 0.3,
      color: C.amber,
      textTransform: "uppercase",
    },

    promptCard: {
      flexDirection: "row",
      backgroundColor: C.surface,
      borderRadius: SpiralRadius.lg,
      borderWidth: 1,
      borderColor: C.border,
      marginBottom: SpiralSpacing.lg,
      overflow: "hidden",
    },
    promptAccentBar: { width: 3, backgroundColor: C.amber },
    promptContent: { flex: 1, padding: SpiralSpacing.md },
    promptLabel: {
      fontSize: 10,
      fontWeight: "700",
      letterSpacing: 1.8,
      textTransform: "uppercase",
      color: C.amber,
      marginBottom: 6,
    },
    promptText: {
      fontSize: 15,
      lineHeight: 22,
      color: C.textSecondary,
      fontStyle: "italic",
    },

    editorContainer: {
      backgroundColor: C.surface,
      borderRadius: SpiralRadius.lg,
      borderWidth: 1,
      borderColor: C.border,
      marginBottom: SpiralSpacing.lg,
    },
    editor: {
      minHeight: 160,
      padding: SpiralSpacing.md,
      fontSize: 16,
      lineHeight: 26,
      color: C.textPrimary,
      fontFamily: Platform.OS === "ios" ? "Georgia" : "serif",
    },
    editorFooter: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      padding: SpiralSpacing.sm,
      paddingHorizontal: SpiralSpacing.md,
      borderTopWidth: 1,
      borderTopColor: C.border,
    },
    editorFooterLeft: {
      flexDirection: "row",
      alignItems: "center",
      gap: SpiralSpacing.sm,
    },
    wordCount: { fontSize: 12, color: C.textMuted },
    micButton: {
      width: 32,
      height: 32,
      borderRadius: 16,
      alignItems: "center",
      justifyContent: "center",
      borderWidth: 1,
    },
    voiceLocaleRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
      paddingHorizontal: SpiralSpacing.md,
      paddingBottom: SpiralSpacing.sm,
      marginTop: -2,
    },
    voiceLabel: {
      fontSize: 11,
      fontWeight: "600",
      textTransform: "uppercase",
      letterSpacing: 0.8,
    },
    voiceLocaleChip: {
      borderWidth: 1,
      borderRadius: SpiralRadius.pill,
      paddingHorizontal: 10,
      paddingVertical: 4,
    },
    voiceLocaleChipText: {
      fontSize: 11,
      fontWeight: "700",
      letterSpacing: 0.4,
    },
    submitButton: {
      backgroundColor: C.amber,
      paddingHorizontal: SpiralSpacing.md,
      paddingVertical: SpiralSpacing.sm,
      borderRadius: SpiralRadius.pill,
    },
    submitButtonPressed: { opacity: 0.75 },
    submitButtonDisabled: { backgroundColor: C.border },
    submitButtonText: {
      fontSize: 13,
      fontWeight: "700",
      color: C.midnight,
    },

    sectionTitle: {
      fontSize: 11,
      fontWeight: "700",
      letterSpacing: 1.8,
      textTransform: "uppercase",
      color: C.textMuted,
      marginBottom: SpiralSpacing.md,
    },

    entryCard: {
      backgroundColor: C.surface,
      borderRadius: SpiralRadius.lg,
      borderWidth: 1,
      borderColor: C.border,
      padding: SpiralSpacing.md,
      marginBottom: SpiralSpacing.sm,
    },
    entryCardPressed: {
      borderColor: C.amber + "66",
      backgroundColor: C.surfaceElevated,
    },
    entryHeader: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: SpiralSpacing.sm,
    },
    entryDate: { fontSize: 12, fontWeight: "600", color: C.textMuted },
    emotionRow: { flexDirection: "row", gap: 4 },
    entryPreview: {
      fontSize: 14,
      lineHeight: 20,
      color: C.textSecondary,
    },

    // ── Error / analyzing banners ──────────────────────────────────────────
    errorBanner: {
      flexDirection: "row",
      alignItems: "center",
      gap: 6,
      borderWidth: 1,
      borderRadius: SpiralRadius.md,
      paddingHorizontal: SpiralSpacing.md,
      paddingVertical: SpiralSpacing.sm,
      marginBottom: SpiralSpacing.md,
    },
    errorBannerText: { fontSize: 13, color: "#F87171", flex: 1 },
    analyzeRow: {
      flexDirection: "row",
      alignItems: "center",
      gap: 8,
      borderWidth: 1,
      borderRadius: SpiralRadius.md,
      paddingHorizontal: SpiralSpacing.md,
      paddingVertical: SpiralSpacing.sm,
      marginBottom: SpiralSpacing.md,
    },
    analyzeText: { fontSize: 13 },

    // ── Vocabulary expander ───────────────────────────────────────────────
    vocabCard: {
      borderWidth: 1,
      borderRadius: SpiralRadius.lg,
      padding: SpiralSpacing.md,
      marginBottom: SpiralSpacing.lg,
    },
    vocabHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: SpiralSpacing.sm,
      marginBottom: SpiralSpacing.sm,
    },
    vocabIconWrap: {
      width: 28,
      height: 28,
      borderRadius: 14,
      alignItems: "center",
      justifyContent: "center",
    },
    vocabTitle: {
      fontSize: 13,
      fontWeight: "700",
      marginBottom: 2,
    },
    vocabSubtitle: {
      fontSize: 12,
    },
    vocabChips: {
      flexDirection: "row",
      flexWrap: "wrap",
      gap: 8,
      marginTop: 2,
      marginBottom: SpiralSpacing.sm,
    },
    vocabChip: {
      borderWidth: 1,
      borderRadius: SpiralRadius.pill,
      paddingHorizontal: 10,
      paddingVertical: 6,
    },
    vocabChipText: {
      fontSize: 12,
      fontWeight: "600",
      textTransform: "capitalize",
    },
    vocabHint: {
      fontSize: 12,
      lineHeight: 18,
    },

    // ── Reflection Modal ───────────────────────────────────────────────────
    modalOverlay: {
      flex: 1,
      justifyContent: "flex-end",
      backgroundColor: "rgba(0,0,0,0.6)",
    },
    modalSheet: {
      borderTopLeftRadius: SpiralRadius.xl,
      borderTopRightRadius: SpiralRadius.xl,
      borderWidth: 1,
      borderBottomWidth: 0,
      padding: SpiralSpacing.lg,
      paddingBottom: SpiralSpacing.xxl,
      maxHeight: "80%",
    },
    modalHandle: {
      width: 40,
      height: 4,
      borderRadius: 2,
      alignSelf: "center",
      marginBottom: SpiralSpacing.lg,
    },
    modalHeader: {
      flexDirection: "row",
      alignItems: "center",
      gap: SpiralSpacing.sm,
      marginBottom: 6,
    },
    modalIconWrap: {
      width: 36,
      height: 36,
      borderRadius: SpiralRadius.md,
      alignItems: "center",
      justifyContent: "center",
    },
    modalTitle: { fontSize: 18, fontWeight: "700" },
    modalSubtitle: {
      fontSize: 14,
      lineHeight: 20,
      marginBottom: SpiralSpacing.lg,
    },
    modalLoading: {
      flexDirection: "row",
      alignItems: "center",
      gap: SpiralSpacing.sm,
      paddingVertical: SpiralSpacing.lg,
    },
    modalLoadingText: { fontSize: 14 },
    questionRow: {
      flexDirection: "row",
      alignItems: "flex-start",
      gap: SpiralSpacing.sm,
      borderBottomWidth: 1,
      paddingVertical: SpiralSpacing.md,
    },
    questionNum: {
      width: 28,
      height: 28,
      borderRadius: 14,
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0,
    },
    questionNumText: { fontSize: 13, fontWeight: "700" },
    questionText: { flex: 1, fontSize: 15, lineHeight: 22, paddingTop: 4 },
    modalClose: {
      height: 50,
      borderRadius: SpiralRadius.pill,
      alignItems: "center",
      justifyContent: "center",
      marginTop: SpiralSpacing.lg,
    },
    modalCloseText: { fontSize: 15, fontWeight: "700" },
  });
}
