/**
 * Session Relationship Graph Component
 *
 * Displays an adjacency matrix showing inter-session message relationships.
 * Features:
 * - Fetches sessions and their message histories
 * - Scans for source_session fields to build an adjacency map
 * - Renders a table with sessions as rows/columns
 * - Cell background color scaled by message count via HSL
 * - Click on a cell to select a session
 * - Cluster badges above the matrix grouping sessions by channel_id
 * - Loading and empty states
 */

import { useState, useEffect, useMemo, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from '@/components/ui/tooltip';
import { Button } from '@/components/ui/button';
import { useSessions } from '@/hooks/useGateway';
import { getSessionHistory } from '@/lib/api';
import type { Session, SessionMessage } from '@/types/gateway';
import { Layers, RefreshCw } from 'lucide-react';

interface SessionRelationshipGraphProps {
  onSessionSelect?: (sessionId: string) => void;
}

/** Map from source session to target session to message count */
type AdjacencyMap = Record<string, Record<string, number>>;

/** Color palette for channel badges */
const CHANNEL_COLORS = [
  'bg-blue-100 text-blue-800',
  'bg-green-100 text-green-800',
  'bg-purple-100 text-purple-800',
  'bg-orange-100 text-orange-800',
  'bg-pink-100 text-pink-800',
  'bg-teal-100 text-teal-800',
  'bg-yellow-100 text-yellow-800',
  'bg-red-100 text-red-800',
];

function getCellColor(count: number, maxCount: number): string {
  if (count === 0 || maxCount === 0) return 'transparent';
  const ratio = count / maxCount;
  // Interpolate lightness from 95% (low) down to 50% (high), saturation from 20% to 80%
  const lightness = 95 - ratio * 45;
  const saturation = 20 + ratio * 60;
  return `hsl(210, ${saturation}%, ${lightness}%)`;
}

export function SessionRelationshipGraph({ onSessionSelect }: SessionRelationshipGraphProps) {
  const { sessions, loading: sessionsLoading, error: sessionsError, refetch } = useSessions();
  const [adjacency, setAdjacency] = useState<AdjacencyMap>({});
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const fetchAllHistories = useCallback(async (sessionList: Session[]) => {
    if (sessionList.length === 0) return;

    setHistoryLoading(true);
    setHistoryError(null);

    const newAdjacency: AdjacencyMap = {};

    try {
      const results = await Promise.allSettled(
        sessionList.map((session) =>
          getSessionHistory(session.session_id, 100, 0).then((messages) => ({
            sessionId: session.session_id,
            messages,
          }))
        )
      );

      for (const result of results) {
        if (result.status !== 'fulfilled') continue;
        const { sessionId, messages } = result.value;

        for (const msg of messages) {
          if (msg.source_session && msg.source_session !== sessionId) {
            const source = msg.source_session;
            const target = sessionId;
            if (!newAdjacency[source]) newAdjacency[source] = {};
            newAdjacency[source][target] = (newAdjacency[source][target] || 0) + 1;
          }
        }
      }

      setAdjacency(newAdjacency);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : 'Failed to fetch session histories');
    } finally {
      setHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    if (sessions.length > 0) {
      fetchAllHistories(sessions);
    }
  }, [sessions, fetchAllHistories]);

  // Compute session IDs that participate in at least one relationship
  const sessionIds = useMemo(() => {
    return sessions.map((s) => s.session_id);
  }, [sessions]);

  // Session lookup map
  const sessionMap = useMemo(() => {
    const map: Record<string, Session> = {};
    for (const s of sessions) {
      map[s.session_id] = s;
    }
    return map;
  }, [sessions]);

  // Channel clusters
  const channelClusters = useMemo(() => {
    const clusters: Record<string, string[]> = {};
    for (const session of sessions) {
      const ch = session.channel_id || 'unknown';
      if (!clusters[ch]) clusters[ch] = [];
      clusters[ch].push(session.session_id);
    }
    return clusters;
  }, [sessions]);

  // Max count for color scaling
  const maxCount = useMemo(() => {
    let max = 0;
    for (const sourceMap of Object.values(adjacency)) {
      for (const count of Object.values(sourceMap)) {
        if (count > max) max = count;
      }
    }
    return max;
  }, [adjacency]);

  // Total relationship count
  const totalRelationships = useMemo(() => {
    let total = 0;
    for (const sourceMap of Object.values(adjacency)) {
      for (const count of Object.values(sourceMap)) {
        total += count;
      }
    }
    return total;
  }, [adjacency]);

  const truncateId = (id: string, len: number = 8): string => {
    return id.length > len ? id.slice(0, len) + '...' : id;
  };

  const loading = sessionsLoading || historyLoading;
  const error = sessionsError || historyError;

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Session Relationship Graph</CardTitle>
          <CardDescription>Inter-session message adjacency matrix</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-12 text-destructive">
            <p>Error: {error}</p>
            <Button onClick={refetch} className="mt-4" size="sm">
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Session Relationship Graph</CardTitle>
              <CardDescription>
                Inter-session message adjacency matrix ({totalRelationships} cross-session messages)
              </CardDescription>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                refetch();
                fetchAllHistories(sessions);
              }}
              disabled={loading}
            >
              <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
              Refresh
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          {/* Channel Cluster Badges */}
          {Object.keys(channelClusters).length > 0 && (
            <div className="mb-4 space-y-2">
              <p className="text-sm font-medium text-muted-foreground">Channel Clusters</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(channelClusters).map(([channelId, sessionIdList], idx) => (
                  <Badge
                    key={channelId}
                    variant="outline"
                    className={CHANNEL_COLORS[idx % CHANNEL_COLORS.length]}
                  >
                    {channelId} ({sessionIdList.length} sessions)
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Loading State */}
          {loading && (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <RefreshCw className="h-8 w-8 text-muted-foreground animate-spin" />
              <p className="text-sm text-muted-foreground">
                {sessionsLoading ? 'Loading sessions...' : 'Scanning message histories...'}
              </p>
            </div>
          )}

          {/* Empty State */}
          {!loading && sessionIds.length === 0 && (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <Layers className="h-8 w-8 text-muted-foreground" />
              <p className="text-muted-foreground">No sessions found.</p>
            </div>
          )}

          {/* Adjacency Matrix Table */}
          {!loading && sessionIds.length > 0 && (
            <TooltipProvider>
              <div className="overflow-auto max-h-[600px]">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="sticky left-0 bg-background z-10 min-w-[100px]">
                        Source / Target
                      </TableHead>
                      {sessionIds.map((targetId) => {
                        const session = sessionMap[targetId];
                        const channelIdx = Object.keys(channelClusters).indexOf(session?.channel_id || '');
                        return (
                          <TableHead key={targetId} className="text-center min-w-[80px]">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  className="text-xs font-mono hover:underline cursor-pointer"
                                  onClick={() => onSessionSelect?.(targetId)}
                                >
                                  <span
                                    className="inline-block w-2 h-2 rounded-full mr-1"
                                    style={{
                                      backgroundColor:
                                        channelIdx >= 0
                                          ? `hsl(${(channelIdx * 47) % 360}, 60%, 50%)`
                                          : '#999',
                                    }}
                                  />
                                  {truncateId(targetId)}
                                </button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p className="font-mono text-xs">{targetId}</p>
                                <p className="text-xs">Channel: {session?.channel_id || 'unknown'}</p>
                                <p className="text-xs">Type: {session?.session_type || 'unknown'}</p>
                              </TooltipContent>
                            </Tooltip>
                          </TableHead>
                        );
                      })}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {sessionIds.map((sourceId) => {
                      const sourceSession = sessionMap[sourceId];
                      const channelIdx = Object.keys(channelClusters).indexOf(
                        sourceSession?.channel_id || ''
                      );
                      return (
                        <TableRow key={sourceId}>
                          <TableCell className="sticky left-0 bg-background z-10">
                            <Tooltip>
                              <TooltipTrigger asChild>
                                <button
                                  className="text-xs font-mono hover:underline cursor-pointer flex items-center"
                                  onClick={() => onSessionSelect?.(sourceId)}
                                >
                                  <span
                                    className="inline-block w-2 h-2 rounded-full mr-1 shrink-0"
                                    style={{
                                      backgroundColor:
                                        channelIdx >= 0
                                          ? `hsl(${(channelIdx * 47) % 360}, 60%, 50%)`
                                          : '#999',
                                    }}
                                  />
                                  {truncateId(sourceId)}
                                </button>
                              </TooltipTrigger>
                              <TooltipContent>
                                <p className="font-mono text-xs">{sourceId}</p>
                                <p className="text-xs">Channel: {sourceSession?.channel_id || 'unknown'}</p>
                                <p className="text-xs">Messages: {sourceSession?.message_count || 0}</p>
                              </TooltipContent>
                            </Tooltip>
                          </TableCell>
                          {sessionIds.map((targetId) => {
                            const count = adjacency[sourceId]?.[targetId] || 0;
                            const isDiagonal = sourceId === targetId;
                            return (
                              <TableCell
                                key={targetId}
                                className="text-center cursor-pointer p-0"
                                onClick={() => {
                                  if (count > 0) {
                                    onSessionSelect?.(targetId);
                                  }
                                }}
                              >
                                <Tooltip>
                                  <TooltipTrigger asChild>
                                    <div
                                      className="w-full h-full min-h-[36px] flex items-center justify-center text-xs transition-colors hover:opacity-80"
                                      style={{
                                        backgroundColor: isDiagonal
                                          ? 'hsl(0, 0%, 92%)'
                                          : getCellColor(count, maxCount),
                                      }}
                                    >
                                      {count > 0 ? count : isDiagonal ? '-' : ''}
                                    </div>
                                  </TooltipTrigger>
                                  <TooltipContent>
                                    {isDiagonal ? (
                                      <p className="text-xs">Self ({truncateId(sourceId)})</p>
                                    ) : count > 0 ? (
                                      <div>
                                        <p className="text-xs font-medium">
                                          {count} message{count !== 1 ? 's' : ''}
                                        </p>
                                        <p className="text-xs">
                                          From: {truncateId(sourceId)}
                                        </p>
                                        <p className="text-xs">
                                          To: {truncateId(targetId)}
                                        </p>
                                      </div>
                                    ) : (
                                      <p className="text-xs">No messages between these sessions</p>
                                    )}
                                  </TooltipContent>
                                </Tooltip>
                              </TableCell>
                            );
                          })}
                        </TableRow>
                      );
                    })}
                  </TableBody>
                </Table>
              </div>
            </TooltipProvider>
          )}
        </CardContent>
      </Card>

      {/* Legend */}
      {!loading && sessionIds.length > 0 && maxCount > 0 && (
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center gap-4">
              <p className="text-sm text-muted-foreground">Color scale:</p>
              <div className="flex items-center gap-1">
                {[0, 0.25, 0.5, 0.75, 1].map((ratio) => (
                  <div
                    key={ratio}
                    className="w-8 h-4 rounded-sm border"
                    style={{
                      backgroundColor:
                        ratio === 0
                          ? 'transparent'
                          : `hsl(210, ${20 + ratio * 60}%, ${95 - ratio * 45}%)`,
                    }}
                  />
                ))}
                <span className="text-xs text-muted-foreground ml-2">
                  0 - {maxCount} messages
                </span>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
