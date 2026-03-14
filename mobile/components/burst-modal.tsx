/**
 * components/burst-modal.tsx
 * ==========================
 * The Burst Session modal — a focused 5-minute venting space where
 * the user can type freely without any judgment or external tracking.
 *
 * UX design principles:
 *   - Full-screen dark overlay with soft glow — feels safe and private
 *   - Countdown ring around the timer — visual urgency without pressure
 *   - Mid-session AI acknowledgments appear at the bottom as a gentle
 *     overlay, fading in and out. Never interrupts the user's typing.
 *   - "I'm done" button always visible — user is in full control
 *   - End-of-session closing message from the AI fills the screen
 *     with a gentle fade, then the modal closes with a soft delay
 *
 * Privacy:
 *   - No user_id sent to the backend
 *   - Session text is not saved to AsyncStorage or any store
 *   - It passes through the Groq API only during the session
 */

import * as Haptics from "expo-haptics";
import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  Animated,
  Easing,
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
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";

import { SpiralColorSet, useSpiralTheme } from "@/context/theme-context";
import { SpiralRadius, SpiralSpacing } from "@/constants/theme";
import { sendBurstAck, sendBurstClose } from "@/services/burst-service";

// ─── Constants ────────────────────────────────────────────────────────────────

const SESSION_DURATION_S = 300; // 5 minutes
const ACK_INTERVAL_MS = 20_000; // 20 seconds between acknowledgments
const CLOSING_DISPLAY_MS = 4_000; // How long to show the closing message

// ─── Types ────────────────────────────────────────────────────────────────────

interface BurstModalProps {
  visible: boolean;
  onClose: () => void;
}

// ─── Component ────────────────────────────────────────────────────────────────

export function BurstModal({ visible, onClose }: BurstModalProps) {
  const { C } = useSpiralTheme();
  const styles = useMemo(() => makeStyles(C), [C]);
  const insets = useSafeAreaInsets();

  // ── State ──────────────────────────────────────────────────────────────────

  const [sessionText, setSessionText] = useState("");
  const [elapsed, setElapsed] = useState(0);
  const [acknowledgment, setAcknowledgment] = useState<string | null>(null);
  const [closingMessage, setClosingMessage] = useState<string | null>(null);
  const [isClosing, setIsClosing] = useState(false);

  // ── Refs ───────────────────────────────────────────────────────────────────

  const textRef = useRef(sessionText);
  textRef.current = sessionText;

  const elapsedRef = useRef(elapsed);
  elapsedRef.current = elapsed;

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const ackTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const isMountedRef = useRef(false);

  // ── Animations ─────────────────────────────────────────────────────────────

  const ackOpacity = useRef(new Animated.Value(0)).current;
  const closingOpacity = useRef(new Animated.Value(0)).current;
  const ringProgress = useRef(new Animated.Value(0)).current; // 0→1 over 300s

  // ── Helpers ────────────────────────────────────────────────────────────────

  const clearTimers = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (ackTimerRef.current) clearInterval(ackTimerRef.current);
    timerRef.current = null;
    ackTimerRef.current = null;
  }, []);

  const showAck = useCallback(
    (text: string) => {
      if (!isMountedRef.current) return;
      setAcknowledgment(text);
      ackOpacity.setValue(0);
      Animated.sequence([
        Animated.timing(ackOpacity, {
          toValue: 1,
          duration: 500,
          useNativeDriver: true,
        }),
        Animated.delay(3000),
        Animated.timing(ackOpacity, {
          toValue: 0,
          duration: 600,
          useNativeDriver: true,
        }),
      ]).start(() => {
        if (isMountedRef.current) setAcknowledgment(null);
      });
    },
    [ackOpacity]
  );

  const fetchAck = useCallback(async () => {
    if (!isMountedRef.current) return;
    const text = textRef.current.trim();
    if (!text) return; // Don't acknowledge an empty session

    const res = await sendBurstAck({
      partial_text: text,
      elapsed_seconds: elapsedRef.current,
    });
    if (isMountedRef.current) {
      showAck(res.acknowledgment);
    }
  }, [showAck]);

  const endSession = useCallback(async () => {
    if (isClosing) return;
    setIsClosing(true);
    clearTimers();

    if (Platform.OS !== "web") {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }

    // Fetch closing message
    const text = textRef.current.trim();
    const res = await sendBurstClose({
      session_text: text || "The user sat quietly in the space.",
    });

    if (!isMountedRef.current) return;

    setClosingMessage(res.closing_message);

    // Fade in closing message
    Animated.timing(closingOpacity, {
      toValue: 1,
      duration: 700,
      easing: Easing.out(Easing.ease),
      useNativeDriver: true,
    }).start();

    // Auto-close after display
    setTimeout(() => {
      if (!isMountedRef.current) return;
      Animated.timing(closingOpacity, {
        toValue: 0,
        duration: 500,
        useNativeDriver: true,
      }).start(() => {
        if (isMountedRef.current) onClose();
      });
    }, CLOSING_DISPLAY_MS);
  }, [isClosing, clearTimers, closingOpacity, onClose]);

  // ── Session lifecycle ──────────────────────────────────────────────────────

  useEffect(() => {
    if (!visible) return;

    // Reset state each time modal opens
    isMountedRef.current = true;
    setSessionText("");
    setElapsed(0);
    setAcknowledgment(null);
    setClosingMessage(null);
    setIsClosing(false);
    ringProgress.setValue(0);
    ackOpacity.setValue(0);
    closingOpacity.setValue(0);

    // 1-second countdown tick
    timerRef.current = setInterval(() => {
      if (!isMountedRef.current) return;
      setElapsed((prev) => {
        const next = prev + 1;
        if (next >= SESSION_DURATION_S) {
          clearInterval(timerRef.current!);
          timerRef.current = null;
          endSession();
        }
        return next;
      });
    }, 1000);

    // Ring animation (5 min)
    Animated.timing(ringProgress, {
      toValue: 1,
      duration: SESSION_DURATION_S * 1000,
      easing: Easing.linear,
      useNativeDriver: false,
    }).start();

    // Mid-session acknowledgments every 20s
    // First ack after 20s, then every 20s
    ackTimerRef.current = setInterval(fetchAck, ACK_INTERVAL_MS);

    return () => {
      isMountedRef.current = false;
      clearTimers();
    };
  }, [visible]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Timer display ──────────────────────────────────────────────────────────

  const remaining = SESSION_DURATION_S - elapsed;
  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");

  // Ring stroke color: green → amber → red as time runs out
  const ringColor = ringProgress.interpolate({
    inputRange: [0, 0.6, 0.85, 1],
    outputRange: [C.teal, C.amber, "#F87171", "#F87171"],
  });

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <Modal
      visible={visible}
      animationType="fade"
      statusBarTranslucent
      transparent={false}
    >
      <KeyboardAvoidingView
        style={[styles.root, { paddingTop: insets.top, paddingBottom: insets.bottom }]}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        {/* ── Closing overlay ────────────────────────────────────────────── */}
        {isClosing && closingMessage && (
          <Animated.View
            style={[styles.closingOverlay, { opacity: closingOpacity }]}
          >
            <Text style={styles.closingEmoji}>🌿</Text>
            <Text style={styles.closingText}>{closingMessage}</Text>
          </Animated.View>
        )}

        {!isClosing && (
          <>
            {/* ── Header: timer + close ──────────────────────────────────── */}
            <View style={styles.header}>
              {/* Timer ring */}
              <View style={styles.timerWrap}>
                <Animated.Text style={[styles.timerText, { color: ringColor }]}>
                  {mm}:{ss}
                </Animated.Text>
                <Text style={styles.timerLabel}>remaining</Text>
              </View>

              {/* Done button */}
              <Pressable
                onPress={endSession}
                style={({ pressed }) => [
                  styles.doneBtn,
                  pressed && { opacity: 0.7 },
                ]}
                hitSlop={8}
              >
                <Ionicons name="checkmark-circle" size={22} color={C.teal} />
                <Text style={styles.doneBtnText}>I&apos;m done</Text>
              </Pressable>
            </View>

            {/* ── Prompt ────────────────────────────────────────────────── */}
            <View style={styles.promptWrap}>
              <Text style={styles.promptText}>
                Just let it out. No one is reading this.
              </Text>
            </View>

            {/* ── Text area ─────────────────────────────────────────────── */}
            <ScrollView
              style={styles.scrollArea}
              contentContainerStyle={styles.scrollContent}
              keyboardShouldPersistTaps="handled"
            >
              <TextInput
                style={styles.textInput}
                multiline
                autoFocus
                placeholder="Start typing… or don't. Both are okay."
                placeholderTextColor={C.textMuted}
                value={sessionText}
                onChangeText={setSessionText}
                scrollEnabled={false}
                textAlignVertical="top"
              />
            </ScrollView>

            {/* ── Acknowledgment bubble ──────────────────────────────────── */}
            {acknowledgment && (
              <Animated.View
                style={[styles.ackBubble, { opacity: ackOpacity }]}
                pointerEvents="none"
              >
                <Text style={styles.ackText}>{acknowledgment}</Text>
              </Animated.View>
            )}
          </>
        )}
      </KeyboardAvoidingView>
    </Modal>
  );
}

// ─── Styles ───────────────────────────────────────────────────────────────────

function makeStyles(C: SpiralColorSet) {
  return StyleSheet.create({
    root: {
      flex: 1,
      backgroundColor: C.midnight,
    },

    // Header
    header: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      paddingHorizontal: SpiralSpacing.lg,
      paddingTop: SpiralSpacing.md,
      paddingBottom: SpiralSpacing.sm,
      borderBottomWidth: 1,
      borderBottomColor: C.border,
    },
    timerWrap: {
      alignItems: "center",
    },
    timerText: {
      fontSize: 26,
      fontWeight: "700",
      letterSpacing: 1,
    },
    timerLabel: {
      fontSize: 11,
      color: C.textMuted,
      letterSpacing: 0.5,
      marginTop: 1,
    },
    doneBtn: {
      flexDirection: "row",
      alignItems: "center",
      gap: 6,
      backgroundColor: C.tealDim,
      paddingHorizontal: SpiralSpacing.md,
      paddingVertical: SpiralSpacing.sm,
      borderRadius: SpiralRadius.pill,
      borderWidth: 1,
      borderColor: C.teal + "44",
    },
    doneBtnText: {
      fontSize: 14,
      fontWeight: "600",
      color: C.teal,
      letterSpacing: 0.3,
    },

    // Prompt
    promptWrap: {
      paddingHorizontal: SpiralSpacing.lg,
      paddingTop: SpiralSpacing.lg,
      paddingBottom: SpiralSpacing.sm,
    },
    promptText: {
      fontSize: 14,
      color: C.textSecondary,
      fontStyle: "italic",
      lineHeight: 20,
      textAlign: "center",
    },

    // Text input
    scrollArea: {
      flex: 1,
    },
    scrollContent: {
      flexGrow: 1,
      paddingHorizontal: SpiralSpacing.lg,
      paddingVertical: SpiralSpacing.md,
    },
    textInput: {
      flex: 1,
      minHeight: 300,
      fontSize: 17,
      lineHeight: 27,
      color: C.textPrimary,
      fontWeight: "400",
    },

    // Acknowledgment bubble
    ackBubble: {
      position: "absolute",
      bottom: 40,
      alignSelf: "center",
      backgroundColor: C.violetDim,
      borderWidth: 1,
      borderColor: C.violet + "55",
      paddingHorizontal: SpiralSpacing.lg,
      paddingVertical: SpiralSpacing.sm,
      borderRadius: SpiralRadius.pill,
      maxWidth: "80%",
    },
    ackText: {
      fontSize: 14,
      color: C.violet,
      fontWeight: "500",
      textAlign: "center",
      letterSpacing: 0.2,
    },

    // Closing overlay
    closingOverlay: {
      flex: 1,
      alignItems: "center",
      justifyContent: "center",
      paddingHorizontal: SpiralSpacing.xxl,
      gap: SpiralSpacing.lg,
    },
    closingEmoji: {
      fontSize: 48,
    },
    closingText: {
      fontSize: 20,
      lineHeight: 32,
      color: C.textPrimary,
      textAlign: "center",
      fontWeight: "400",
      letterSpacing: 0.2,
    },
  });
}
