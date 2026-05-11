import { useState, useMemo } from 'react';
import { useSession } from '@/hooks/useGateway';
import { SessionType, ActivationMode } from '@/types/gateway';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from '@/components/ui/hover-card';
import { Separator } from '@/components/ui/separator';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';

interface SessionIndicatorProps {
  sessionId: string | null;
  channelId?: string | null;
}

const sessionTypeBadgeVariant = (type: SessionType) => {
  switch (type) {
    case SessionType.MAIN:
      return 'default' as const;
    case SessionType.GROUP:
      return 'secondary' as const;
    case SessionType.WEBHOOK:
      return 'outline' as const;
  }
};

/**
 * Returns idle time in minutes from last_activity_at to now.
 */
const getIdleMinutes = (lastActivity: string): number => {
  const lastMs = new Date(lastActivity).getTime();
  const nowMs = Date.now();
  return (nowMs - lastMs) / (1000 * 60);
};

/**
 * Returns the health dot color class based on idle time.
 * Green: normal, Yellow: > 30min idle, Red: > 50min approaching 60min archive.
 */
const getHealthColor = (idleMinutes: number): string => {
  if (idleMinutes > 50) return 'bg-red-500';
  if (idleMinutes > 30) return 'bg-yellow-500';
  return 'bg-green-500';
};

export const SessionIndicator = ({
  sessionId,
  channelId,
}: SessionIndicatorProps) => {
  const { session, loading } = useSession(sessionId);
  const [copied, setCopied] = useState(false);

  const idleMinutes = useMemo(() => {
    if (!session) return 0;
    return getIdleMinutes(session.last_activity_at);
  }, [session]);

  const healthColor = useMemo(() => getHealthColor(idleMinutes), [idleMinutes]);

  const handleCopySessionId = () => {
    if (!session) return;
    navigator.clipboard.writeText(session.session_id);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  if (!sessionId) {
    return (
      <div className="flex items-center h-8 px-3 text-xs text-muted-foreground">
        No active session
      </div>
    );
  }

  if (loading || !session) {
    return (
      <div className="flex items-center h-8 px-3 text-xs text-muted-foreground">
        Loading session...
      </div>
    );
  }

  const truncatedId = session.session_id.slice(0, 8) + '...';
  const showMemoryBar =
    session.memory_usage !== undefined && session.memory_usage > 50;

  return (
    <div className="flex items-center gap-2 h-8 px-3 text-xs">
      {/* Health dot */}
      <span className={cn('inline-block h-2 w-2 rounded-full shrink-0', healthColor)} />

      {/* Session ID with hover card */}
      <HoverCard>
        <HoverCardTrigger asChild>
          <button className="flex items-center gap-1 font-mono text-xs text-muted-foreground hover:text-foreground transition-colors">
            {truncatedId}
          </button>
        </HoverCardTrigger>
        <HoverCardContent className="w-80 text-xs" side="bottom" align="start">
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm">Session Details</span>
              <span className={cn('inline-block h-2 w-2 rounded-full', healthColor)} />
            </div>
            <Separator />
            <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
              <span className="text-muted-foreground">Session ID</span>
              <span className="font-mono break-all">{session.session_id}</span>
              <span className="text-muted-foreground">Channel ID</span>
              <span className="font-mono break-all">{session.channel_id}</span>
              <span className="text-muted-foreground">User ID</span>
              <span className="font-mono break-all">{session.user_id}</span>
              <span className="text-muted-foreground">Chat ID</span>
              <span className="font-mono break-all">{session.chat_id}</span>
              <span className="text-muted-foreground">Type</span>
              <span>{session.session_type}</span>
              <span className="text-muted-foreground">Activation</span>
              <span>{session.activation_mode}</span>
              <span className="text-muted-foreground">Messages</span>
              <span>{session.message_count}</span>
              {session.memory_usage !== undefined && (
                <>
                  <span className="text-muted-foreground">Memory</span>
                  <span>{session.memory_usage}%</span>
                </>
              )}
              <span className="text-muted-foreground">Created</span>
              <span>{new Date(session.created_at).toLocaleString()}</span>
              <span className="text-muted-foreground">Last Active</span>
              <span>{new Date(session.last_activity_at).toLocaleString()}</span>
              <span className="text-muted-foreground">Idle</span>
              <span>{Math.round(idleMinutes)}min</span>
              {session.archived_at && (
                <>
                  <span className="text-muted-foreground">Archived</span>
                  <span>{new Date(session.archived_at).toLocaleString()}</span>
                </>
              )}
            </div>
          </div>
        </HoverCardContent>
      </HoverCard>

      {/* Copy button */}
      <Button
        variant="ghost"
        size="icon"
        className="h-5 w-5"
        onClick={handleCopySessionId}
      >
        {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
        <span className="sr-only">Copy session ID</span>
      </Button>

      <Separator orientation="vertical" className="h-4" />

      {/* Channel badge */}
      {(channelId || session.channel_id) && (
        <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
          {channelId ?? session.channel_id}
        </Badge>
      )}

      {/* Session type badge */}
      <Badge
        variant={sessionTypeBadgeVariant(session.session_type)}
        className="text-[10px] px-1.5 py-0"
      >
        {session.session_type}
      </Badge>

      {/* Activation mode */}
      <span className="text-muted-foreground">{session.activation_mode}</span>

      <Separator orientation="vertical" className="h-4" />

      {/* Message count */}
      <span className="text-muted-foreground">
        {session.message_count} msgs
      </span>

      {/* Memory usage mini progress bar */}
      {showMemoryBar && (
        <>
          <Separator orientation="vertical" className="h-4" />
          <div className="flex items-center gap-1">
            <Progress
              value={session.memory_usage}
              className="h-1.5 w-16"
            />
            <span className="text-muted-foreground">
              {session.memory_usage}%
            </span>
          </div>
        </>
      )}
    </div>
  );
};
