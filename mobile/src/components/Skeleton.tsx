import { View } from "react-native";

/**
 * Static placeholder blocks while loading. No animation: cheapest possible on low-end Android
 * and nothing to disable for "reduce motion".
 */
export function Skeleton({ className = "" }: { className?: string }) {
  return <View className={`rounded-sm bg-surface-muted ${className}`} />;
}

/** A card-shaped skeleton with a few lines, announced as loading to screen readers. */
export function SkeletonCard({ lines = 3, label }: { lines?: number; label: string }) {
  return (
    <View
      className="gap-3 rounded-lg border border-surface-line bg-surface-card p-4"
      accessible
      accessibilityLabel={label}
      accessibilityRole="progressbar"
      testID="skeleton"
    >
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-8 w-2/3" />
      {Array.from({ length: Math.max(0, lines - 2) }).map((_, i) => (
        <Skeleton key={i} className="h-4 w-full" />
      ))}
    </View>
  );
}
