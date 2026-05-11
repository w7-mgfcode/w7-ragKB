import { useState } from 'react';
import { X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { submitScore } from '@/lib/langfuse';

const RATING_OPTIONS = [
  { label: 'Very good', value: 1.0 },
  { label: 'Good', value: 0.67 },
  { label: 'Not so good', value: 0.33 },
  { label: 'Bad', value: 0.0 },
] as const;

interface ConversationRatingProps {
  traceId: string | undefined;
  onComplete: () => void;
  onDismiss: () => void;
}

export function ConversationRating({
  traceId,
  onComplete,
  onDismiss,
}: ConversationRatingProps) {
  const [selectedValue, setSelectedValue] = useState<number | null>(null);
  const [showCommentBox, setShowCommentBox] = useState(false);
  const [comment, setComment] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSelect = (value: number) => {
    setSelectedValue(value);

    // Show comment box only for "Bad" rating
    if (value === 0.0) {
      setShowCommentBox(true);
    } else {
      // Submit immediately for non-bad ratings
      submitRating(value);
    }
  };

  const submitRating = async (value: number, commentText?: string) => {
    if (!traceId) {
      onComplete();
      return;
    }

    setIsSubmitting(true);

    await submitScore({
      traceId,
      name: 'conversation_rating',
      value,
      comment: commentText || undefined,
    });

    setIsSubmitting(false);
    onComplete();
  };

  const handleSubmitBadRating = () => {
    submitRating(0.0, comment.trim() || undefined);
  };

  const handleSkipComment = () => {
    submitRating(0.0);
  };

  return (
    <Card className="w-80 shadow-lg animate-in slide-in-from-bottom-2 duration-200">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium">
            How's this conversation going?
          </CardTitle>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 -mr-2"
            onClick={onDismiss}
            aria-label="Dismiss"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        {!showCommentBox ? (
          <div className="space-y-2">
            {RATING_OPTIONS.map((option) => (
              <Button
                key={option.value}
                variant={selectedValue === option.value ? 'default' : 'outline'}
                className="w-full justify-start"
                onClick={() => handleSelect(option.value)}
                disabled={isSubmitting}
              >
                {option.label}
              </Button>
            ))}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">
              Sorry to hear that. What went wrong? (optional)
            </p>
            <Textarea
              placeholder="Tell us more..."
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
              className="resize-none"
            />
            <div className="flex gap-2">
              <Button
                variant="outline"
                className="flex-1"
                onClick={handleSkipComment}
                disabled={isSubmitting}
              >
                Skip
              </Button>
              <Button
                className="flex-1"
                onClick={handleSubmitBadRating}
                disabled={isSubmitting}
              >
                Submit
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
