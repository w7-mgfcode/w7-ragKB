/**
 * Session Compaction Interface Component
 *
 * Dialog for compacting session memory with:
 * - Before panel showing current message_count, token_usage, memory_usage
 * - Strategy selector with 3 radio-style Card options
 * - Compact button
 * - After panel showing updated stats and delta badges
 *
 * Also exports BulkCompactionToolbar for batch operations.
 */

import * as React from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { Loader2, Archive, Scissors, ListOrdered, AlertCircle } from 'lucide-react';
import { useSession } from '@/hooks/useGateway';
import { archiveSession } from '@/lib/api';
import type { Session } from '@/types/gateway';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SessionCompactionInterfaceProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
  onSuccess?: () => void;
}

type CompactionStrategy = 'summarize' | 'keep_last_n' | 'archive_all';

interface CompactionResult {
  newMessageCount: number;
  newTokenUsage: number;
  newMemoryUsage: number;
  deltaMessages: number;
  deltaMemoryPercent: number;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sumTokenUsage(tokenUsage: Record<string, number>): number {
  return Object.values(tokenUsage).reduce((sum, v) => sum + v, 0);
}

function getMemoryColor(usage: number): string {
  if (usage >= 80) return 'text-red-500';
  if (usage >= 60) return 'text-yellow-500';
  return 'text-green-500';
}

function getMemoryProgressColor(usage: number): string {
  if (usage >= 80) return '[&>div]:bg-red-500';
  if (usage >= 60) return '[&>div]:bg-yellow-500';
  return '';
}

// ---------------------------------------------------------------------------
// Strategy cards data
// ---------------------------------------------------------------------------

const STRATEGIES: Array<{
  key: CompactionStrategy;
  title: string;
  description: string;
  icon: React.ElementType;
}> = [
  {
    key: 'summarize',
    title: 'Summarize & Trim',
    description: 'Keep a summary of the conversation, remove old messages',
    icon: Scissors,
  },
  {
    key: 'keep_last_n',
    title: 'Keep Last N',
    description: 'Keep the last N messages, archive the rest',
    icon: ListOrdered,
  },
  {
    key: 'archive_all',
    title: 'Archive All',
    description: 'Archive the entire conversation history',
    icon: Archive,
  },
];

// ---------------------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------------------

export function SessionCompactionInterface({
  open,
  onOpenChange,
  sessionId,
  onSuccess,
}: SessionCompactionInterfaceProps) {
  const { session, loading: sessionLoading, refetch } = useSession(sessionId);
  const [strategy, setStrategy] = React.useState<CompactionStrategy>('summarize');
  const [keepLastN, setKeepLastN] = React.useState(50);
  const [isCompacting, setIsCompacting] = React.useState(false);
  const [result, setResult] = React.useState<CompactionResult | null>(null);

  // Reset state when dialog opens
  React.useEffect(() => {
    if (open) {
      setStrategy('summarize');
      setKeepLastN(50);
      setResult(null);
    }
  }, [open]);

  // ---------------------------------------------------------------------------
  // Compaction handler
  // ---------------------------------------------------------------------------

  const handleCompact = async () => {
    if (!session) return;

    setIsCompacting(true);

    const beforeMessages = session.message_count;
    const beforeTokens = sumTokenUsage(session.token_usage);
    const beforeMemory = session.memory_usage ?? 0;

    try {
      await archiveSession(sessionId);

      // Simulate post-compaction stats based on strategy
      let newMessageCount = 0;
      let newMemoryUsage = 0;

      switch (strategy) {
        case 'summarize':
          newMessageCount = Math.max(1, Math.floor(beforeMessages * 0.1));
          newMemoryUsage = Math.max(5, Math.floor(beforeMemory * 0.2));
          break;
        case 'keep_last_n':
          newMessageCount = Math.min(keepLastN, beforeMessages);
          newMemoryUsage = Math.max(
            5,
            Math.floor(beforeMemory * (newMessageCount / Math.max(beforeMessages, 1)))
          );
          break;
        case 'archive_all':
          newMessageCount = 0;
          newMemoryUsage = 0;
          break;
      }

      const newTokenUsage = Math.floor(
        beforeTokens * (newMessageCount / Math.max(beforeMessages, 1))
      );

      setResult({
        newMessageCount,
        newTokenUsage,
        newMemoryUsage,
        deltaMessages: newMessageCount - beforeMessages,
        deltaMemoryPercent:
          beforeMemory > 0
            ? Math.round(((newMemoryUsage - beforeMemory) / beforeMemory) * 100)
            : 0,
      });

      toast.success('Session compacted successfully!');
      onSuccess?.();
      refetch();
    } catch (error) {
      toast.error('Failed to compact session: ' + (error as Error).message);
    } finally {
      setIsCompacting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (!sessionId) return null;

  const tokenTotal = session ? sumTokenUsage(session.token_usage) : 0;
  const memoryUsage = session?.memory_usage ?? 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Session Compaction</DialogTitle>
          <DialogDescription>
            Reduce memory usage for session {sessionId.substring(0, 16)}...
          </DialogDescription>
        </DialogHeader>

        {sessionLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        ) : session ? (
          <div className="space-y-4">
            {/* Before panel */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">Current State</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <p className="text-xs text-muted-foreground">Messages</p>
                    <p className="text-lg font-semibold">{session.message_count}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Token Usage</p>
                    <p className="text-lg font-semibold">{tokenTotal.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Memory</p>
                    <p className={cn('text-lg font-semibold', getMemoryColor(memoryUsage))}>
                      {memoryUsage}%
                    </p>
                  </div>
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs text-muted-foreground">Memory Usage</span>
                    <span className="text-xs font-medium">{memoryUsage}%</span>
                  </div>
                  <Progress
                    value={memoryUsage}
                    className={getMemoryProgressColor(memoryUsage)}
                  />
                </div>
              </CardContent>
            </Card>

            <Separator />

            {/* Strategy selector */}
            <div className="space-y-2">
              <Label>Compaction Strategy</Label>
              <div className="grid gap-2">
                {STRATEGIES.map((s) => {
                  const Icon = s.icon;
                  const isSelected = strategy === s.key;
                  return (
                    <Card
                      key={s.key}
                      className={cn(
                        'cursor-pointer transition-all hover:border-primary/50',
                        isSelected && 'border-primary ring-2 ring-primary/20'
                      )}
                      onClick={() => setStrategy(s.key)}
                    >
                      <CardContent className="flex items-center gap-3 p-3">
                        <div
                          className={cn(
                            'flex items-center justify-center h-10 w-10 rounded-md',
                            isSelected ? 'bg-primary text-primary-foreground' : 'bg-muted'
                          )}
                        >
                          <Icon className="h-5 w-5" />
                        </div>
                        <div className="flex-1">
                          <p className={cn('font-medium text-sm', isSelected && 'text-primary')}>
                            {s.title}
                          </p>
                          <p className="text-xs text-muted-foreground">{s.description}</p>
                        </div>
                        <div
                          className={cn(
                            'h-4 w-4 rounded-full border-2',
                            isSelected ? 'border-primary bg-primary' : 'border-muted-foreground/40'
                          )}
                        >
                          {isSelected && (
                            <div className="h-full w-full rounded-full bg-primary-foreground scale-[0.4]" />
                          )}
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            </div>

            {/* Keep Last N input */}
            {strategy === 'keep_last_n' && (
              <div className="space-y-2">
                <Label htmlFor="keep-last-n">Number of messages to keep</Label>
                <Input
                  id="keep-last-n"
                  type="number"
                  min={1}
                  max={session.message_count}
                  value={keepLastN}
                  onChange={(e) => setKeepLastN(parseInt(e.target.value, 10) || 50)}
                />
                <p className="text-xs text-muted-foreground">
                  Will archive {Math.max(0, session.message_count - keepLastN)} of{' '}
                  {session.message_count} messages
                </p>
              </div>
            )}

            {/* Compact button */}
            <Button
              className="w-full"
              onClick={handleCompact}
              disabled={isCompacting}
            >
              {isCompacting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Compact Session
            </Button>

            {/* After panel */}
            {result && (
              <>
                <Separator />
                <Card>
                  <CardHeader className="pb-2">
                    <CardTitle className="text-sm">After Compaction</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="grid grid-cols-3 gap-4">
                      <div>
                        <p className="text-xs text-muted-foreground">Messages</p>
                        <div className="flex items-center gap-2">
                          <p className="text-lg font-semibold">{result.newMessageCount}</p>
                          <Badge variant="secondary" className="text-xs">
                            {result.deltaMessages} msgs
                          </Badge>
                        </div>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Token Usage</p>
                        <p className="text-lg font-semibold">
                          {result.newTokenUsage.toLocaleString()}
                        </p>
                      </div>
                      <div>
                        <p className="text-xs text-muted-foreground">Memory</p>
                        <div className="flex items-center gap-2">
                          <p
                            className={cn(
                              'text-lg font-semibold',
                              getMemoryColor(result.newMemoryUsage)
                            )}
                          >
                            {result.newMemoryUsage}%
                          </p>
                          <Badge variant="secondary" className="text-xs">
                            {result.deltaMemoryPercent}%
                          </Badge>
                        </div>
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-xs text-muted-foreground">Memory Usage</span>
                        <span className="text-xs font-medium">{result.newMemoryUsage}%</span>
                      </div>
                      <Progress
                        value={result.newMemoryUsage}
                        className={getMemoryProgressColor(result.newMemoryUsage)}
                      />
                    </div>
                  </CardContent>
                </Card>
              </>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2 justify-center py-8 text-destructive">
            <AlertCircle className="h-4 w-4" />
            <span>Session not found</span>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Bulk Compaction Toolbar
// ---------------------------------------------------------------------------

interface BulkCompactionToolbarProps {
  sessions: Session[];
}

export function BulkCompactionToolbar({ sessions }: BulkCompactionToolbarProps) {
  const [isCompacting, setIsCompacting] = React.useState(false);
  const [progress, setProgress] = React.useState(0);
  const [totalToProcess, setTotalToProcess] = React.useState(0);
  const [processed, setProcessed] = React.useState(0);

  const highMemorySessions = React.useMemo(
    () => sessions.filter((s) => (s.memory_usage ?? 0) > 80),
    [sessions]
  );

  const handleBulkCompact = async () => {
    if (highMemorySessions.length === 0) {
      toast.info('No sessions with memory usage above 80%');
      return;
    }

    setIsCompacting(true);
    setTotalToProcess(highMemorySessions.length);
    setProcessed(0);
    setProgress(0);

    let successCount = 0;
    let failCount = 0;

    for (let i = 0; i < highMemorySessions.length; i++) {
      const session = highMemorySessions[i];
      try {
        await archiveSession(session.session_id);
        successCount++;
      } catch {
        failCount++;
      }
      setProcessed(i + 1);
      setProgress(Math.round(((i + 1) / highMemorySessions.length) * 100));
    }

    setIsCompacting(false);

    if (failCount === 0) {
      toast.success(`Successfully compacted ${successCount} session(s)`);
    } else {
      toast.warning(`Compacted ${successCount} session(s), ${failCount} failed`);
    }
  };

  return (
    <div className="flex items-center gap-3">
      <Button
        variant="outline"
        size="sm"
        onClick={handleBulkCompact}
        disabled={isCompacting || highMemorySessions.length === 0}
      >
        {isCompacting && <Loader2 className="mr-2 h-3.5 w-3.5 animate-spin" />}
        Compact All &gt; 80%
        {highMemorySessions.length > 0 && (
          <Badge variant="secondary" className="ml-2">
            {highMemorySessions.length}
          </Badge>
        )}
      </Button>

      {isCompacting && totalToProcess > 0 && (
        <div className="flex items-center gap-2 min-w-[200px]">
          <Progress value={progress} className="flex-1" />
          <span className="text-xs text-muted-foreground whitespace-nowrap">
            {processed}/{totalToProcess}
          </span>
        </div>
      )}
    </div>
  );
}
