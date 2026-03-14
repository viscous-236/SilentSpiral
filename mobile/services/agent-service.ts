import { api } from "./api";
import type { EmotionScore } from "./emotion-service";

// ─── Reflection Agent ─────────────────────────────────────────────────────────
// Mirrors backend ReflectRequest + ReflectResponse schemas exactly.

export interface ReflectRequest {
  journal_text: string;
  emotions: EmotionScore[];
  history?: string[];
  mirror_phrase?: string;
}

export interface ReflectResponse {
  questions: string[];
  top_emotion: string;
  mirror_phrase_used: string | null;
}

export async function getReflection(
  req: ReflectRequest,
): Promise<ReflectResponse> {
  const { data } = await api.post<ReflectResponse>("/agent/reflect", req);
  return data;
}

// ─── Pattern analysis — POST /patterns/analyze ────────────────────────────────

export interface EmotionRecord {
  user_id: string;
  timestamp: string; // ISO8601 e.g. "2026-03-12T00:00:00Z"
  entry_id: string;
  emotions: Record<string, number>;
}

export type AnomalyFlag =
  | "HIGH_VOLATILITY"
  | "DOWNWARD_SPIRAL"
  | "LOW_ENGAGEMENT"
  | null;

export interface WindowStats {
  avg_scores: Record<string, number>;
  dominant_emotion: string;
  volatility_score: number;
  entry_count: number;
}

export interface PatternAnalysisResponse {
  window: WindowStats;
  anomaly: AnomalyFlag;
}

export async function analyzePatterns(
  records: EmotionRecord[],
): Promise<PatternAnalysisResponse> {
  const { data } = await api.post<PatternAnalysisResponse>(
    "/patterns/analyze",
    { records },
  );
  return data;
}

// ─── Pattern Agent — POST /agent/pattern ─────────────────────────────────────

export interface PatternAgentRequest {
  window_stats: WindowStats;
  anomaly_flag?: AnomalyFlag;
  history_summary?: string;
}

export interface PatternAgentResponse {
  insights: string[];
  highlight: string;
  dominant_emotion: string;
}

export async function getPatternNarrative(
  req: PatternAgentRequest,
): Promise<PatternAgentResponse> {
  const { data } = await api.post<PatternAgentResponse>("/agent/pattern", req);
  return data;
}

// ─── Coach Agent — POST /agent/coach ─────────────────────────────────────────

export interface CoachRequest {
  pattern_insight: string;
  anomaly_flag?: AnomalyFlag;
  user_preferences?: Record<string, unknown>;
}

export interface CoachResponse {
  suggestions: string[];
  challenge: string;
  triggered: boolean;
}

export async function getCoaching(req: CoachRequest): Promise<CoachResponse> {
  const { data } = await api.post<CoachResponse>("/agent/coach", req);
  return data;
}
