/**
 * use-dashboard-data.ts
 * ─────────────────────
 * Loads all user data from AsyncStorage and derives the dashboard visuals:
 *   • heatmap  — 5-week × 7-day emotion grid from real entries + checkins
 *   • timeline — last 14 days emotion bars from real entries + checkins
 *   • spiralScore — computed from /patterns/analyze WindowStats
 *   • patternCards — AI-generated, from /patterns/analyze + /agent/pattern
 *
 * Requires at least 2 entries to fire API calls (otherwise shows empty states).
 */

import { useCallback, useEffect, useState } from "react";
import { useFocusEffect } from "expo-router";
import { useAuth } from "@/context/auth-context";
import {
  getDashboardCache,
  setDashboardCache,
  loadCheckins,
  loadEntries,
  mapToDisplayEmotion,
  moodIndexToEmotion,
  toIsoDate,
  type InsightCachePayload,
  type JournalEntry,
  type MoodCheckin,
} from "@/services/journal-store";
import {
  analyzePatterns,
  getCoaching,
  getPatternNarrative,
  type AnomalyFlag,
  type EmotionRecord,
  type WindowStats,
} from "@/services/agent-service";
import type { PatternCardData } from "@/components/pattern-card";

// ─── Derived heatmap ──────────────────────────────────────────────────────────

/** Returns the last 5 weeks (35 days) as a grid compatible with MoodCell */
function buildHeatmap(
  entries: JournalEntry[],
  checkins: MoodCheckin[],
): (string | undefined)[][] {
  // Build a date→latest-emotion lookup for fast access.
  const byDate: Record<string, { emotion: string; ts: number }> = {};
  const parseTs = (id: string): number => {
    const n = Number(id);
    return Number.isFinite(n) ? n : 0;
  };

  const upsert = (isoDate: string, emotion: string, ts: number) => {
    const current = byDate[isoDate];
    if (!current || ts >= current.ts) {
      byDate[isoDate] = { emotion, ts };
    }
  };

  for (const e of entries) {
    upsert(
      e.isoDate,
      mapToDisplayEmotion(e.emotions[0] ?? "neutral"),
      parseTs(e.id),
    );
  }
  for (const c of checkins) {
    upsert(c.isoDate, moodIndexToEmotion(c.moodIndex), parseTs(c.id));
  }

  // Build a 5x7 grid aligned to week columns; include current week up to today.
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const dayOfWeek = today.getDay(); // 0=Sun ... 6=Sat

  // End on Saturday of the current week so WEEK_DAYS columns stay aligned.
  // Future cells in this week remain empty, but today's input is always included.
  const gridEnd = new Date(today);
  gridEnd.setDate(today.getDate() + (6 - dayOfWeek));

  const gridStart = new Date(gridEnd);
  gridStart.setDate(gridEnd.getDate() - 34);

  const grid: (string | undefined)[][] = [];
  const cursor = new Date(gridStart);
  for (let week = 0; week < 5; week++) {
    const row: (string | undefined)[] = [];
    for (let day = 0; day < 7; day++) {
      const key = toIsoDate(cursor);
      row.push(byDate[key]?.emotion);
      cursor.setDate(cursor.getDate() + 1);
    }
    grid.push(row);
  }
  return grid;
}

// ─── Derived timeline ─────────────────────────────────────────────────────────

interface TimelinePoint {
  day: string;    // display day number e.g. "12"
  emotion: string;
  intensity: number;
}

function buildTimeline(
  entries: JournalEntry[],
  checkins: MoodCheckin[],
): TimelinePoint[] {
  // Merge entries + check-ins, keeping the latest event per day.
  const byDate: Record<string, TimelinePoint & { ts: number }> = {};
  const parseTs = (id: string): number => {
    const n = Number(id);
    return Number.isFinite(n) ? n : 0;
  };

  const upsert = (isoDate: string, point: TimelinePoint, ts: number) => {
    const current = byDate[isoDate];
    if (!current || ts >= current.ts) {
      byDate[isoDate] = { ...point, ts };
    }
  };

  for (const e of entries) {
    upsert(
      e.isoDate,
      {
        day: e.isoDate.slice(8), // "12" from "2026-03-12"
        emotion: mapToDisplayEmotion(e.emotions[0] ?? "neutral"),
        intensity: e.intensity,
      },
      parseTs(e.id),
    );
  }
  for (const c of checkins) {
    const intensity = [0.3, 0.45, 0.5, 0.7, 0.9][c.moodIndex] ?? 0.5;
    upsert(
      c.isoDate,
      {
        day: c.isoDate.slice(8),
        emotion: moodIndexToEmotion(c.moodIndex),
        intensity,
      },
      parseTs(c.id),
    );
  }

  // Take last 14 sorted by isoDate
  return Object.entries(byDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .slice(-14)
    .map(([, v]) => ({
      day: v.day,
      emotion: v.emotion,
      intensity: v.intensity,
    }));
}

// ─── Spiral score ─────────────────────────────────────────────────────────────

function computeSpiralScore(
  stats: WindowStats,
): number {
  let positive = 0;
  let difficult = 0;

  for (const [label, score] of Object.entries(stats.avg_scores)) {
    const bucket = mapToDisplayEmotion(label);
    if (bucket === "joy" || bucket === "calm") {
      positive += score;
    } else if (
      bucket === "sadness"
      || bucket === "anxiety"
      || bucket === "anger"
    ) {
      difficult += score;
    }
  }

  // Emotion vectors: balance of positive vs difficult emotional signal.
  const totalTone = positive + difficult;
  const tone = totalTone > 0 ? positive / totalTone : 0.5;

  // Entry frequency: more consistent journaling raises confidence in the signal.
  const frequency = Math.min(stats.entry_count, 30) / 30;

  // Volatility: higher volatility lowers stability.
  const stability = Math.max(0, Math.min(1, 1 - stats.volatility_score));

  return Math.round(tone * 45 + frequency * 25 + stability * 30);
}

// ─── Pattern cards from AI response ──────────────────────────────────────────

const ICON_MAP: Record<string, string> = {
  joy: "sunny-outline",
  calm: "leaf-outline",
  sadness: "rainy-outline",
  anxiety: "alert-circle-outline",
  anger: "flame-outline",
  neutral: "ellipse-outline",
};

function buildPatternCards(
  highlight: string,
  insights: string[],
  dominantEmotion: string,
  anomaly: AnomalyFlag,
): PatternCardData[] {
  const displayEmotion = mapToDisplayEmotion(dominantEmotion);
  const timeLabel = anomaly === "DOWNWARD_SPIRAL"
    ? "Downward spiral"
    : anomaly === "HIGH_VOLATILITY"
      ? "High volatility"
      : anomaly === "LOW_ENGAGEMENT"
        ? "Low engagement"
        : "Current window";

  // First card uses the AI headline; subsequent cards use each insight sentence
  return insights.map((insight, i) => ({
    id: `ai-${i}`,
    icon: (ICON_MAP[displayEmotion] ?? "sparkles") as PatternCardData["icon"],
    title: i === 0 ? highlight : `Insight ${i + 1}`,
    body: insight,
    emotion: displayEmotion,
    timeframe: i === 0 ? timeLabel : "Pattern",
  }));
}

// ─── Hook ─────────────────────────────────────────────────────────────────────

interface DashboardData {
  heatmap: (string | undefined)[][];
  timeline: TimelinePoint[];
  spiralScore: number;
  patternCards: PatternCardData[];
  coachSuggestions: string[];
  coachChallenge: string;
  windowStats: WindowStats | null;
  anomaly: AnomalyFlag;
  loading: boolean;
  patternLoading: boolean;
  coachLoading: boolean;
  hasData: boolean;
}

// InsightCachePayload is defined in journal-store.ts (single source of truth).
// Locally we narrow the generic unknowns to the concrete types used in this hook.
type LocalCachePayload = InsightCachePayload & {
  windowStats: WindowStats;
  anomaly: AnomalyFlag;
  patternCards: PatternCardData[];
};

function buildInsightsSignature(entries: JournalEntry[]): string {
  const normalized = entries
    .filter((e) => Object.keys(e.emotionScores).length > 0)
    .map((e) => ({
      id: e.id,
      isoDate: e.isoDate,
      intensity: e.intensity,
      emotionScores: e.emotionScores,
    }))
    .sort((a, b) => a.isoDate.localeCompare(b.isoDate) || a.id.localeCompare(b.id));
  return JSON.stringify(normalized);
}

export function useDashboardData(): DashboardData {
  const { user } = useAuth();

  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [checkins, setCheckins] = useState<MoodCheckin[]>([]);
  const [windowStats, setWindowStats] = useState<WindowStats | null>(null);
  const [anomaly, setAnomaly] = useState<AnomalyFlag>(null);
  const [patternCards, setPatternCards] = useState<PatternCardData[]>([]);
  const [coachSuggestions, setCoachSuggestions] = useState<string[]>([]);
  const [coachChallenge, setCoachChallenge] = useState("");
  const [spiralScore, setSpiralScore] = useState(0);
  const [loading, setLoading] = useState(true);
  const [patternLoading, setPatternLoading] = useState(false);
  const [coachLoading, setCoachLoading] = useState(false);

  // ── Load local data on every focus (refreshes after check-ins) ──────────────
  useFocusEffect(
    useCallback(() => {
      if (!user?.id) {
        setEntries([]);
        setCheckins([]);
        setLoading(false);
        return;
      }

      setLoading(true);
      Promise.all([loadEntries(user.id), loadCheckins(user.id)])
        .then(([e, c]) => {
          setEntries(e);
          setCheckins(c);
        })
        .finally(() => setLoading(false));
    }, [user?.id]),
  );

  // ── Call pattern API whenever entries change and count ≥ 2 ─────────────────
  const fetchPatterns = useCallback(async () => {
    if (!user?.id) {
      setWindowStats(null);
      setAnomaly(null);
      setPatternCards([]);
      setCoachSuggestions([]);
      setCoachChallenge("");
      setSpiralScore(0);
      return;
    }

    if (entries.length < 2) {
      setWindowStats(null);
      setAnomaly(null);
      setPatternCards([]);
      setCoachSuggestions([]);
      setCoachChallenge("");
      setSpiralScore(0);
      return;
    }

    // Only entries with real emotionScores can be sent to /patterns/analyze
    const validEntries = entries.filter(
      (e) => Object.keys(e.emotionScores).length > 0,
    );
    if (validEntries.length < 2) {
      setWindowStats(null);
      setAnomaly(null);
      setPatternCards([]);
      setCoachSuggestions([]);
      setCoachChallenge("");
      setSpiralScore(0);
      return;
    }

    const signature = buildInsightsSignature(validEntries);
    const today = toIsoDate(new Date());

    const cached = (await getDashboardCache(user.id)) as LocalCachePayload | null;
    if (cached) {
      const isFresh = cached.generatedOn === today;
      const isSameInput = cached.signature === signature;
      if (isFresh && isSameInput) {
        setWindowStats(cached.windowStats);
        setAnomaly(cached.anomaly);
        setSpiralScore(cached.spiralScore);
        setPatternCards(cached.patternCards);
        setCoachSuggestions(cached.coachSuggestions);
        setCoachChallenge(cached.coachChallenge);
        return;
      }
    }

    setPatternLoading(true);
    setCoachLoading(true);
    try {
      const records: EmotionRecord[] = validEntries.map((e) => ({
        user_id: user.id,
        timestamp: `${e.isoDate}T00:00:00Z`,
        entry_id: e.id,
        emotions: e.emotionScores,
      }));

      const analysisRes = await analyzePatterns(records);
      const stats = analysisRes.window;
      const flag = analysisRes.anomaly;
      const score = computeSpiralScore(stats);

      setWindowStats(stats);
      setAnomaly(flag);
      setSpiralScore(score);

      // Fetch Pattern Agent narrative only when we have good window data
      const narrativeRes = await getPatternNarrative({
        window_stats: stats,
        anomaly_flag: flag,
        history_summary: "",
      });

      setPatternCards(
        buildPatternCards(
          narrativeRes.highlight,
          narrativeRes.insights,
          narrativeRes.dominant_emotion,
          flag,
        ),
      );

      const coachRes = await getCoaching({
        pattern_insight: narrativeRes.insights.join(" "),
        anomaly_flag: flag,
        user_preferences: {},
      });

      setCoachSuggestions(coachRes.suggestions);
      setCoachChallenge(coachRes.challenge);

      await setDashboardCache(user.id, {
        signature,
        generatedOn: today,
        spiralScore: score,
        windowStats: stats,
        anomaly: flag,
        patternCards: buildPatternCards(
          narrativeRes.highlight,
          narrativeRes.insights,
          narrativeRes.dominant_emotion,
          flag,
        ),
        coachSuggestions: coachRes.suggestions,
        coachChallenge: coachRes.challenge,
      });
    } catch {
      // Keep the previous insights in place when API calls fail.
    } finally {
      setPatternLoading(false);
      setCoachLoading(false);
    }
  }, [entries, user?.id]);

  useEffect(() => {
    if (!loading) fetchPatterns();
  }, [loading, fetchPatterns]);

  const heatmap = buildHeatmap(entries, checkins);
  const timeline = buildTimeline(entries, checkins);

  return {
    heatmap,
    timeline,
    spiralScore,
    patternCards,
    coachSuggestions,
    coachChallenge,
    windowStats,
    anomaly,
    loading,
    patternLoading,
    coachLoading,
    hasData: entries.length > 0 || checkins.length > 0,
  };
}
