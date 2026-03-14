import { api } from "./api";

const SESSION_DURATION_SECONDS = 600;

export interface SessionTurn {
  role: "user" | "agent";
  content: string;
}

export interface SessionStartRequest {
  duration_seconds?: number;
}

export interface SessionStartResponse {
  session_id: string;
  agent_message: string;
  remaining_seconds: number;
}

export interface SessionMessageRequest {
  session_id: string;
  user_message: string;
  elapsed_seconds: number;
  history: SessionTurn[];
}

export interface SessionMessageResponse {
  agent_reply: string;
  remaining_seconds: number;
  session_ended: boolean;
}

export interface SessionCloseRequest {
  session_id: string;
  history: SessionTurn[];
  session_text: string;
}

export interface SessionCloseResponse {
  closing_message: string;
}

export async function startSession(
  req: SessionStartRequest = {}
): Promise<SessionStartResponse> {
  try {
    const { data } = await api.post<SessionStartResponse>("/agent/session/start", {
      duration_seconds: req.duration_seconds ?? SESSION_DURATION_SECONDS,
    });
    return data;
  } catch {
    return {
      session_id: `local_${Date.now()}`,
      agent_message: "I am here with you. Take your time and share what is heavy.",
      remaining_seconds: SESSION_DURATION_SECONDS,
    };
  }
}

export async function sendSessionMessage(
  req: SessionMessageRequest
): Promise<SessionMessageResponse> {
  try {
    const { data } = await api.post<SessionMessageResponse>("/agent/session/message", req);
    return data;
  } catch {
    return {
      agent_reply: "I hear you. Keep going if you want to.",
      remaining_seconds: Math.max(0, SESSION_DURATION_SECONDS - req.elapsed_seconds),
      session_ended: false,
    };
  }
}

export async function closeSession(
  req: SessionCloseRequest
): Promise<SessionCloseResponse> {
  try {
    const { data } = await api.post<SessionCloseResponse>("/agent/session/close", req);
    return data;
  } catch {
    return {
      closing_message:
        "Thank you for letting that out. You gave your feelings space, and that matters.",
    };
  }
}
