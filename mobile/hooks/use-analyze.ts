import { useState } from "react";
import { analyzeText, type AnalyzeResult } from "@/services/emotion-service";

type AnalyzeOutcome = {
  result: AnalyzeResult | null;
  errorMessage: string | null;
};

export function useAnalyze() {
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyze(text: string): Promise<AnalyzeOutcome> {
    setLoading(true);
    setError(null);
    try {
      const res = await analyzeText({ text });
      setResult(res);
      return { result: res, errorMessage: null };
    } catch (e) {
      const message = e instanceof Error ? e.message : "Analysis failed";
      setError(message);
      return { result: null, errorMessage: message };
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setResult(null);
    setError(null);
  }

  return { analyze, result, loading, error, reset };
}
