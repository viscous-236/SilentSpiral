import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  closeSession as closeSessionRequest,
  sendSessionMessage,
  startSession,
  type SessionTurn,
} from "@/services/session-service";

const SESSION_DURATION_SECONDS = 600;

export interface ListeningMessage {
  id: string;
  role: "user" | "agent";
  text: string;
}

interface ListeningSessionState {
  sessionId: string | null;
  messages: ListeningMessage[];
  remainingSeconds: number;
  active: boolean;
  loading: boolean;
  ending: boolean;
  error: string | null;
}

function toTurns(messages: ListeningMessage[]): SessionTurn[] {
  return messages.map((m) => ({ role: m.role, content: m.text }));
}

function toSessionText(messages: ListeningMessage[]): string {
  return messages
    .filter((m) => m.role === "user")
    .map((m) => m.text)
    .join("\n\n");
}

export function useListeningSession() {
  const [state, setState] = useState<ListeningSessionState>({
    sessionId: null,
    messages: [],
    remainingSeconds: SESSION_DURATION_SECONDS,
    active: false,
    loading: false,
    ending: false,
    error: null,
  });

  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const inFlightRef = useRef(false);
  const stateRef = useRef(state);
  stateRef.current = state;

  const clearTimer = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const startCountdown = useCallback(() => {
    clearTimer();
    intervalRef.current = setInterval(() => {
      setState((prev) => {
        if (!prev.active || prev.remainingSeconds <= 1) {
          return { ...prev, remainingSeconds: 0, active: false };
        }
        return { ...prev, remainingSeconds: prev.remainingSeconds - 1 };
      });
    }, 1000);
  }, [clearTimer]);

  useEffect(() => clearTimer, [clearTimer]);

  const start = useCallback(async () => {
    if (inFlightRef.current) return;
    inFlightRef.current = true;
    setState((prev) => ({ ...prev, loading: true, error: null }));

    try {
      const res = await startSession({ duration_seconds: SESSION_DURATION_SECONDS });
      setState({
        sessionId: res.session_id,
        messages: [{ id: `agent-${Date.now()}`, role: "agent", text: res.agent_message }],
        remainingSeconds: res.remaining_seconds,
        active: true,
        loading: false,
        ending: false,
        error: null,
      });
      startCountdown();
    } catch (e) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: e instanceof Error ? e.message : "Failed to start session",
      }));
    } finally {
      inFlightRef.current = false;
    }
  }, [startCountdown]);

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed || inFlightRef.current) return;

    const current = stateRef.current;
    if (!current.active || !current.sessionId) return;

    const userMsg: ListeningMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      text: trimmed,
    };
    const nextMessages = [...current.messages, userMsg];

    setState((prev) => ({
      ...prev,
      messages: nextMessages,
      loading: true,
      error: null,
    }));

    inFlightRef.current = true;
    try {
      const elapsed = Math.max(0, SESSION_DURATION_SECONDS - current.remainingSeconds);
      const res = await sendSessionMessage({
        session_id: current.sessionId,
        user_message: trimmed,
        elapsed_seconds: elapsed,
        history: toTurns(nextMessages),
      });

      setState((prev) => {
        const agentMsg: ListeningMessage = {
          id: `agent-${Date.now()}`,
          role: "agent",
          text: res.agent_reply,
        };
        return {
          ...prev,
          messages: [...prev.messages, agentMsg],
          remainingSeconds: res.remaining_seconds,
          active: !res.session_ended,
          loading: false,
          error: null,
        };
      });

      if (res.session_ended) {
        clearTimer();
      }
    } catch (e) {
      setState((prev) => ({
        ...prev,
        loading: false,
        error: e instanceof Error ? e.message : "Failed to send message",
      }));
    } finally {
      inFlightRef.current = false;
    }
  }, [clearTimer]);

  const close = useCallback(async () => {
    if (inFlightRef.current) return;

    const current = stateRef.current;
    if (!current.sessionId) return;

    const sid = current.sessionId;
    const snapshot = current.messages;

    setState((prev) => ({ ...prev, ending: true, loading: true, active: false, error: null }));

    clearTimer();

    inFlightRef.current = true;
    try {
      const res = await closeSessionRequest({
        session_id: sid,
        history: toTurns(snapshot),
        session_text: toSessionText(snapshot),
      });

      setState((prev) => ({
        ...prev,
        messages: [
          ...prev.messages,
          { id: `close-${Date.now()}`, role: "agent", text: res.closing_message },
        ],
        ending: false,
        loading: false,
      }));
    } catch (e) {
      setState((prev) => ({
        ...prev,
        ending: false,
        loading: false,
        error: e instanceof Error ? e.message : "Failed to close session",
      }));
    } finally {
      inFlightRef.current = false;
    }
  }, [clearTimer]);

  const reset = useCallback(() => {
    clearTimer();
    setState({
      sessionId: null,
      messages: [],
      remainingSeconds: SESSION_DURATION_SECONDS,
      active: false,
      loading: false,
      ending: false,
      error: null,
    });
  }, [clearTimer]);

  const mmss = useMemo(() => {
    const mm = String(Math.floor(state.remainingSeconds / 60)).padStart(2, "0");
    const ss = String(state.remainingSeconds % 60).padStart(2, "0");
    return `${mm}:${ss}`;
  }, [state.remainingSeconds]);

  return {
    ...state,
    timerLabel: mmss,
    start,
    send,
    close,
    reset,
  };
}
