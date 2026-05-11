import { useState } from 'react';
import { ThumbsUp, ThumbsDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { submitScore } from '@/lib/langfuse';
import { cn } from '@/lib/utils';

interface FeedbackWidgetProps {
  traceId: string | undefined;
  className?: string;
}

export function FeedbackWidget({ traceId, className }: FeedbackWidgetProps) {
  const [submitted, setSubmitted] = useState(false);
  const [selectedValue, setSelectedValue] = useState<1 | 0 | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Don't render if no trace_id (graceful degradation)
  if (!traceId) {
    return null;
  }

  const handleFeedback = async (isPositive: boolean) => {
    if (isSubmitting || submitted) return;

    const value = isPositive ? 1 : 0;
    setSelectedValue(value as 1 | 0);
    setIsSubmitting(true);

    // Fire-and-forget - don't block UI
    submitScore({
      traceId,
      name: 'message_feedback',
      value,
    }).finally(() => {
      setIsSubmitting(false);
      setSubmitted(true);
    });
  };

  if (submitted) {
    return (
      <span className={cn('text-xs text-muted-foreground', className)}>
        {selectedValue === 1 ? 'Thanks!' : 'Thanks for the feedback'}
      </span>
    );
  }

  return (
    <div
      className={cn(
        'flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity',
        className
      )}
    >
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        onClick={() => handleFeedback(true)}
        disabled={isSubmitting}
        aria-label="Thumbs up"
      >
        <ThumbsUp className="h-3 w-3" />
      </Button>
      <Button
        variant="ghost"
        size="icon"
        className="h-6 w-6"
        onClick={() => handleFeedback(false)}
        disabled={isSubmitting}
        aria-label="Thumbs down"
      >
        <ThumbsDown className="h-3 w-3" />
      </Button>
    </div>
  );
}
