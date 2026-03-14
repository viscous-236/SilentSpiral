/**
 * services/burst-service.ts
 * ==========================
 * Client-side API calls for the ephemeral Burst Session feature.
 *
 * Endpoints (no auth required):
 *   POST /agent/burst/ack   — mid-session acknowledgment
 *   POST /agent/burst/close — session closing message
 *
 * Privacy note: session text is sent to the backend/Groq API
 * but never stored anywhere. It is ephemeral by design.
 */

import { api } from "./api";

// ─── Ack (mid-session) ────────────────────────────────────────────────────────

export interface BurstAckRequest {
  /** Whatever the user has typed so far (≥1 char, ≤5000 chars) */
  partial_text: string;
  /** Seconds elapsed since session start — clamped to [0, 300] */
  elapsed_seconds: number;
}

export interface BurstAckResponse {
  /** Short warm acknowledgment (≤12 words) */
  acknowledgment: string;
}

/**
 * Call POST /agent/burst/ack to get a mid-session acknowledgment.
 * Returns the acknowledgment string, or a hardcoded fallback on error.
 */
export async function sendBurstAck(
  req: BurstAckRequest
): Promise<BurstAckResponse> {
  try {
    const { data } = await api.post<BurstAckResponse>("/agent/burst/ack", req);
    return data;
  } catch {
    // Graceful degradation — never crash the user's venting session
    return { acknowledgment: "I'm right here with you." };
  }
}

// ─── Close (session ending) ───────────────────────────────────────────────────

export interface BurstCloseRequest {
  /** Complete text from the session (≥1 char, ≤10000 chars) */
  session_text: string;
}

export interface BurstCloseResponse {
  /** 2–3 sentence warm closing affirmation */
  closing_message: string;
}

/**
 * Call POST /agent/burst/close to get a warm session closing message.
 * Returns the closing message, or a hardcoded fallback on error.
 */
export async function sendBurstClose(
  req: BurstCloseRequest
): Promise<BurstCloseResponse> {
  try {
    const { data } = await api.post<BurstCloseResponse>(
      "/agent/burst/close",
      req
    );
    return data;
  } catch {
    return {
      closing_message:
        "You showed up for yourself tonight — that matters. Take a gentle breath when you're ready.",
    };
  }
}
