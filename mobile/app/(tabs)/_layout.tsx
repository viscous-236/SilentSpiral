import { Redirect, Tabs } from "expo-router";
import React from "react";
import { Platform } from "react-native";

import { Ionicons } from "@expo/vector-icons";
import { useAuth } from "@/context/auth-context";
import { useSpiralTheme } from "@/context/theme-context";

export default function TabLayout() {
  const { user, isLoading } = useAuth();
  const { C, isDark } = useSpiralTheme();

  if (isLoading) return null;
  if (!user) return <Redirect href="/auth/sign-in" />;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: C.amber,
        tabBarInactiveTintColor: C.textMuted,
        tabBarShowLabel: true,
        tabBarLabelStyle: {
          fontSize: 10,
          fontWeight: "600",
          marginBottom: Platform.OS === "ios" ? 0 : 4,
        },
        tabBarStyle: {
          position: "absolute",
          bottom: 24,
          left: 24,
          right: 24,
          borderRadius: 32,
          backgroundColor: isDark
            ? "rgba(19,25,41,0.96)"
            : "rgba(255,255,255,0.97)",
          borderTopWidth: 0,
          borderWidth: 1,
          borderColor: C.border,
          height: 64,
          elevation: 0,
          shadowColor: "#000",
          shadowOffset: { width: 0, height: 8 },
          shadowOpacity: isDark ? 0.5 : 0.12,
          shadowRadius: 20,
          paddingBottom: 8,
          paddingTop: 8,
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="home-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="journal"
        options={{
          title: "Journal",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="create-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="dashboard"
        options={{
          title: "Insights",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="analytics-outline" size={size} color={color} />
          ),
        }}
      />
      <Tabs.Screen
        name="silent"
        options={{
          title: "Check-in",
          tabBarIcon: ({ color, size }) => (
            <Ionicons
              name="radio-button-on-outline"
              size={size}
              color={color}
            />
          ),
        }}
      />
      <Tabs.Screen
        name="guide"
        options={{
          href: null,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: "Profile",
          tabBarIcon: ({ color, size }) => (
            <Ionicons name="person-circle-outline" size={size} color={color} />
          ),
        }}
      />
      {/* Hide legacy explore tab */}
      <Tabs.Screen name="explore" options={{ href: null }} />
    </Tabs>
  );
}
