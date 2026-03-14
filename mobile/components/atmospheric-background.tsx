import React, { useMemo } from "react";
import { StyleSheet, View } from "react-native";

import { useSpiralTheme } from "@/context/theme-context";

type AtmosphereVariant = "journal" | "insights" | "silent" | "profile";

interface AtmosphericBackgroundProps {
  variant?: AtmosphereVariant;
}

interface BlobPreset {
  top?: number;
  bottom?: number;
  left?: number;
  right?: number;
  size: number;
  color: string;
  opacity?: number;
}

function getPresets(variant: AtmosphereVariant): BlobPreset[] {
  switch (variant) {
    case "journal":
      return [
        { top: -90, right: -60, size: 240, color: "amber", opacity: 0.9 },
        { top: 180, left: -110, size: 280, color: "violet", opacity: 0.75 },
        { bottom: -140, right: -80, size: 300, color: "teal", opacity: 0.7 },
      ];
    case "insights":
      return [
        { top: -80, left: -70, size: 250, color: "teal", opacity: 0.8 },
        { top: 140, right: -120, size: 290, color: "violet", opacity: 0.65 },
        { bottom: -120, left: -100, size: 260, color: "amber", opacity: 0.85 },
      ];
    case "silent":
      return [
        { top: -110, right: -90, size: 260, color: "violet", opacity: 0.8 },
        { top: 210, left: -130, size: 320, color: "teal", opacity: 0.7 },
        { bottom: -150, right: -120, size: 330, color: "amber", opacity: 0.65 },
      ];
    case "profile":
    default:
      return [
        { top: -100, left: -90, size: 220, color: "amber", opacity: 0.75 },
        { top: 210, right: -90, size: 250, color: "teal", opacity: 0.65 },
        { bottom: -130, left: -120, size: 300, color: "violet", opacity: 0.6 },
      ];
  }
}

export function AtmosphericBackground({
  variant = "journal",
}: AtmosphericBackgroundProps) {
  const { C } = useSpiralTheme();

  const blobs = useMemo(() => {
    const palette = {
      amber: C.amberDim,
      violet: C.violetDim,
      teal: C.tealDim,
    } as const;

    return getPresets(variant).map((preset) => ({
      ...preset,
      colorValue: palette[preset.color as keyof typeof palette],
    }));
  }, [C, variant]);

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      {blobs.map((blob, idx) => (
        <View
          key={`${variant}-${idx}`}
          style={[
            styles.blob,
            {
              top: blob.top,
              bottom: blob.bottom,
              left: blob.left,
              right: blob.right,
              width: blob.size,
              height: blob.size,
              borderRadius: blob.size / 2,
              backgroundColor: blob.colorValue,
              opacity: blob.opacity ?? 0.75,
            },
          ]}
        />
      ))}
      <View style={[styles.scrim, { backgroundColor: C.midnight }]} />
    </View>
  );
}

const styles = StyleSheet.create({
  blob: {
    position: "absolute",
  },
  scrim: {
    ...StyleSheet.absoluteFillObject,
    opacity: 0.82,
  },
});
