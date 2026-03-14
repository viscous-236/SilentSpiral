import { api } from "./api";

// ─── Types matching backend schemas ──────────────────────────────────────────

export interface EmotionScore {
  label: string;
  score: number;
}

// POST /analyze → request
export interface AnalyzeRequest {
  text: string;
}

// POST /analyze → response (mirrors backend AnalyzeResponse)
export interface AnalyzeResult {
  /** Top emotions above threshold, sorted score descending */
  emotions: EmotionScore[];
  top_emotion: string;
  intensity: number;
  emotion_category: "positive" | "negative" | "neutral";
  word_count: number;
  crisis_flag: boolean;
}

// ─── Service call ─────────────────────────────────────────────────────────────
export async function analyzeText(req: AnalyzeRequest): Promise<AnalyzeResult> {
  const { data } = await api.post<AnalyzeResult>("/analyze", req);
  return data;
}

/** Convert the API emotion array to a label→score dict (used by /patterns/analyze) */
export function emotionArrayToDict(
  emotions: EmotionScore[],
): Record<string, number> {
  return Object.fromEntries(emotions.map((e) => [e.label, e.score]));
}
