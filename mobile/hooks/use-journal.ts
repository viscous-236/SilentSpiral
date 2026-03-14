import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/context/auth-context";
import {
  addEntry as persistAddEntry,
  loadEntries,
  updateEntry as persistUpdateEntry,
  type JournalEntry,
} from "@/services/journal-store";

export function useJournal() {
  const { user } = useAuth();
  const [entries, setEntries] = useState<JournalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  // Load persisted entries for the active user
  useEffect(() => {
    let isMounted = true;

    if (!user?.id) {
      setEntries([]);
      setLoading(false);
      return () => {
        isMounted = false;
      };
    }

    setLoading(true);
    loadEntries(user.id)
      .then((data) => {
        if (isMounted) setEntries(data);
      })
      .finally(() => {
        if (isMounted) setLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [user?.id]);

  /** Prepend a new entry and persist to AsyncStorage */
  const addEntry = useCallback(async (entry: JournalEntry) => {
    const next = await persistAddEntry(entry, user?.id);
    setEntries(next);
  }, [user?.id]);

  /** Patch a single entry (e.g. update emotions after API returns real data) */
  const updateEntry = useCallback(
    async (id: string, patch: Partial<JournalEntry>) => {
      await persistUpdateEntry(id, patch, user?.id);
      setEntries((prev) =>
        prev.map((e) => (e.id === id ? { ...e, ...patch } : e)),
      );
    },
    [user?.id],
  );

  return { entries, addEntry, updateEntry, loading };
}
