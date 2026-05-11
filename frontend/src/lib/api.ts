import { v4 as uuidv4 } from 'uuid';
import { authFetch, getAccessToken } from './auth-client';
import type { Message, FileAttachment, Conversation } from '@/types/database.types';

const ENABLE_STREAMING = import.meta.env.VITE_ENABLE_STREAMING === 'true';
const AGENT_ENDPOINT = import.meta.env.VITE_AGENT_ENDPOINT;
const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

interface ApiResponse {
  title?: string;
  session_id?: string;
  output: string;
}

interface StreamingChunk {
  text?: string;
  title?: string;
  session_id?: string;
  done?: boolean;
  complete?: boolean;
  conversation_title?: string;
  error?: string;
  trace_id?: string;
}

export const sendMessage = async (
  query: string,
  user_id: string,
  session_id: string = '',
  access_token?: string,
  files?: FileAttachment[],
  onStreamChunk?: (chunk: StreamingChunk) => void
): Promise<ApiResponse> => {
  const token = access_token || getAccessToken();
  const request_id = uuidv4();
  const payload = { query, user_id, request_id, session_id, files };

  const response = await fetch(AGENT_ENDPOINT, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': token ? `Bearer ${token}` : '',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`API error: ${response.status} - ${errorText}`);
  }

  if (ENABLE_STREAMING && onStreamChunk) {
    return handleStreamingResponse(response, session_id, onStreamChunk);
  }

  return handleStandardResponse(response, session_id);
};

export const fetchConversations = async (): Promise<Conversation[]> => {
  const res = await authFetch(`${API_BASE}/api/conversations`);
  if (!res.ok) throw new Error(`Failed to fetch conversations: ${res.status}`);
  return res.json();
};

export const fetchMessages = async (sessionId: string): Promise<Message[]> => {
  const res = await authFetch(`${API_BASE}/api/conversations/${sessionId}/messages`);
  if (!res.ok) throw new Error(`Failed to fetch messages: ${res.status}`);
  return res.json();
};


// ---------------------------------------------------------------------------
// Response handlers (extracted from the original monolithic sendMessage)
// ---------------------------------------------------------------------------

async function handleStreamingResponse(
  response: Response,
  sessionId: string,
  onStreamChunk: (chunk: StreamingChunk) => void
): Promise<ApiResponse> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('Failed to get response reader');

  const decoder = new TextDecoder();
  let lastTextChunk = '';
  let finalText = '';
  let finalTitle = '';
  let finalSessionId = sessionId;

  while (true) {
    const { done, value } = await reader.read();

    const raw = done ? decoder.decode() : decoder.decode(value, { stream: true });
    if (!raw) {
      if (done) break;
      continue;
    }

    const lines = raw.split('\n').filter((l) => l.trim() !== '');

    for (const line of lines) {
      let chunk: StreamingChunk;
      try {
        chunk = JSON.parse(line);
      } catch {
        continue; // skip malformed JSON fragments
      }

      if (chunk.text !== undefined && chunk.text.trim() !== '') {
        lastTextChunk = chunk.text;
        finalText = chunk.text;
        onStreamChunk(chunk);
      }

      if (chunk.title) finalTitle = chunk.title;
      if (chunk.session_id) finalSessionId = chunk.session_id;
      if (chunk.conversation_title) finalTitle = chunk.conversation_title;

      if (chunk.complete === true) {
        if (chunk.text !== undefined && chunk.text.trim() !== '') {
          lastTextChunk = chunk.text;
          finalText = chunk.text;
        }

        onStreamChunk({
          text: lastTextChunk,
          complete: true,
          session_id: finalSessionId,
          conversation_title: finalTitle,
          trace_id: chunk.trace_id,
        });

        return {
          title: finalTitle || 'New conversation',
          session_id: finalSessionId,
          output: lastTextChunk || finalText,
        };
      }
    }

    if (done) break;
  }

  return {
    title: finalTitle || 'New conversation',
    session_id: finalSessionId,
    output: lastTextChunk || finalText,
  };
}

async function handleStandardResponse(
  response: Response,
  sessionId: string
): Promise<ApiResponse> {
  const responseText = await response.text();
  if (!responseText.trim()) throw new Error('Empty response from API');

  const parsed = JSON.parse(responseText);

  if (Array.isArray(parsed)) {
    return {
      title: parsed[0]?.conversation_title || 'New conversation',
      session_id: parsed[0]?.session_id || sessionId,
      output: parsed[0]?.output || "Sorry, I couldn't process your request.",
    };
  }

  return parsed;
}

// ============================================================================
// Gateway API Functions (OpenClaw Integration)
// ============================================================================

import { ChannelStatus } from '@/types/gateway';
import type {
  Channel,
  ChannelFormData,
  ChannelFilters,
  Session,
  SessionFilters,
  SessionMessage,
  SessionMessageFormData,
  SessionConfigFormData,
  Webhook,
  WebhookFormData,
  WebhookFilters,
  WebhookTestFormData,
  WebhookTestResponse,
  CronJob,
  CronJobFormData,
  CronJobFilters,
  CronExecution,
  CronExecutionFilters,
  CronSchedulePreview,
  GatewayMetrics,
  ChannelMetrics,
  MetricsTimeRange,
  PaginatedResponse,
  BrowserInstance,
  BrowserScreenshot,
  BrowserCDPCommand,
  ChannelUser,
  ApprovalEvent,
  GenerateApprovalCodeFormData,
  ApproveUserFormData,
  DMPairingFilters,
} from '@/types/gateway';

// ---------------------------------------------------------------------------
// Channel Management
// ---------------------------------------------------------------------------

export const listChannels = async (filters?: ChannelFilters): Promise<Channel[]> => {
  const params = new URLSearchParams();
  if (filters?.channel_type) params.append('channel_type', filters.channel_type);
  if (filters?.status) params.append('status', filters.status);
  if (filters?.enabled !== undefined) params.append('enabled', String(filters.enabled));
  if (filters?.search) params.append('search', filters.search);

  const url = `${API_BASE}/api/gateway/channels${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (res.ok) return res.json();
  if (res.status !== 404) throw new Error(`Failed to fetch channels: ${res.status}`);

  // Compatibility fallback: derive channel list from monitor gateway endpoint.
  const monitorRes = await authFetch(`${API_BASE}/api/admin/monitor/gateway`);
  if (!monitorRes.ok) throw new Error(`Failed to fetch channels: ${monitorRes.status}`);
  const monitor = await monitorRes.json();

  return (monitor.channels ?? []).map((channel: any) => ({
    channel_id: channel.channel_id,
    channel_type: channel.channel_type,
    status: channel.status,
    config: {
      api_token: '',
      webhook_url: undefined,
      rate_limit_per_minute: 60,
      max_message_length: 4000,
      supports_threads: true,
      supports_buttons: false,
      supports_embeds: false,
      custom_config: {},
    },
    enabled: Boolean(channel.is_connected),
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    error_message: channel.error_count > 0 ? `${channel.error_count} recent errors` : undefined,
  }));
};

export const getChannel = async (channelId: string): Promise<Channel> => {
  const res = await authFetch(`${API_BASE}/api/gateway/channels/${channelId}`);
  if (!res.ok) throw new Error(`Failed to fetch channel: ${res.status}`);
  return res.json();
};

export const createChannel = async (data: ChannelFormData): Promise<Channel> => {
  const res = await authFetch(`${API_BASE}/api/gateway/channels`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to create channel: ${error}`);
  }
  return res.json();
};

export const updateChannel = async (channelId: string, data: Partial<ChannelFormData>): Promise<Channel> => {
  const res = await authFetch(`${API_BASE}/api/gateway/channels/${channelId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to update channel: ${error}`);
  }
  return res.json();
};

export const deleteChannel = async (channelId: string): Promise<void> => {
  const res = await authFetch(`${API_BASE}/api/gateway/channels/${channelId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to delete channel: ${error}`);
  }
};

export const testChannelConnection = async (channelId: string): Promise<{ success: boolean; message: string }> => {
  const res = await authFetch(`${API_BASE}/api/gateway/channels/${channelId}/test`, {
    method: 'POST',
  });
  if (res.ok) return res.json();

  if (res.status !== 404) {
    const error = await res.text();
    throw new Error(`Failed to test channel: ${error}`);
  }

  // Compatibility fallback for backends without /api/gateway/channels/{id}/test.
  const monitorRes = await authFetch(`${API_BASE}/api/admin/monitor/gateway`);
  if (!monitorRes.ok) {
    return {
      success: false,
      message: `Channel test endpoint unavailable and monitor check failed (${monitorRes.status}).`,
    };
  }

  const monitor = await monitorRes.json();
  const channel = (monitor.channels ?? []).find((c: any) => c.channel_id === channelId);
  if (!channel) {
    return {
      success: false,
      message: "Channel not found in gateway monitor.",
    };
  }

  const isConnected = channel.status === "connected" || channel.is_connected === true;
  return {
    success: Boolean(isConnected),
    message: isConnected ? "Channel appears connected (monitor fallback)." : "Channel is not connected (monitor fallback).",
  };
};

// ---------------------------------------------------------------------------
// Session Management
// ---------------------------------------------------------------------------

export const listSessions = async (filters?: SessionFilters): Promise<Session[]> => {
  const params = new URLSearchParams();
  if (filters?.channel_id) params.append('channel_id', filters.channel_id);
  if (filters?.session_type) params.append('session_type', filters.session_type);
  if (filters?.activation_mode) params.append('activation_mode', filters.activation_mode);
  if (filters?.archived !== undefined) params.append('archived', String(filters.archived));
  if (filters?.search) params.append('search', filters.search);

  const url = `${API_BASE}/api/gateway/sessions${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(`Failed to fetch sessions: ${res.status}`);
  }
  return res.json();
};

export const getSession = async (sessionId: string): Promise<Session> => {
  const res = await authFetch(`${API_BASE}/api/gateway/sessions/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to fetch session: ${res.status}`);
  return res.json();
};

export const getSessionHistory = async (sessionId: string, limit: number = 50, offset: number = 0): Promise<SessionMessage[]> => {
  const params = new URLSearchParams({ limit: limit.toString(), offset: offset.toString() });
  const res = await authFetch(`${API_BASE}/api/gateway/sessions/${sessionId}/history?${params}`);
  if (!res.ok) throw new Error(`Failed to fetch session history: ${res.status}`);
  return res.json();
};

export const sendMessageToSession = async (sessionId: string, data: SessionMessageFormData): Promise<SessionMessage> => {
  const res = await authFetch(`${API_BASE}/api/gateway/sessions/${sessionId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to send message: ${error}`);
  }
  return res.json();
};

export const updateSessionConfig = async (sessionId: string, data: SessionConfigFormData): Promise<Session> => {
  const res = await authFetch(`${API_BASE}/api/gateway/sessions/${sessionId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to update session: ${error}`);
  }
  return res.json();
};

export const archiveSession = async (sessionId: string): Promise<void> => {
  const res = await authFetch(`${API_BASE}/api/gateway/sessions/${sessionId}/archive`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to archive session: ${error}`);
  }
};

// ---------------------------------------------------------------------------
// Webhook Management
// ---------------------------------------------------------------------------

export const listWebhooks = async (filters?: WebhookFilters): Promise<Webhook[]> => {
  const params = new URLSearchParams();
  if (filters?.enabled !== undefined) params.append('enabled', String(filters.enabled));
  if (filters?.search) params.append('search', filters.search);

  const url = `${API_BASE}/api/gateway/webhooks${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (!res.ok) throw new Error(`Failed to fetch webhooks: ${res.status}`);
  return res.json();
};

export const getWebhook = async (webhookId: string): Promise<Webhook> => {
  const res = await authFetch(`${API_BASE}/api/gateway/webhooks/${webhookId}`);
  if (!res.ok) throw new Error(`Failed to fetch webhook: ${res.status}`);
  return res.json();
};

export const createWebhook = async (data: WebhookFormData): Promise<Webhook> => {
  const res = await authFetch(`${API_BASE}/api/gateway/webhooks`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to create webhook: ${error}`);
  }
  return res.json();
};

export const updateWebhook = async (webhookId: string, data: Partial<WebhookFormData>): Promise<Webhook> => {
  const res = await authFetch(`${API_BASE}/api/gateway/webhooks/${webhookId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to update webhook: ${error}`);
  }
  return res.json();
};

export const deleteWebhook = async (webhookId: string): Promise<void> => {
  const res = await authFetch(`${API_BASE}/api/gateway/webhooks/${webhookId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to delete webhook: ${error}`);
  }
};

export const testWebhook = async (webhookId: string, data: WebhookTestFormData): Promise<WebhookTestResponse> => {
  const res = await authFetch(`${API_BASE}/api/gateway/webhooks/${webhookId}/test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to test webhook: ${error}`);
  }
  return res.json();
};

// ---------------------------------------------------------------------------
// Cron Job Management
// ---------------------------------------------------------------------------

export const listCronJobs = async (filters?: CronJobFilters): Promise<CronJob[]> => {
  const params = new URLSearchParams();
  if (filters?.enabled !== undefined) params.append('enabled', String(filters.enabled));
  if (filters?.search) params.append('search', filters.search);

  const url = `${API_BASE}/api/gateway/cron-jobs${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (!res.ok) throw new Error(`Failed to fetch cron jobs: ${res.status}`);
  return res.json();
};

export const getCronJob = async (cronJobId: string): Promise<CronJob> => {
  const res = await authFetch(`${API_BASE}/api/gateway/cron-jobs/${cronJobId}`);
  if (!res.ok) throw new Error(`Failed to fetch cron job: ${res.status}`);
  return res.json();
};

export const createCronJob = async (data: CronJobFormData): Promise<CronJob> => {
  const res = await authFetch(`${API_BASE}/api/gateway/cron-jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to create cron job: ${error}`);
  }
  return res.json();
};

export const updateCronJob = async (cronJobId: string, data: Partial<CronJobFormData>): Promise<CronJob> => {
  const res = await authFetch(`${API_BASE}/api/gateway/cron-jobs/${cronJobId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to update cron job: ${error}`);
  }
  return res.json();
};

export const deleteCronJob = async (cronJobId: string): Promise<void> => {
  const res = await authFetch(`${API_BASE}/api/gateway/cron-jobs/${cronJobId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to delete cron job: ${error}`);
  }
};

export const pauseCronJob = async (cronJobId: string): Promise<CronJob> => {
  const res = await authFetch(`${API_BASE}/api/gateway/cron-jobs/${cronJobId}/pause`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to pause cron job: ${error}`);
  }
  return res.json();
};

export const resumeCronJob = async (cronJobId: string): Promise<CronJob> => {
  const res = await authFetch(`${API_BASE}/api/gateway/cron-jobs/${cronJobId}/resume`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to resume cron job: ${error}`);
  }
  return res.json();
};

export const executeCronJobNow = async (cronJobId: string): Promise<{ success: boolean; message: string }> => {
  const res = await authFetch(`${API_BASE}/api/gateway/cron-jobs/${cronJobId}/execute`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to execute cron job: ${error}`);
  }
  return res.json();
};

export const getCronExecutionHistory = async (
  cronJobId: string,
  filters?: CronExecutionFilters
): Promise<CronExecution[]> => {
  const params = new URLSearchParams();
  if (filters?.outcome) params.append('outcome', filters.outcome);
  if (filters?.start_date) params.append('start_date', filters.start_date);
  if (filters?.end_date) params.append('end_date', filters.end_date);

  const url = `${API_BASE}/api/gateway/cron-jobs/${cronJobId}/history${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (!res.ok) throw new Error(`Failed to fetch cron execution history: ${res.status}`);
  return res.json();
};

export const previewCronSchedule = async (schedule: string, timezone: string): Promise<CronSchedulePreview> => {
  const res = await authFetch(`${API_BASE}/api/gateway/cron-jobs/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ schedule, timezone }),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to preview cron schedule: ${error}`);
  }
  return res.json();
};

// ---------------------------------------------------------------------------
// Gateway Metrics
// ---------------------------------------------------------------------------

export const getGatewayMetrics = async (timeRange?: MetricsTimeRange): Promise<GatewayMetrics> => {
  const params = timeRange ? `?time_range=${timeRange}` : '';
  const res = await authFetch(`${API_BASE}/api/admin/monitor/gateway${params}`);
  if (!res.ok) throw new Error(`Failed to fetch gateway metrics: ${res.status}`);
  const data = await res.json();

  const messagesPerChannel: Record<string, number> = {};
  const channelHealth: Record<string, ChannelStatus> = {};
  let queueDepth = 0;

  for (const channel of data.channels ?? []) {
    const routed = Number(channel.messages_sent ?? 0);
    const delivered = Number(channel.messages_received ?? 0);
    const errors = Number(channel.error_count ?? 0);
    const channelQueueDepth = Number(channel.queue_depth ?? 0);
    messagesPerChannel[channel.channel_id] = routed + delivered;
    queueDepth += channelQueueDepth;

    if (channel.status === 'connected' || channel.is_connected === true) {
      channelHealth[channel.channel_id] = ChannelStatus.CONNECTED;
    } else if (errors > 0 || channel.status === 'error') {
      channelHealth[channel.channel_id] = ChannelStatus.ERROR;
    } else {
      channelHealth[channel.channel_id] = ChannelStatus.DISCONNECTED;
    }
  }

  return {
    messages_per_channel: messagesPerChannel,
    active_sessions: Number(data.active_sessions ?? 0),
    queue_depth: queueDepth,
    channel_health: channelHealth,
    timestamp: new Date().toISOString(),
  };
};

export const getChannelMetrics = async (channelId: string, timeRange?: MetricsTimeRange): Promise<ChannelMetrics> => {
  const params = timeRange ? `?time_range=${timeRange}` : '';
  const res = await authFetch(`${API_BASE}/api/admin/monitor/gateway${params}`);
  if (!res.ok) throw new Error(`Failed to fetch channel metrics: ${res.status}`);
  const data = await res.json();
  const channel = (data.channels ?? []).find((c: { channel_id: string }) => c.channel_id === channelId);
  if (!channel) throw new Error(`Channel not found in metrics: ${channelId}`);

  return {
    channel_id: channel.channel_id,
    messages_sent: Number(channel.messages_sent ?? 0),
    messages_received: Number(channel.messages_received ?? 0),
    errors: Number(channel.error_count ?? 0),
    avg_response_time_ms: 0,
    timestamp: new Date().toISOString(),
  };
};

// ---------------------------------------------------------------------------
// Browser Instance Management
// ---------------------------------------------------------------------------

export const listBrowserInstances = async (): Promise<BrowserInstance[]> => {
  const res = await authFetch(`${API_BASE}/api/gateway/browser-instances`);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(`Failed to fetch browser instances: ${res.status}`);
  }
  return res.json();
};

export const getBrowserInstance = async (sessionId: string): Promise<BrowserInstance> => {
  const res = await authFetch(`${API_BASE}/api/gateway/browser-instances/${sessionId}`);
  if (!res.ok) throw new Error(`Failed to fetch browser instance: ${res.status}`);
  return res.json();
};

export const closeBrowserInstance = async (sessionId: string): Promise<void> => {
  const res = await authFetch(`${API_BASE}/api/gateway/browser-instances/${sessionId}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to close browser instance: ${error}`);
  }
};

export const getBrowserScreenshots = async (sessionId: string): Promise<BrowserScreenshot[]> => {
  const res = await authFetch(`${API_BASE}/api/gateway/browser-instances/${sessionId}/screenshots`);
  if (!res.ok) throw new Error(`Failed to fetch browser screenshots: ${res.status}`);
  return res.json();
};

export const getBrowserCDPLog = async (sessionId: string, limit: number = 100): Promise<BrowserCDPCommand[]> => {
  const params = new URLSearchParams({ limit: limit.toString() });
  const res = await authFetch(`${API_BASE}/api/gateway/browser-instances/${sessionId}/cdp-log?${params}`);
  if (!res.ok) throw new Error(`Failed to fetch CDP log: ${res.status}`);
  return res.json();
};

// ---------------------------------------------------------------------------
// DM Pairing Management
// ---------------------------------------------------------------------------

export const listChannelUsers = async (filters?: DMPairingFilters): Promise<ChannelUser[]> => {
  const params = new URLSearchParams();
  if (filters?.channel_id) params.append('channel_id', filters.channel_id);
  if (filters?.approved !== undefined) params.append('approved', String(filters.approved));
  if (filters?.search) params.append('search', filters.search);

  const url = `${API_BASE}/api/gateway/dm-pairing/users${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(`Failed to fetch channel users: ${res.status}`);
  }
  return res.json();
};

export const generateApprovalCode = async (data: GenerateApprovalCodeFormData): Promise<ChannelUser> => {
  const res = await authFetch(`${API_BASE}/api/gateway/dm-pairing/generate-code`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to generate approval code: ${error}`);
  }
  return res.json();
};

export const approveUser = async (data: ApproveUserFormData): Promise<ChannelUser> => {
  const res = await authFetch(`${API_BASE}/api/gateway/dm-pairing/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to approve user: ${error}`);
  }
  return res.json();
};

export const revokeApproval = async (channelUserId: string): Promise<void> => {
  const res = await authFetch(`${API_BASE}/api/gateway/dm-pairing/${channelUserId}/revoke`, {
    method: 'POST',
  });
  if (!res.ok) {
    const error = await res.text();
    throw new Error(`Failed to revoke approval: ${error}`);
  }
};

export const getApprovalHistory = async (filters?: { channel_id?: string; start_date?: string; end_date?: string }): Promise<ApprovalEvent[]> => {
  const params = new URLSearchParams();
  if (filters?.channel_id) params.append('channel_id', filters.channel_id);
  if (filters?.start_date) params.append('start_date', filters.start_date);
  if (filters?.end_date) params.append('end_date', filters.end_date);

  const url = `${API_BASE}/api/gateway/dm-pairing/history${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(`Failed to fetch approval history: ${res.status}`);
  }
  return res.json();
};

// ---------------------------------------------------------------------------
// Security Audit Log
// ---------------------------------------------------------------------------

import type { SecurityAuditEvent, SecurityAuditFilters } from '@/types/gateway';

export const listSecurityAuditEvents = async (filters?: SecurityAuditFilters): Promise<SecurityAuditEvent[]> => {
  const params = new URLSearchParams();
  if (filters?.event_type) params.append('event_type', filters.event_type);
  if (filters?.severity) params.append('severity', filters.severity);
  if (filters?.start_date) params.append('start_date', filters.start_date);
  if (filters?.end_date) params.append('end_date', filters.end_date);
  if (filters?.search) params.append('search', filters.search);

  const url = `${API_BASE}/api/gateway/security-audit${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (!res.ok) {
    if (res.status === 404) return [];
    throw new Error(`Failed to fetch security audit events: ${res.status}`);
  }
  return res.json();
};

export const exportSecurityAuditLog = async (filters?: SecurityAuditFilters): Promise<Blob> => {
  const params = new URLSearchParams();
  if (filters?.event_type) params.append('event_type', filters.event_type);
  if (filters?.severity) params.append('severity', filters.severity);
  if (filters?.start_date) params.append('start_date', filters.start_date);
  if (filters?.end_date) params.append('end_date', filters.end_date);
  if (filters?.search) params.append('search', filters.search);

  const url = `${API_BASE}/api/gateway/security-audit/export${params.toString() ? `?${params}` : ''}`;
  const res = await authFetch(url);
  if (!res.ok) {
    throw new Error(`Failed to export security audit log: ${res.status}`);
  }
  return res.blob();
};

// ---------------------------------------------------------------------------
// Session Compaction
// ---------------------------------------------------------------------------

export const compactSession = async (
  sessionId: string,
  strategy: 'summarize' | 'keep_last_n' | 'archive_all',
  keepCount?: number
): Promise<{ message_count: number; token_usage: Record<string, number>; memory_usage: number }> => {
  // Try dedicated compact endpoint first, fall back to archive
  try {
    const res = await authFetch(`${API_BASE}/api/gateway/sessions/${sessionId}/compact`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy, keep_count: keepCount }),
    });
    if (res.ok) return res.json();
    if (res.status !== 404) {
      const error = await res.text();
      throw new Error(`Failed to compact session: ${error}`);
    }
  } catch (err) {
    if (err instanceof TypeError) {
      // Network error — fall through to archive fallback
    } else if (err instanceof Error && !err.message.includes('404')) {
      throw err;
    }
  }

  // Fallback: archive the session
  await archiveSession(sessionId);
  return { message_count: 0, token_usage: {}, memory_usage: 0 };
};
