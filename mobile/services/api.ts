import axios, { AxiosError, AxiosRequestConfig, AxiosResponse } from "axios";
import Constants from "expo-constants";
import { NativeModules, Platform } from "react-native";

function parseHost(candidate?: string): string | null {
  if (!candidate) return null;
  const withoutScheme = candidate.replace(/^[a-z]+:\/\//i, "");
  const host = withoutScheme.split("/")[0]?.split(":")[0]?.trim();
  if (!host || host === "0.0.0.0") return null;
  return host;
}

function buildLocalApiBaseUrlCandidates(): string[] {
  const unique = new Set<string>();
  const addCandidate = (candidate?: string | null) => {
    if (!candidate) return;
    unique.add(candidate.replace(/\/+$/, ""));
  };

  if (__DEV__) {
    const c = Constants as unknown as {
      expoConfig?: { hostUri?: string };
      expoGoConfig?: { debuggerHost?: string };
      manifest2?: { extra?: { expoGo?: { debuggerHost?: string } } };
      manifest?: { debuggerHost?: string };
      linkingUri?: string;
    };

    const hostCandidates = [
      NativeModules?.SourceCode?.scriptURL as string | undefined,
      c.expoConfig?.hostUri,
      c.expoGoConfig?.debuggerHost,
      c.manifest2?.extra?.expoGo?.debuggerHost,
      c.manifest?.debuggerHost,
      c.linkingUri,
    ];

    for (const candidate of hostCandidates) {
      const host = parseHost(candidate);
      if (host) addCandidate(`http://${host}:8000`);
    }
  }

  if (Platform.OS === "android") {
    addCandidate("http://10.0.2.2:8000");
  }
  addCandidate("http://127.0.0.1:8000");
  addCandidate("http://localhost:8000");

  return Array.from(unique);
}

export function getApiBaseUrlCandidates(): string[] {
  return buildLocalApiBaseUrlCandidates();
}

let activeApiBaseUrl = getApiBaseUrlCandidates()[0] ?? "http://127.0.0.1:8000";
export const API_BASE_URL = activeApiBaseUrl;

export function getActiveApiBaseUrl(): string {
  return activeApiBaseUrl;
}

function isNetworkLikeError(error: AxiosError): boolean {
  if (error.response) return false;

  const lower = (error.message ?? "").toLowerCase();
  return (
    error.code === "ECONNABORTED" ||
    lower.includes("network") ||
    lower.includes("timeout") ||
    lower.includes("failed") ||
    lower.includes("cannot")
  );
}

type RetryableConfig = AxiosRequestConfig & {
  __failoverAttempted?: boolean;
};

const rawApi = axios.create({
  timeout: 45_000,
  headers: { Accept: "application/json" },
});

async function retryWithFailover(
  originalConfig: RetryableConfig,
): Promise<AxiosResponse | null> {
  if (originalConfig.__failoverAttempted) return null;
  originalConfig.__failoverAttempted = true;

  const fallbacks = getApiBaseUrlCandidates().filter(
    (url) => url !== activeApiBaseUrl,
  );

  for (const candidate of fallbacks) {
    try {
      const response = await rawApi.request({
        ...originalConfig,
        baseURL: candidate,
      });
      activeApiBaseUrl = candidate;
      console.log(`[API] Failover switched base URL -> ${activeApiBaseUrl}`);
      return response;
    } catch {
      // try next local candidate
    }
  }

  return null;
}

// ─── Startup diagnostic ─────────────────────────────────────────────────────
// Visible in Metro logs for quick diagnosis of routing and network issues.
console.log(`[API] Base URL candidates → ${getApiBaseUrlCandidates().join(", ")}`);
console.log(`[API] Active base URL → ${activeApiBaseUrl}`);

// ─── Axios Instance ─────────────────────────────────────────────────────────
export const api = axios.create({
  baseURL: activeApiBaseUrl,
  timeout: 45_000,
  headers: { Accept: "application/json" },
});

api.interceptors.request.use((config) => {
  config.baseURL = activeApiBaseUrl;

  if (config.data instanceof FormData && config.headers) {
    delete config.headers["Content-Type"];
    delete config.headers["content-type"];
  }
  return config;
});

// Normalize error messages from FastAPI detail fields
api.interceptors.response.use(
  (res) => res,
  async (err: AxiosError) => {
    const config = (err.config ?? {}) as RetryableConfig;

    if (isNetworkLikeError(err)) {
      const recovered = await retryWithFailover(config);
      if (recovered) return recovered;
    }

    const responseData = err.response?.data as
      | { detail?: string | Array<{ msg?: string }>; message?: string }
      | undefined;
    const detail = responseData?.detail;
    const baseMessage =
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail.map((d: { msg?: string }) => d.msg ?? d).join("; ")
          : responseData?.message ?? err.message ?? "Unknown error";

    const message = isNetworkLikeError(err)
      ? `Cannot reach API at ${activeApiBaseUrl}. ${baseMessage}`
      : baseMessage;

    return Promise.reject(new Error(message));
  },
);
