import { getActiveApiBaseUrl } from "./api";

export type VoiceLocale = "en-US" | "hi-IN";

export interface TranscribeResponse {
  text: string;
  locale: VoiceLocale;
}

const TRANSCRIBE_TIMEOUT_MS = 45_000;

function inferAudioMeta(uri: string): { name: string; type: string } {
  const clean = uri.split("?")[0].toLowerCase();
  const fileExt = clean.includes(".") ? clean.split(".").pop() : undefined;
  const ext = fileExt || "m4a";

  const mimeByExt: Record<string, string> = {
    m4a: "audio/m4a",
    mp4: "audio/mp4",
    caf: "audio/x-caf",
    wav: "audio/wav",
    mp3: "audio/mpeg",
    aac: "audio/aac",
    webm: "audio/webm",
    ogg: "audio/ogg",
  };

  const safeExt = mimeByExt[ext] ? ext : "m4a";
  return {
    name: `voice-${Date.now()}.${safeExt}`,
    type: mimeByExt[safeExt],
  };
}

export async function transcribeAudioUri(
  audioUri: string,
  locale: VoiceLocale,
): Promise<TranscribeResponse> {
  const meta = inferAudioMeta(audioUri);

  const baseCandidates = [getActiveApiBaseUrl()];

  let lastError = "Unknown error";

  for (const base of baseCandidates) {
    const endpoint = `${base.replace(/\/$/, "")}/transcribe`;
    const form = new FormData();
    form.append("locale", locale);
    form.append("audio", {
      uri: audioUri,
      name: meta.name,
      type: meta.type,
    } as any);

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), TRANSCRIBE_TIMEOUT_MS);

    try {
      const res = await fetch(endpoint, {
        method: "POST",
        body: form,
        headers: { Accept: "application/json" },
        signal: controller.signal,
      });

      const raw = await res.text();
      const json = raw ? JSON.parse(raw) as Partial<TranscribeResponse> & { detail?: unknown } : {};

      if (!res.ok) {
        const detail = typeof json.detail === "string"
          ? json.detail
          : `HTTP ${res.status}`;
        throw new Error(detail);
      }

      const text = typeof json.text === "string" ? json.text : "";
      const outLocale = (json.locale === "hi-IN" ? "hi-IN" : "en-US") as VoiceLocale;
      return { text, locale: outLocale };
    } catch (err) {
      lastError = err instanceof Error ? err.message : "Unknown error";
      const lowered = lastError.toLowerCase();
      const isNetworkish =
        lowered.includes("network")
        || lowered.includes("failed to fetch")
        || lowered.includes("timeout")
        || lowered.includes("aborted")
        || lowered.includes("load failed");

      if (!isNetworkish) throw new Error(lastError);
    } finally {
      clearTimeout(timer);
    }
  }

  throw new Error(`Network error: cannot reach ${baseCandidates[0]}/transcribe`);
}
