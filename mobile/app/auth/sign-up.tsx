import React, { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { Link } from "expo-router";
import Animated, { FadeInDown } from "react-native-reanimated";

import { useAuth } from "@/context/auth-context";
import { useSpiralTheme } from "@/context/theme-context";
import { SpiralRadius, SpiralSpacing } from "@/constants/theme";

export default function SignUpScreen() {
  const { signUp } = useAuth();
  const { C } = useSpiralTheme();

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSignUp = async () => {
    setError("");
    setLoading(true);
    const result = await signUp(name, email, password);
    setLoading(false);
    if (result.error) {
      setError(result.error);
    }
  };

  return (
    <SafeAreaView
      style={[styles.safe, { backgroundColor: C.midnight }]}
      edges={["top", "bottom"]}
    >
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : "height"}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* ── Brand mark ───────────────────────────────────────────────── */}
          <Animated.View entering={FadeInDown.springify()} style={styles.brand}>
            <View style={[styles.brandDot, { backgroundColor: C.amber }]} />
            <Text style={[styles.brandName, { color: C.textPrimary }]}>
              Reflectra
            </Text>
          </Animated.View>

          {/* ── Heading ─────────────────────────────────────────────────── */}
          <Animated.View
            entering={FadeInDown.delay(80).springify()}
            style={styles.header}
          >
            <Text style={[styles.title, { color: C.textPrimary }]}>
              Start here
            </Text>
            <Text style={[styles.subtitle, { color: C.textSecondary }]}>
              Create your space. Write without limits.
            </Text>
          </Animated.View>

          {/* ── Form ────────────────────────────────────────────────────── */}
          <Animated.View
            entering={FadeInDown.delay(160).springify()}
            style={[
              styles.form,
              { backgroundColor: C.surface, borderColor: C.border },
            ]}
          >
            <TextInput
              style={[
                styles.input,
                { color: C.textPrimary, borderColor: C.border, backgroundColor: C.midnight },
              ]}
              placeholder="Your name"
              placeholderTextColor={C.textMuted}
              value={name}
              onChangeText={setName}
              autoCapitalize="words"
              returnKeyType="next"
            />
            <TextInput
              style={[
                styles.input,
                { color: C.textPrimary, borderColor: C.border, backgroundColor: C.midnight },
              ]}
              placeholder="Email"
              placeholderTextColor={C.textMuted}
              value={email}
              onChangeText={setEmail}
              keyboardType="email-address"
              autoCapitalize="none"
              autoComplete="email"
              returnKeyType="next"
            />
            <TextInput
              style={[
                styles.input,
                { color: C.textPrimary, borderColor: C.border, backgroundColor: C.midnight },
              ]}
              placeholder="Password (min. 6 characters)"
              placeholderTextColor={C.textMuted}
              value={password}
              onChangeText={setPassword}
              secureTextEntry
              returnKeyType="done"
              onSubmitEditing={handleSignUp}
            />
            {!!error && <Text style={styles.errorText}>{error}</Text>}
          </Animated.View>

          {/* ── CTA ─────────────────────────────────────────────────────── */}
          <Animated.View entering={FadeInDown.delay(240).springify()}>
            <Pressable
              onPress={handleSignUp}
              disabled={loading}
              style={({ pressed }) => [
                styles.button,
                {
                  backgroundColor: C.amber,
                  opacity: pressed || loading ? 0.75 : 1,
                },
              ]}
            >
              <Text style={[styles.buttonText, { color: C.midnight }]}>
                {loading ? "Creating account…" : "Create Account"}
              </Text>
            </Pressable>

            <View style={styles.footer}>
              <Text style={[styles.footerText, { color: C.textMuted }]}>
                Already have an account?{"  "}
              </Text>
              <Link href={"/auth/sign-in" as never} asChild>
                <Pressable>
                  <Text style={[styles.link, { color: C.amber }]}>Sign In</Text>
                </Pressable>
              </Link>
            </View>
          </Animated.View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1 },
  flex: { flex: 1 },
  scroll: {
    flexGrow: 1,
    justifyContent: "center",
    padding: SpiralSpacing.xl,
  },
  brand: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    marginBottom: SpiralSpacing.xxl,
  },
  brandDot: { width: 10, height: 10, borderRadius: 5 },
  brandName: { fontSize: 15, fontWeight: "700", letterSpacing: 0.5 },
  header: { marginBottom: SpiralSpacing.xl },
  title: {
    fontSize: 34,
    fontWeight: "700",
    letterSpacing: -0.8,
    marginBottom: 8,
  },
  subtitle: { fontSize: 16, lineHeight: 24 },
  form: {
    borderRadius: SpiralRadius.lg,
    borderWidth: 1,
    padding: SpiralSpacing.md,
    gap: SpiralSpacing.sm,
    marginBottom: SpiralSpacing.lg,
  },
  input: {
    borderWidth: 1,
    borderRadius: SpiralRadius.md,
    paddingHorizontal: SpiralSpacing.md,
    paddingVertical: 14,
    fontSize: 16,
  },
  errorText: { color: "#F87171", fontSize: 13, paddingHorizontal: 4 },
  button: {
    height: 54,
    borderRadius: SpiralRadius.pill,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: SpiralSpacing.lg,
  },
  buttonText: { fontSize: 16, fontWeight: "700", letterSpacing: 0.3 },
  footer: {
    flexDirection: "row",
    justifyContent: "center",
    alignItems: "center",
  },
  footerText: { fontSize: 14 },
  link: { fontSize: 14, fontWeight: "700" },
});
