import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import * as SecureStore from 'expo-secure-store';
import { api } from '@/services/api';
import { migrateLegacyDataToUser, clearAllUserData } from '@/services/journal-store';

// ─── Types ────────────────────────────────────────────────────────────────────
export type User = {
  id: string;
  email: string;
  name: string;
};

type AuthResult = { error?: string };

type AuthContextType = {
  user: User | null;
  isLoading: boolean;
  signIn: (email: string, password: string) => Promise<AuthResult>;
  signUp: (name: string, email: string, password: string) => Promise<AuthResult>;
  signOut: () => Promise<void>;
};

// ─── Context ──────────────────────────────────────────────────────────────────
const AuthContext = createContext<AuthContextType>({
  user: null,
  isLoading: true,
  signIn: async () => ({}),
  signUp: async () => ({}),
  signOut: async () => {},
});

const SESSION_KEY = 'spiral_session_v1';

// ─── Provider ─────────────────────────────────────────────────────────────────
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore persisted session on mount
  useEffect(() => {
    (async () => {
      try {
        const raw = await SecureStore.getItemAsync(SESSION_KEY);
        if (raw) {
          try {
            const restoredUser = JSON.parse(raw) as User;
            setUser(restoredUser);
            await migrateLegacyDataToUser(restoredUser.id);
          } catch {
            // corrupted — ignore
          }
        }
      } catch {
        // ignore secure store read failures
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const signIn = useCallback(async (email: string, password: string): Promise<AuthResult> => {
    const trimEmail = email.trim().toLowerCase();
    if (!trimEmail.includes('@')) return { error: 'Enter a valid email address.' };
    if (password.length < 6) return { error: 'Password must be at least 6 characters.' };

    try {
      const { data } = await api.post<User>('/auth/login', {
        email: trimEmail,
        password,
      });
      await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(data));
      await migrateLegacyDataToUser(data.id);
      setUser(data);
      return {};
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Sign in failed.';
      return { error: msg };
    }
  }, []);

  const signUp = useCallback(
    async (name: string, email: string, password: string): Promise<AuthResult> => {
      const trimName = name.trim();
      const trimEmail = email.trim().toLowerCase();
      if (!trimName) return { error: 'Name is required.' };
      if (!trimEmail.includes('@')) return { error: 'Enter a valid email address.' };
      if (password.length < 6) return { error: 'Password must be at least 6 characters.' };

      try {
        const { data } = await api.post<User>('/auth/register', {
          name: trimName,
          email: trimEmail,
          password,
        });
        await SecureStore.setItemAsync(SESSION_KEY, JSON.stringify(data));
        await migrateLegacyDataToUser(data.id);
        setUser(data);
        return {};
      } catch (e) {
        const msg = e instanceof Error ? e.message : 'Sign up failed.';
        return { error: msg };
      }
    },
    [],
  );

  const signOut = useCallback(async () => {
    // Capture id before clearing user state
    const userId = user?.id;
    await SecureStore.deleteItemAsync(SESSION_KEY);
    setUser(null);
    // Poka-Yoke: clear ALL AsyncStorage data so the next user on this device
    // starts with an empty slate. Runs after setUser(null) so no UI flash.
    await clearAllUserData(userId);
  }, [user?.id]);

  return (
    <AuthContext.Provider value={{ user, isLoading, signIn, signUp, signOut }}>
      {children}
    </AuthContext.Provider>
  );
}

// ─── Hook ─────────────────────────────────────────────────────────────────────
export function useAuth() {
  return useContext(AuthContext);
}
