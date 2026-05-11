/**
 * Type definitions for OpenClaw Gateway integration
 * 
 * These types define the data structures for multi-channel gateway features:
 * - Channels: Messaging platform integrations (Slack, Telegram, Discord, WhatsApp)
 * - Sessions: Isolated conversation contexts with independent state
 * - Webhooks: HTTP endpoints that trigger agent actions
 * - Cron Jobs: Scheduled recurring agent tasks
 * - Gateway Metrics: Real-time system health and performance data
 */

// ============================================================================
// Channel Types
// ============================================================================

/**
 * Supported messaging platform types
 */
export enum ChannelType {
  SLACK = 'slack',
  TELEGRAM = 'telegram',
  DISCORD = 'discord',
  WHATSAPP = 'whatsapp',
}

/**
 * Channel connection status
 */
export enum ChannelStatus {
  CONNECTED = 'connected',
  DISCONNECTED = 'disconnected',
  ERROR = 'error',
}

/**
 * Channel configuration stored in database
 */
export interface ChannelConfig {
  api_token: string;
  webhook_url?: string;
  rate_limit_per_minute: number;
  max_message_length: number;
  supports_threads: boolean;
  supports_buttons: boolean;
  supports_embeds: boolean;
  custom_config: Record<string, any>;
}

/**
 * Channel entity representing a messaging platform integration
 */
export interface Channel {
  channel_id: string;
  channel_type: ChannelType;
  status: ChannelStatus;
  config: ChannelConfig;
  enabled: boolean;
  created_at: string;
  updated_at: string;
  error_message?: string;
}

/**
 * Form data for creating/editing a channel
 */
export interface ChannelFormData {
  channel_id: string;
  channel_type: ChannelType;
  api_token: string;
  webhook_url?: string;
  rate_limit_per_minute: number;
  enabled: boolean;
}

// ============================================================================
// Session Types
// ============================================================================

/**
 * Session type determines behavior and permissions
 */
export enum SessionType {
  MAIN = 'main',
  GROUP = 'group',
  WEBHOOK = 'webhook',
}

/**
 * Activation mode for group sessions
 */
export enum ActivationMode {
  MENTION = 'mention',
  ALWAYS = 'always',
  MANUAL = 'manual',
}

/**
 * Session entity representing an isolated conversation context
 */
export interface Session {
  session_id: string;
  channel_id: string;
  user_id: string;
  chat_id: string;
  session_type: SessionType;
  activation_mode: ActivationMode;
  tool_allowlist: string[];
  tool_denylist: string[];
  message_count: number;
  token_usage: Record<string, number>;
  memory_usage?: number; // Percentage of memory limit used (0-100)
  created_at: string;
  last_activity_at: string;
  archived_at?: string;
}

/**
 * Message within a session
 */
export interface SessionMessage {
  message_id: number;
  session_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  metadata: Record<string, any>;
  source_session?: string; // Session ID if this is an inter-session message
  created_at: string;
}

/**
 * Form data for sending a message to a session
 */
export interface SessionMessageFormData {
  message: string;
  metadata?: string; // JSON string
}

/**
 * Form data for updating session configuration
 */
export interface SessionConfigFormData {
  activation_mode: ActivationMode;
  tool_allowlist: string[];
  tool_denylist: string[];
}

// ============================================================================
// Webhook Types
// ============================================================================

/**
 * Webhook entity representing an HTTP endpoint that triggers agent actions
 */
export interface Webhook {
  webhook_id: string;
  webhook_url: string;
  target_session_id: string;
  auth_token: string;
  payload_schema?: Record<string, any>;
  transform_rules: Record<string, any>;
  enabled: boolean;
  created_at: string;
  last_triggered_at?: string;
}

/**
 * Form data for creating/editing a webhook
 */
export interface WebhookFormData {
  webhook_id: string;
  target_session_id: string;
  auth_token: string;
  payload_schema?: string; // JSON string
  transform_rules?: string; // JSON string
  enabled: boolean;
}

/**
 * Form data for testing a webhook
 */
export interface WebhookTestFormData {
  payload: string; // JSON string
  auth_token: string;
}

/**
 * Webhook test response
 */
export interface WebhookTestResponse {
  status: number;
  body: string;
  timestamp: string;
}

// ============================================================================
// Cron Job Types
// ============================================================================

/**
 * Cron job execution outcome
 */
export enum CronExecutionOutcome {
  SUCCESS = 'success',
  FAILURE = 'failure',
  SKIPPED = 'skipped',
}

/**
 * Cron job entity representing a scheduled recurring task
 */
export interface CronJob {
  cron_job_id: string;
  schedule: string;
  target_session_id: string;
  message_template: string;
  timezone: string;
  enabled: boolean;
  created_at: string;
  last_executed_at?: string;
  next_execution_at?: string;
}

/**
 * Cron job execution record
 */
export interface CronExecution {
  execution_id: number;
  cron_job_id: string;
  timestamp: string;
  outcome: CronExecutionOutcome;
  error_message?: string;
}

/**
 * Form data for creating/editing a cron job
 */
export interface CronJobFormData {
  cron_job_id: string;
  schedule: string;
  target_session_id: string;
  message_template: string;
  timezone: string;
  enabled: boolean;
}

/**
 * Cron schedule preview showing next execution times
 */
export interface CronSchedulePreview {
  next_executions: string[];
  is_valid: boolean;
  error_message?: string;
}

// ============================================================================
// Gateway Metrics Types
// ============================================================================

/**
 * Overall gateway metrics
 */
export interface GatewayMetrics {
  messages_per_channel: Record<string, number>;
  active_sessions: number;
  queue_depth: number;
  channel_health: Record<string, ChannelStatus>;
  timestamp: string;
}

/**
 * Channel-specific metrics
 */
export interface ChannelMetrics {
  channel_id: string;
  messages_sent: number;
  messages_received: number;
  errors: number;
  avg_response_time_ms: number;
  timestamp: string;
}

/**
 * Time range for metrics filtering
 */
export enum MetricsTimeRange {
  LAST_HOUR = 'last_hour',
  LAST_24H = 'last_24h',
  LAST_7D = 'last_7d',
}

// ============================================================================
// API Response Types
// ============================================================================

/**
 * Paginated list response
 */
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
  has_prev: boolean;
}

/**
 * API error response
 */
export interface ApiError {
  error: string;
  message: string;
  details?: Record<string, any>;
}

// ============================================================================
// Filter and Sort Types
// ============================================================================

/**
 * Channel list filters
 */
export interface ChannelFilters {
  channel_type?: ChannelType;
  status?: ChannelStatus;
  enabled?: boolean;
  search?: string;
}

/**
 * Session list filters
 */
export interface SessionFilters {
  channel_id?: string;
  session_type?: SessionType;
  activation_mode?: ActivationMode;
  archived?: boolean;
  search?: string;
}

/**
 * Webhook list filters
 */
export interface WebhookFilters {
  enabled?: boolean;
  search?: string;
}

/**
 * Cron job list filters
 */
export interface CronJobFilters {
  enabled?: boolean;
  search?: string;
}

/**
 * Cron execution history filters
 */
export interface CronExecutionFilters {
  outcome?: CronExecutionOutcome;
  start_date?: string;
  end_date?: string;
}

/**
 * Sort direction
 */
export enum SortDirection {
  ASC = 'asc',
  DESC = 'desc',
}

/**
 * Sort configuration
 */
export interface SortConfig {
  field: string;
  direction: SortDirection;
}

// ============================================================================
// DM Pairing Types
// ============================================================================

/**
 * Channel user approval status
 */
export enum ApprovalStatus {
  PENDING = 'pending',
  APPROVED = 'approved',
  REJECTED = 'rejected',
}

/**
 * Channel user entity representing a user across channels with approval status
 */
export interface ChannelUser {
  channel_user_id: string;
  channel_id: string;
  user_id: string;
  user_name?: string;
  approved: boolean;
  approval_code?: string;
  approval_code_expires_at?: string;
  created_at: string;
  approved_at?: string;
}

/**
 * Approval event log entry
 */
export interface ApprovalEvent {
  event_id: number;
  channel_user_id: string;
  event_type: 'generated' | 'approved' | 'rejected' | 'revoked';
  user_id: string;
  user_name?: string;
  channel_id: string;
  timestamp: string;
  details?: string;
}

/**
 * Form data for generating an approval code
 */
export interface GenerateApprovalCodeFormData {
  channel_id: string;
  user_id: string;
  user_name?: string;
}

/**
 * Form data for approving a user
 */
export interface ApproveUserFormData {
  channel_user_id: string;
  approval_code?: string;
}

/**
 * DM pairing filters
 */
export interface DMPairingFilters {
  channel_id?: string;
  approved?: boolean;
  search?: string;
}

// ============================================================================
// Browser Instance Types
// ============================================================================

/**
 * Browser instance status
 */
export enum BrowserInstanceStatus {
  ACTIVE = 'active',
  IDLE = 'idle',
  CLOSED = 'closed',
}

/**
 * Browser instance entity representing an active browser session
 */
export interface BrowserInstance {
  session_id: string;
  url: string;
  status: BrowserInstanceStatus;
  memory_usage: number; // Memory usage in MB
  created_at: string;
  last_activity_at?: string;
  screenshot_url?: string; // URL to latest screenshot thumbnail
}

/**
 * Browser screenshot entity
 */
export interface BrowserScreenshot {
  screenshot_id: string;
  session_id: string;
  url: string;
  image_url: string;
  timestamp: string;
}

/**
 * Browser CDP command log entry
 */
export interface BrowserCDPCommand {
  command_id: number;
  session_id: string;
  command: string;
  params: Record<string, any>;
  result?: Record<string, any>;
  error?: string;
  timestamp: string;
  duration_ms: number;
}

// ============================================================================
// Security Audit Types
// ============================================================================

/**
 * Security audit event types
 */
export enum SecurityEventType {
  BLOCKED_TOOL = 'blocked_tool',
  FAILED_WEBHOOK_AUTH = 'failed_webhook_auth',
  DM_PAIRING_FAILURE = 'dm_pairing_failure',
  UNAUTHORIZED_ACCESS = 'unauthorized_access',
}

/**
 * Security event severity levels
 */
export enum SecurityEventSeverity {
  INFO = 'info',
  WARNING = 'warning',
  ERROR = 'error',
}

/**
 * Security audit event entity
 */
export interface SecurityAuditEvent {
  event_id: number;
  timestamp: string;
  event_type: SecurityEventType;
  severity: SecurityEventSeverity;
  session_id?: string;
  user_id?: string;
  channel_id?: string;
  details: string;
  metadata?: Record<string, any>;
}

/**
 * Security audit log filters
 */
export interface SecurityAuditFilters {
  event_type?: SecurityEventType;
  severity?: SecurityEventSeverity;
  start_date?: string;
  end_date?: string;
  search?: string; // Search by session_id or user_id
}
