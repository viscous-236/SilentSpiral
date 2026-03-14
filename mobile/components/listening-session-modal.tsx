import * as Haptics from "expo-haptics";
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
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

import { SpiralRadius, SpiralSpacing } from "@/constants/theme";
import { SpiralColorSet, useSpiralTheme } from "@/context/theme-context";
import { useListeningSession } from "@/hooks/use-listening-session";

interface ListeningSessionModalProps {
  visible: boolean;
  onClose: () => void;
}

export function ListeningSessionModal({
  visible,
  onClose,
}: ListeningSessionModalProps) {
  const { C } = useSpiralTheme();
  const styles = useMemo(() => makeStyles(C), [C]);
  const insets = useSafeAreaInsets();

  const {
    messages,
    active,
    loading,
    ending,
    error,
    timerLabel,
    remainingSeconds,
    start,
    send,
    close,
    reset,
  } = useListeningSession();

  const [draft, setDraft] = useState("");
  const didAutoCloseRef = useRef(false);
  const scrollRef = useRef<ScrollView | null>(null);

  useEffect(() => {
    if (!visible) {
      didAutoCloseRef.current = false;
      setDraft("");
      reset();
      return;
    }

    start();
  }, [visible, start, reset]);

  useEffect(() => {
    if (!visible) return;
    const t = setTimeout(() => scrollRef.current?.scrollToEnd({ animated: true }), 40);
    return () => clearTimeout(t);
  }, [messages, visible]);

  useEffect(() => {
    if (!visible || didAutoCloseRef.current || remainingSeconds > 0 || active || ending) {
      return;
    }
    didAutoCloseRef.current = true;
    close().catch(() => {
      // Keep modal responsive even if close request fails.
    });
  }, [visible, remainingSeconds, active, ending, close]);

  const handleSend = useCallback(async () => {
    const text = draft.trim();
    if (!text || loading || ending || !active) return;
    setDraft("");
    if (Platform.OS !== "web") {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    await send(text);
  }, [draft, loading, ending, active, send]);

  const handleDone = useCallback(async () => {
    if (ending) return;

    if (Platform.OS !== "web") {
      Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
    }

    await close();

    setTimeout(() => {
      onClose();
      reset();
      didAutoCloseRef.current = false;
      setDraft("");
    }, 2200);
  }, [ending, close, onClose, reset]);

  return (
    <Modal visible={visible} animationType="fade" transparent={false} statusBarTranslucent>
      <KeyboardAvoidingView
        style={[styles.root, { paddingTop: insets.top, paddingBottom: insets.bottom }]}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={styles.headerRow}>
          <View>
            <Text style={styles.kicker}>Private Listening Session</Text>
            <Text style={styles.timer}>{timerLabel}</Text>
          </View>
          <Pressable onPress={handleDone} style={styles.doneButton}>
            <Ionicons name="checkmark-circle" size={18} color={C.teal} />
            <Text style={styles.doneText}>Done</Text>
          </Pressable>
        </View>

        <Text style={styles.privacyNotice}>
          This session is temporary. Nothing here is saved after it ends.
        </Text>

        <ScrollView
          ref={scrollRef}
          style={styles.thread}
          contentContainerStyle={styles.threadContent}
          keyboardShouldPersistTaps="handled"
        >
          {messages.map((m) => (
            <View
              key={m.id}
              style={[
                styles.bubble,
                m.role === "user" ? styles.userBubble : styles.agentBubble,
              ]}
            >
              <Text style={styles.bubbleText}>{m.text}</Text>
            </View>
          ))}
          {loading && (
            <View style={[styles.bubble, styles.agentBubble]}>
              <Text style={styles.typingText}>Listening...</Text>
            </View>
          )}
        </ScrollView>

        {error ? <Text style={styles.errorText}>{error}</Text> : null}

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={draft}
            onChangeText={setDraft}
            placeholder="Say what is heavy right now..."
            placeholderTextColor={C.textMuted}
            multiline
            editable={!ending}
          />
          <Pressable
            style={({ pressed }) => [styles.sendButton, pressed && { opacity: 0.75 }]}
            onPress={handleSend}
            disabled={!active || loading || ending || draft.trim().length === 0}
          >
            <Ionicons name="arrow-up" size={20} color={C.midnight} />
          </Pressable>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function makeStyles(C: SpiralColorSet) {
  return StyleSheet.create({
    root: {
      flex: 1,
      backgroundColor: C.midnight,
      paddingHorizontal: SpiralSpacing.lg,
    },
    headerRow: {
      marginTop: SpiralSpacing.sm,
      flexDirection: "row",
      justifyContent: "space-between",
      alignItems: "center",
    },
    kicker: {
      fontSize: 12,
      letterSpacing: 1,
      color: C.textSecondary,
      textTransform: "uppercase",
    },
    timer: {
      marginTop: 4,
      fontSize: 28,
      fontWeight: "700",
      color: C.textPrimary,
    },
    doneButton: {
      flexDirection: "row",
      alignItems: "center",
      gap: SpiralSpacing.xs,
      borderWidth: 1,
      borderColor: `${C.teal}55`,
      borderRadius: SpiralRadius.pill,
      paddingHorizontal: SpiralSpacing.md,
      paddingVertical: SpiralSpacing.sm,
      backgroundColor: `${C.teal}14`,
    },
    doneText: {
      color: C.teal,
      fontWeight: "700",
      fontSize: 14,
    },
    privacyNotice: {
      marginTop: SpiralSpacing.md,
      marginBottom: SpiralSpacing.sm,
      color: C.textSecondary,
      fontSize: 13,
    },
    thread: {
      flex: 1,
      marginTop: SpiralSpacing.xs,
    },
    threadContent: {
      paddingBottom: SpiralSpacing.md,
      gap: SpiralSpacing.sm,
    },
    bubble: {
      maxWidth: "88%",
      borderRadius: SpiralRadius.lg,
      paddingHorizontal: SpiralSpacing.md,
      paddingVertical: SpiralSpacing.sm,
    },
    userBubble: {
      alignSelf: "flex-end",
      backgroundColor: `${C.violet}40`,
      borderColor: `${C.violet}66`,
      borderWidth: 1,
    },
    agentBubble: {
      alignSelf: "flex-start",
      backgroundColor: C.surface,
      borderColor: C.border,
      borderWidth: 1,
    },
    bubbleText: {
      color: C.textPrimary,
      fontSize: 15,
      lineHeight: 21,
    },
    typingText: {
      color: C.textSecondary,
      fontSize: 14,
    },
    inputRow: {
      flexDirection: "row",
      alignItems: "flex-end",
      gap: SpiralSpacing.sm,
      marginTop: SpiralSpacing.sm,
      marginBottom: SpiralSpacing.sm,
    },
    input: {
      flex: 1,
      minHeight: 48,
      maxHeight: 150,
      borderRadius: SpiralRadius.md,
      borderWidth: 1,
      borderColor: C.border,
      backgroundColor: C.surface,
      color: C.textPrimary,
      paddingHorizontal: SpiralSpacing.md,
      paddingVertical: SpiralSpacing.sm,
      fontSize: 15,
    },
    sendButton: {
      width: 44,
      height: 44,
      borderRadius: 22,
      alignItems: "center",
      justifyContent: "center",
      backgroundColor: C.teal,
    },
    errorText: {
      marginTop: SpiralSpacing.xs,
      marginBottom: SpiralSpacing.xs,
      color: "#F87171",
      fontSize: 12,
    },
  });
}
