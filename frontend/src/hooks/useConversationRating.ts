import { useState, useEffect, useMemo } from 'react';
import { Message } from '@/types/database.types';

/**
 * Parse rating thresholds from environment variable.
 * Format: comma-separated numbers (e.g., "5,10,15,20")
 * Default: [5, 10, 15, 20, 25, 30]
 */
const parseThresholds = (): number[] => {
  const envValue = import.meta.env.VITE_RATING_THRESHOLDS;
  if (envValue && typeof envValue === 'string') {
    const parsed = envValue
      .split(',')
      .map((s: string) => parseInt(s.trim(), 10))
      .filter((n: number) => !isNaN(n) && n > 0);
    if (parsed.length > 0) {
      return parsed;
    }
  }
  return [5, 10, 15, 20, 25, 30];
};

const RATING_THRESHOLDS = parseThresholds();

interface UseConversationRatingResult {
  showRating: boolean;
  currentTraceId: string | undefined;
  handleRatingComplete: () => void;
  handleRatingDismiss: () => void;
}

/**
 * Hook to manage conversation rating popup display.
 * Shows rating popup at configurable message count thresholds.
 */
export function useConversationRating(messages: Message[]): UseConversationRatingResult {
  const [showRating, setShowRating] = useState(false);
  const [dismissedThresholds, setDismissedThresholds] = useState<Set<number>>(new Set());

  // Count AI messages
  const aiMessageCount = useMemo(
    () => messages.filter((m) => m.message.type === 'ai').length,
    [messages]
  );

  // Get trace_id from most recent AI message
  const currentTraceId = useMemo(() => {
    const aiMessages = messages.filter((m) => m.message.type === 'ai');
    return aiMessages[aiMessages.length - 1]?.message.trace_id;
  }, [messages]);

  // Check if we should show rating popup
  useEffect(() => {
    const threshold = RATING_THRESHOLDS.find(
      (t) => aiMessageCount === t && !dismissedThresholds.has(t)
    );

    if (threshold) {
      setShowRating(true);
    }
  }, [aiMessageCount, dismissedThresholds]);

  const handleRatingComplete = () => {
    setShowRating(false);
    setDismissedThresholds((prev) => new Set([...prev, aiMessageCount]));
  };

  const handleRatingDismiss = () => {
    setShowRating(false);
    setDismissedThresholds((prev) => new Set([...prev, aiMessageCount]));
  };

  return {
    showRating,
    currentTraceId,
    handleRatingComplete,
    handleRatingDismiss,
  };
}
