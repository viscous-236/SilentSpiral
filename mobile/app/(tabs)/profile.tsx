/**
 * profile.tsx
 * ───────────
 * Profile tab: displays account info, journal/check-in stats,
 * theme toggle, and sign out. All data is read from AuthContext
 * and AsyncStorage (same sources as the rest of the app).
 */

import React, { useCallback, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Ionicons } from "@expo/vector-icons";
import { useFocusEffect } from "expo-router";

import { AtmosphericBackground } from "@/components/atmospheric-background";
import { useAuth } from "@/context/auth-context";
import { useSpiralTheme, type SpiralColorSet } from "@/context/theme-context";
import { SpiralRadius, SpiralSpacing } from "@/constants/theme";
import { loadEntries, loadCheckins } from "@/services/journal-store";

// ── App version (bump manually or source from app.json) ──────────────────────
const APP_VERSION = "1.0.0";

// ─── Screen ──────────────────────────────────────────────────────────────────
export default function ProfileScreen() {
  const { C, isDark, toggleTheme } = useSpiralTheme();
  const { user, signOut } = useAuth();

  const [entryCount, setEntryCount] = useState(0);
  const [checkinCount, setCheckinCount] = useState(0);
  const [statsLoading, setStatsLoading] = useState(true);

  // Reload counts every time screen is focused (same pattern as dashboard fix)
  useFocusEffect(
    useCallback(() => {
      if (!user?.id) {
        setEntryCount(0);
        setCheckinCount(0);
        setStatsLoading(false);
        return;
      }

      setStatsLoading(true);
      Promise.all([loadEntries(user.id), loadCheckins(user.id)])
        .then(([entries, checkins]) => {
          setEntryCount(entries.length);
          setCheckinCount(checkins.length);
        })
        .finally(() => setStatsLoading(false));
    }, [user?.id]),
  );

  const handleSignOut = useCallback(() => {
    Alert.alert(
      "Sign out",
      "Are you sure you want to sign out?",
      [
        { text: "Cancel", style: "cancel" },
        {
          text: "Sign out",
          style: "destructive",
          onPress: async () => {
            await signOut();
          },
        },
      ],
      { cancelable: true },
    );
  }, [signOut]);

  const styles = makeStyles(C);

  return (
    <SafeAreaView style={styles.safe} edges={["top"]}>
      <AtmosphericBackground variant="profile" />
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        showsVerticalScrollIndicator={false}
      >
        {/* ── Header ─────────────────────────────────────────────── */}
        <View style={styles.headerRow}>
          <Text style={styles.pageTitle}>Profile</Text>
          <Pressable onPress={toggleTheme} style={styles.themeToggle} hitSlop={8}>
            <Ionicons
              name={isDark ? "sunny-outline" : "moon-outline"}
              size={20}
              color={C.amber}
            />
          </Pressable>
        </View>

        {/* ── Avatar + identity ────────────────────────────────── */}
        <View style={styles.card}>
          <View style={styles.avatarCircle}>
            <Text style={styles.avatarInitial}>
              {user?.name?.charAt(0).toUpperCase() ?? "?"}
            </Text>
          </View>
          <Text style={styles.userName}>{user?.name ?? "—"}</Text>
          <Text style={styles.userEmail}>{user?.email ?? "—"}</Text>
        </View>

        {/* ── Stats ────────────────────────────────────────────── */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Your journey</Text>
          {statsLoading ? (
            <ActivityIndicator color={C.amber} style={{ marginVertical: SpiralSpacing.md }} />
          ) : (
            <View style={styles.statsRow}>
              <StatItem
                label="Journal entries"
                value={entryCount}
                icon="create-outline"
                color={C.amber}
                C={C}
              />
              <View style={styles.statDivider} />
              <StatItem
                label="Mood check-ins"
                value={checkinCount}
                icon="radio-button-on-outline"
                color={C.teal}
                C={C}
              />
            </View>
          )}
        </View>

        {/* ── Preferences ──────────────────────────────────────── */}
        <View style={styles.card}>
          <Text style={styles.sectionTitle}>Preferences</Text>
          <Pressable
            style={styles.prefRow}
            onPress={toggleTheme}
            android_ripple={{ color: C.violetDim }}
          >
            <Ionicons
              name={isDark ? "moon-outline" : "sunny-outline"}
              size={18}
              color={C.violet}
              style={styles.prefIcon}
            />
            <Text style={styles.prefLabel}>
              {isDark ? "Dark mode" : "Light mode"}
            </Text>
            <Ionicons name="chevron-forward" size={16} color={C.textMuted} />
          </Pressable>
        </View>

        {/* ── Sign out ─────────────────────────────────────────── */}
        <Pressable
          style={({ pressed }) => [styles.signOutBtn, pressed && styles.signOutPressed]}
          onPress={handleSignOut}
        >
          <Ionicons name="log-out-outline" size={18} color="#F87171" />
          <Text style={styles.signOutText}>Sign out</Text>
        </Pressable>

        {/* ── App version ──────────────────────────────────────── */}
        <Text style={styles.versionText}>Silent Spiral v{APP_VERSION}</Text>

        {/* Spacer for floating tab bar */}
        <View style={{ height: 100 }} />
      </ScrollView>
    </SafeAreaView>
  );
}

// ─── StatItem sub-component ──────────────────────────────────────────────────
function StatItem({
  label,
  value,
  icon,
  color,
  C,
}: {
  label: string;
  value: number;
  icon: React.ComponentProps<typeof Ionicons>["name"];
  color: string;
  C: SpiralColorSet;
}) {
  return (
    <View style={statStyles.container}>
      <View style={[statStyles.iconWrap, { backgroundColor: color + "20" }]}>
        <Ionicons name={icon} size={18} color={color} />
      </View>
      <Text style={[statStyles.value, { color: C.textPrimary }]}>{value}</Text>
      <Text style={[statStyles.label, { color: C.textMuted }]}>{label}</Text>
    </View>
  );
}

const statStyles = StyleSheet.create({
  container: { flex: 1, alignItems: "center", gap: 6 },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  value: { fontSize: 28, fontWeight: "700", letterSpacing: -1 },
  label: { fontSize: 11, textAlign: "center", lineHeight: 15 },
});

// ─── Styles ───────────────────────────────────────────────────────────────────
function makeStyles(C: SpiralColorSet) {
  return StyleSheet.create({
    safe: { flex: 1, backgroundColor: C.midnight },
    scroll: { flex: 1 },
    content: { paddingHorizontal: SpiralSpacing.lg, paddingTop: SpiralSpacing.md },

    headerRow: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "space-between",
      marginBottom: SpiralSpacing.lg,
    },
    pageTitle: {
      fontSize: 28,
      fontWeight: "700",
      color: C.textPrimary,
      letterSpacing: -0.5,
    },
    themeToggle: {
      width: 40,
      height: 40,
      borderRadius: SpiralRadius.pill,
      backgroundColor: C.amberDim,
      alignItems: "center",
      justifyContent: "center",
      borderWidth: 1,
      borderColor: C.amber + "44",
    },

    card: {
      backgroundColor: C.surface,
      borderRadius: SpiralRadius.xl,
      borderWidth: 1,
      borderColor: C.border,
      padding: SpiralSpacing.lg,
      marginBottom: SpiralSpacing.md,
      alignItems: "center",
    },

    // Avatar
    avatarCircle: {
      width: 72,
      height: 72,
      borderRadius: 36,
      backgroundColor: C.amberDim,
      borderWidth: 2,
      borderColor: C.amber + "55",
      alignItems: "center",
      justifyContent: "center",
      marginBottom: SpiralSpacing.sm,
    },
    avatarInitial: {
      fontSize: 30,
      fontWeight: "700",
      color: C.amber,
    },
    userName: {
      fontSize: 20,
      fontWeight: "700",
      color: C.textPrimary,
      marginBottom: 2,
    },
    userEmail: {
      fontSize: 13,
      color: C.textMuted,
    },

    // Stats
    sectionTitle: {
      fontSize: 13,
      fontWeight: "600",
      color: C.textMuted,
      textTransform: "uppercase",
      letterSpacing: 0.8,
      alignSelf: "flex-start",
      marginBottom: SpiralSpacing.md,
    },
    statsRow: {
      flexDirection: "row",
      width: "100%",
      alignItems: "center",
    },
    statDivider: {
      width: 1,
      height: 48,
      backgroundColor: C.border,
      marginHorizontal: SpiralSpacing.md,
    },

    // Preferences
    prefRow: {
      flexDirection: "row",
      alignItems: "center",
      width: "100%",
      paddingVertical: SpiralSpacing.xs,
    },
    prefIcon: { marginRight: SpiralSpacing.sm },
    prefLabel: {
      flex: 1,
      fontSize: 15,
      color: C.textPrimary,
    },

    // Sign out
    signOutBtn: {
      flexDirection: "row",
      alignItems: "center",
      justifyContent: "center",
      gap: SpiralSpacing.sm,
      paddingVertical: SpiralSpacing.md,
      borderRadius: SpiralRadius.xl,
      borderWidth: 1,
      borderColor: "#F87171" + "44",
      backgroundColor: "#F8717120",
      marginBottom: SpiralSpacing.md,
    },
    signOutPressed: { opacity: 0.7 },
    signOutText: {
      fontSize: 15,
      fontWeight: "600",
      color: "#F87171",
    },

    versionText: {
      textAlign: "center",
      fontSize: 12,
      color: C.textMuted,
      marginBottom: SpiralSpacing.sm,
    },
  });
}
