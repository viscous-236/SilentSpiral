import { useState } from "react";
import {
  getReflection,
  type ReflectRequest,
} from "@/services/agent-service";

export function useReflection() {
  const [questions, setQuestions] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function fetchReflection(req: ReflectRequest): Promise<string[] | null> {
    setLoading(true);
    setError(null);
    try {
      const res = await getReflection(req);
      setQuestions(res.questions);
      return res.questions;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reflection failed");
      return null;
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setQuestions([]);
    setError(null);
  }

  return { fetchReflection, questions, loading, error, reset };
}
