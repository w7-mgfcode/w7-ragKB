/**
 * React hooks for OpenClaw Gateway data management
 * 
 * These hooks provide data fetching, caching, and state management for:
 * - Channels: Messaging platform integrations
 * - Sessions: Conversation contexts
 * - Webhooks: HTTP trigger endpoints
 * - Cron Jobs: Scheduled tasks
 * - Gateway Metrics: Real-time system health
 * 
 * All hooks include:
 * - Loading states
 * - Error handling
 * - Auto-refresh capabilities
 * - Optimistic updates
 */

import { useState, useEffect, useCallback } from 'react';
import {
  listChannels,
  getChannel,
  listSessions,
  getSession,
  getSessionHistory,
  listWebhooks,
  getWebhook,
  listCronJobs,
  getCronJob,
  getCronExecutionHistory,
  getGatewayMetrics,
  getChannelMetrics,
  listBrowserInstances,
  getBrowserInstance,
} from '@/lib/api';
import type {
  Channel,
  ChannelFilters,
  Session,
  SessionFilters,
  SessionMessage,
  Webhook,
  WebhookFilters,
  CronJob,
  CronJobFilters,
  CronExecution,
  CronExecutionFilters,
  GatewayMetrics,
  ChannelMetrics,
  MetricsTimeRange,
  BrowserInstance,
} from '@/types/gateway';

// ============================================================================
// Channel Hooks
// ============================================================================

export const useChannels = (filters?: ChannelFilters, autoRefresh: boolean = false) => {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchChannels = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listChannels(filters);
      setChannels(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch channels');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchChannels();

    if (autoRefresh) {
      const interval = setInterval(fetchChannels, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval);
    }
  }, [fetchChannels, autoRefresh]);

  return { channels, loading, error, refetch: fetchChannels };
};

export const useChannel = (channelId: string | null) => {
  const [channel, setChannel] = useState<Channel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchChannel = useCallback(async () => {
    if (!channelId) {
      setChannel(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getChannel(channelId);
      setChannel(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch channel');
    } finally {
      setLoading(false);
    }
  }, [channelId]);

  useEffect(() => {
    fetchChannel();
  }, [fetchChannel]);

  return { channel, loading, error, refetch: fetchChannel };
};

// ============================================================================
// Session Hooks
// ============================================================================

export const useSessions = (filters?: SessionFilters, autoRefresh: boolean = false) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listSessions(filters);
      setSessions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch sessions');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchSessions();

    if (autoRefresh) {
      const interval = setInterval(fetchSessions, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval);
    }
  }, [fetchSessions, autoRefresh]);

  return { sessions, loading, error, refetch: fetchSessions };
};

export const useSession = (sessionId: string | null) => {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSession = useCallback(async () => {
    if (!sessionId) {
      setSession(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getSession(sessionId);
      setSession(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch session');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  return { session, loading, error, refetch: fetchSession };
};

export const useSessionHistory = (sessionId: string | null, initialLimit: number = 50) => {
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);

  const fetchHistory = useCallback(async (currentOffset: number = 0, append: boolean = false) => {
    if (!sessionId) {
      setMessages([]);
      setLoading(false);
      setHasMore(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getSessionHistory(sessionId, initialLimit, currentOffset);
      
      if (append) {
        setMessages((prev) => [...prev, ...data]);
      } else {
        setMessages(data);
      }
      
      setHasMore(data.length === initialLimit);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch session history');
    } finally {
      setLoading(false);
    }
  }, [sessionId, initialLimit]);

  const loadMore = useCallback(() => {
    const newOffset = offset + initialLimit;
    setOffset(newOffset);
    fetchHistory(newOffset, true);
  }, [offset, initialLimit, fetchHistory]);

  useEffect(() => {
    setOffset(0);
    fetchHistory(0, false);
  }, [fetchHistory]);

  return { messages, loading, error, refetch: () => fetchHistory(0, false), loadMore, hasMore };
};

// ============================================================================
// Webhook Hooks
// ============================================================================

export const useWebhooks = (filters?: WebhookFilters, autoRefresh: boolean = false) => {
  const [webhooks, setWebhooks] = useState<Webhook[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchWebhooks = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listWebhooks(filters);
      setWebhooks(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch webhooks');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchWebhooks();

    if (autoRefresh) {
      const interval = setInterval(fetchWebhooks, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval);
    }
  }, [fetchWebhooks, autoRefresh]);

  return { webhooks, loading, error, refetch: fetchWebhooks };
};

export const useWebhook = (webhookId: string | null) => {
  const [webhook, setWebhook] = useState<Webhook | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchWebhook = useCallback(async () => {
    if (!webhookId) {
      setWebhook(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getWebhook(webhookId);
      setWebhook(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch webhook');
    } finally {
      setLoading(false);
    }
  }, [webhookId]);

  useEffect(() => {
    fetchWebhook();
  }, [fetchWebhook]);

  return { webhook, loading, error, refetch: fetchWebhook };
};

// ============================================================================
// Cron Job Hooks
// ============================================================================

export const useCronJobs = (filters?: CronJobFilters, autoRefresh: boolean = false) => {
  const [cronJobs, setCronJobs] = useState<CronJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCronJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listCronJobs(filters);
      setCronJobs(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch cron jobs');
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    fetchCronJobs();

    if (autoRefresh) {
      const interval = setInterval(fetchCronJobs, 30000); // Refresh every 30 seconds
      return () => clearInterval(interval);
    }
  }, [fetchCronJobs, autoRefresh]);

  return { cronJobs, loading, error, refetch: fetchCronJobs };
};

export const useCronJob = (cronJobId: string | null) => {
  const [cronJob, setCronJob] = useState<CronJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchCronJob = useCallback(async () => {
    if (!cronJobId) {
      setCronJob(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getCronJob(cronJobId);
      setCronJob(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch cron job');
    } finally {
      setLoading(false);
    }
  }, [cronJobId]);

  useEffect(() => {
    fetchCronJob();
  }, [fetchCronJob]);

  return { cronJob, loading, error, refetch: fetchCronJob };
};

export const useCronExecutionHistory = (cronJobId: string | null, filters?: CronExecutionFilters) => {
  const [executions, setExecutions] = useState<CronExecution[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchHistory = useCallback(async () => {
    if (!cronJobId) {
      setExecutions([]);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getCronExecutionHistory(cronJobId, filters);
      setExecutions(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch execution history');
    } finally {
      setLoading(false);
    }
  }, [cronJobId, filters]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  return { executions, loading, error, refetch: fetchHistory };
};

// ============================================================================
// Gateway Metrics Hooks
// ============================================================================

export const useGatewayMetrics = (timeRange?: MetricsTimeRange, autoRefresh: boolean = true) => {
  const [metrics, setMetrics] = useState<GatewayMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getGatewayMetrics(timeRange);
      setMetrics(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch gateway metrics');
    } finally {
      setLoading(false);
    }
  }, [timeRange]);

  useEffect(() => {
    fetchMetrics();

    if (autoRefresh) {
      const interval = setInterval(fetchMetrics, 5000); // Refresh every 5 seconds
      return () => clearInterval(interval);
    }
  }, [fetchMetrics, autoRefresh]);

  return { metrics, loading, error, refetch: fetchMetrics };
};

export const useChannelMetrics = (channelId: string | null, timeRange?: MetricsTimeRange) => {
  const [metrics, setMetrics] = useState<ChannelMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchMetrics = useCallback(async () => {
    if (!channelId) {
      setMetrics(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getChannelMetrics(channelId, timeRange);
      setMetrics(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch channel metrics');
    } finally {
      setLoading(false);
    }
  }, [channelId, timeRange]);

  useEffect(() => {
    fetchMetrics();
  }, [fetchMetrics]);

  return { metrics, loading, error, refetch: fetchMetrics };
};

// ============================================================================
// Browser Instance Hooks
// ============================================================================

export const useBrowserInstances = (autoRefresh: boolean = true) => {
  const [instances, setInstances] = useState<BrowserInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInstances = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listBrowserInstances();
      setInstances(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch browser instances');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchInstances();

    if (autoRefresh) {
      const interval = setInterval(fetchInstances, 10000); // Refresh every 10 seconds
      return () => clearInterval(interval);
    }
  }, [fetchInstances, autoRefresh]);

  return { instances, loading, error, refetch: fetchInstances };
};

export const useBrowserInstance = (sessionId: string | null) => {
  const [instance, setInstance] = useState<BrowserInstance | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchInstance = useCallback(async () => {
    if (!sessionId) {
      setInstance(null);
      setLoading(false);
      return;
    }

    try {
      setLoading(true);
      setError(null);
      const data = await getBrowserInstance(sessionId);
      setInstance(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch browser instance');
    } finally {
      setLoading(false);
    }
  }, [sessionId]);

  useEffect(() => {
    fetchInstance();
  }, [fetchInstance]);

  return { instance, loading, error, refetch: fetchInstance };
};

// ============================================================================
// Resource History Hook (Ring Buffer)
// ============================================================================

export interface ResourceSnapshot {
  timestamp: string;
  active_sessions: number;
  queue_depth: number;
  browser_count: number;
  channel_count: number;
  total_messages: number;
}

export const useResourceHistory = (maxSnapshots: number = 60) => {
  const [snapshots, setSnapshots] = useState<ResourceSnapshot[]>([]);
  const snapshotsRef = useCallback(
    (newSnapshot: ResourceSnapshot) => {
      setSnapshots((prev) => {
        const updated = [...prev, newSnapshot];
        return updated.length > maxSnapshots ? updated.slice(-maxSnapshots) : updated;
      });
    },
    [maxSnapshots]
  );

  return { snapshots, addSnapshot: snapshotsRef };
};
