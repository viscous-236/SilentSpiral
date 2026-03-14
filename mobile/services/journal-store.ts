/**
 * journal-store.ts
 * ─────────────────
 * Single source of truth for ALL AsyncStorage access in the app.
 *
 * Key registry (every key the app ever touches):
 *   spiral_entries_v2:{uid}               JournalEntry[]
 *   spiral_checkins_v2:{uid}              MoodCheckin[]
 *   spiral_dashboard_insights_v1:{uid}    InsightCachePayload
 *   spiral_storage_migration_v2           migration one-time flag
 *
 * Legacy keys (removed post-migration, kept here for reference):
 *   spiral_entries_v1, spiral_checkins_v1
 *
 * Rule: no other file may import AsyncStorage directly. All reads/writes
 * must go through the typed helpers in this file.
 */

import AsyncStorage from "@react-native-async-storage/async-storage";

// ─── Shared types (re-exported for consumers) ─────────────────────────────────

export interface JournalEntry {
  id: string;
  /** "2026-03-12" — used for heatmap/timeline date bucketing */
  isoDate: string;
  /** "Mar 12" — display label */
  date: string;
  preview: string;
  /** [top_emotion] from /analyze */
  emotions: string[];
  /** Score of top emotion (0–1) from /analyze */
  intensity: number;
  /** Full label→score map from /analyze, converted to {label: score} dict */
  emotionScores: Record<string, number>;
  type: "entry";
}

export interface MoodCheckin {
  id: string;
  /** "2026-03-12" */
  isoDate: string;
  /** "Mar 12" */
  date: string;
  /** Index into MOODS array (0=Low … 4=Great) */
  moodIndex: number;
  moodLabel: string;
  type: "checkin";
}

// ─── Storage keys ─────────────────────────────────────────────────────────────
// All AsyncStorage key constants live here. No other file defines raw keys.

const LEGACY_ENTRIES_KEY = "spiral_entries_v1";
const LEGACY_CHECKINS_KEY = "spiral_checkins_v1";
const ENTRIES_KEY_PREFIX = "spiral_entries_v2";
const CHECKINS_KEY_PREFIX = "spiral_checkins_v2";
const INSIGHT_CACHE_PREFIX = "spiral_dashboard_insights_v1";
const LEGACY_MIGRATION_FLAG = "spiral_storage_migration_v2";

function getEntriesKey(userId: string): string {
  return `${ENTRIES_KEY_PREFIX}:${userId}`;
}

function getCheckinsKey(userId: string): string {
  return `${CHECKINS_KEY_PREFIX}:${userId}`;
}

function getInsightCacheKey(userId: string): string {
  return `${INSIGHT_CACHE_PREFIX}:${userId}`;
}

/**
 * One-time migration helper: assign pre-existing global local data to the
 * first account that logs in after this change, then remove global keys to
 * prevent future cross-account leakage.
 */
export async function migrateLegacyDataToUser(userId: string): Promise<void> {
  try {
    const migrationDone = await AsyncStorage.getItem(LEGACY_MIGRATION_FLAG);
    if (migrationDone) return;

    const [legacyEntriesRaw, legacyCheckinsRaw, scopedEntriesRaw, scopedCheckinsRaw] = await Promise.all([
      AsyncStorage.getItem(LEGACY_ENTRIES_KEY),
      AsyncStorage.getItem(LEGACY_CHECKINS_KEY),
      AsyncStorage.getItem(getEntriesKey(userId)),
      AsyncStorage.getItem(getCheckinsKey(userId)),
    ]);

    if (legacyEntriesRaw && !scopedEntriesRaw) {
      await AsyncStorage.setItem(getEntriesKey(userId), legacyEntriesRaw);
    }
    if (legacyCheckinsRaw && !scopedCheckinsRaw) {
      await AsyncStorage.setItem(getCheckinsKey(userId), legacyCheckinsRaw);
    }

    await AsyncStorage.multiRemove([LEGACY_ENTRIES_KEY, LEGACY_CHECKINS_KEY]);
    await AsyncStorage.setItem(
      LEGACY_MIGRATION_FLAG,
      JSON.stringify({ migratedTo: userId, at: Date.now() }),
    );
  } catch {
    // Migration is best-effort and should never block auth flow.
  }
}

// ─── Journal entries ──────────────────────────────────────────────────────────

export async function loadEntries(userId: string | null | undefined): Promise<JournalEntry[]> {
  if (!userId) return [];
  try {
    const raw = await AsyncStorage.getItem(getEntriesKey(userId));
    return raw ? (JSON.parse(raw) as JournalEntry[]) : [];
  } catch {
    return [];
  }
}

export async function saveEntries(
  entries: JournalEntry[],
  userId: string | null | undefined,
): Promise<void> {
  if (!userId) return;
  await AsyncStorage.setItem(getEntriesKey(userId), JSON.stringify(entries));
}

export async function addEntry(
  entry: JournalEntry,
  userId: string | null | undefined,
): Promise<JournalEntry[]> {
  if (!userId) return [];
  const existing = await loadEntries(userId);
  const next = [entry, ...existing];
  await saveEntries(next, userId);
  return next;
}

/** Update a single entry in-place (e.g. after API returns real emotion) */
export async function updateEntry(
  id: string,
  patch: Partial<JournalEntry>,
  userId: string | null | undefined,
): Promise<void> {
  if (!userId) return;
  const existing = await loadEntries(userId);
  const next = existing.map((e) => (e.id === id ? { ...e, ...patch } : e));
  await saveEntries(next, userId);
}

// ─── Mood check-ins ───────────────────────────────────────────────────────────

export async function loadCheckins(userId: string | null | undefined): Promise<MoodCheckin[]> {
  if (!userId) return [];
  try {
    const raw = await AsyncStorage.getItem(getCheckinsKey(userId));
    return raw ? (JSON.parse(raw) as MoodCheckin[]) : [];
  } catch {
    return [];
  }
}

export async function addCheckin(
  checkin: MoodCheckin,
  userId: string | null | undefined,
): Promise<void> {
  if (!userId) return;
  const existing = await loadCheckins(userId);
  await AsyncStorage.setItem(
    getCheckinsKey(userId),
    JSON.stringify([checkin, ...existing]),
  );
}

// ─── Dashboard insight cache ─────────────────────────────────────────────────
//
// The cache stores the result of expensive pattern/coach API calls so they
// are not re-fetched when the dashboard re-focuses with unchanged data.
// Ownership lives here (not in use-dashboard-data.ts) so logout can clear it.

/**
 * Shape of the cached dashboard payload. Mirrors what use-dashboard-data.ts
 * produces after calling the pattern + coach agents.
 *
 * 'signature' is a deterministic hash of the input entries so stale cache
 * entries are detected and discarded automatically.
 */
export interface InsightCachePayload {
  /** Stringified sorted emotionScores of all valid entries — change detector. */
  signature: string;
  /** ISO date string ("YYYY-MM-DD") the cache was written on. */
  generatedOn: string;
  spiralScore: number;
  windowStats: unknown;       // typed as WindowStats in use-dashboard-data.ts
  anomaly: unknown;           // typed as AnomalyFlag  in use-dashboard-data.ts
  patternCards: unknown[];    // typed as PatternCardData[] in use-dashboard-data.ts
  coachSuggestions: string[];
  coachChallenge: string;
}

/** Read the cached dashboard payload for this user. Returns null on miss or error. */
export async function getDashboardCache(
  userId: string | null | undefined,
): Promise<InsightCachePayload | null> {
  if (!userId) return null;
  try {
    const raw = await AsyncStorage.getItem(getInsightCacheKey(userId));
    return raw ? (JSON.parse(raw) as InsightCachePayload) : null;
  } catch {
    return null;
  }
}

/** Persist the dashboard payload for this user. Silently ignores errors. */
export async function setDashboardCache(
  userId: string | null | undefined,
  payload: InsightCachePayload,
): Promise<void> {
  if (!userId) return;
  try {
    await AsyncStorage.setItem(getInsightCacheKey(userId), JSON.stringify(payload));
  } catch {
    // Cache write failure is non-fatal; stale data will be refreshed next focus.
  }
}

/**
 * Clear ALL user-scoped AsyncStorage data (entries, checkins, insight cache).
 *
 * Call this on logout to prevent cross-account data leakage on shared devices.
 * Poka-Yoke: architecturally impossible to skip if logout flows through auth-context.
 */
export async function clearAllUserData(
  userId: string | null | undefined,
): Promise<void> {
  if (!userId) return;
  try {
    await AsyncStorage.multiRemove([
      getEntriesKey(userId),
      getCheckinsKey(userId),
      getInsightCacheKey(userId),
    ]);
  } catch {
    // Best-effort; if this fails the user is still logged out of SecureStore.
  }
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Convert a Date to "YYYY-MM-DD" for storage / comparison */
export function toIsoDate(d: Date = new Date()): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** Convert a Date to short display label e.g. "Mar 12" */
export function toDisplayDate(d: Date = new Date()): string {
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

/**
 * Map a GoEmotions label (or moodIndex) to one of the 6 display emotions
 * used by MoodCell and EmotionColors.
 */
const JOY_SET = new Set([
  "joy", "love", "admiration", "amusement", "approval", "caring",
  "desire", "excitement", "gratitude", "optimism", "pride", "relief",
]);
const CALM_SET = new Set([
  "calm", "curiosity", "realization", "surprise", "neutral",
]);
const SADNESS_SET = new Set(["sadness", "grief", "disappointment", "remorse"]);
const ANXIETY_SET = new Set(["nervousness", "fear", "confusion"]);
const ANGER_SET = new Set([
  "anger", "disapproval", "disgust", "annoyance", "embarrassment",
]);

export function mapToDisplayEmotion(label: string): string {
  if (JOY_SET.has(label)) return "joy";
  if (CALM_SET.has(label)) return "calm";
  if (SADNESS_SET.has(label)) return "sadness";
  if (ANXIETY_SET.has(label)) return "anxiety";
  if (ANGER_SET.has(label)) return "anger";
  return "neutral";
}

/** Map a mood check-in index (0–4) to the 6 display emotions */
export function moodIndexToEmotion(index: number): string {
  // 0=Low→sadness, 1=Uneasy→anxiety, 2=Neutral→neutral, 3=Good→calm, 4=Great→joy
  return ["sadness", "anxiety", "neutral", "calm", "joy"][index] ?? "neutral";
}
