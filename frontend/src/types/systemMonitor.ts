export interface ServiceHealth {
  name: string;
  status: 'healthy' | 'degraded' | 'down';
  details?: string;
}

export interface HealthData {
  services: ServiceHealth[];
  uptime_seconds: number;
}

export interface ModelConfig {
  llm_model: string;
  embedding_model: string;
  embedding_dimensions: number;
  gcp_project: string | null;
  gcp_region: string;
}

export interface DatabaseMetrics {
  pool_size: number;
  pool_min: number;
  pool_max: number;
  pool_free: number;
  pool_used: number;
  db_version: string;
  total_conversations: number;
  total_messages: number;
  total_documents: number;
  total_web_users: number;
}

export interface LogEntry {
  timestamp: string;
  logger: string;
  level: string;
  message: string;
}

export interface LogsData {
  records: LogEntry[];
  total_buffered: number;
}

export interface SlackStatus {
  bot_token_configured: boolean;
  app_token_configured: boolean;
  socket_handlers_count: number;
}

export interface SystemResources {
  process_memory_mb: number;
  system_memory_total_mb: number;
  system_memory_used_mb: number;
  system_memory_available_mb: number;
  cpu_percent: number;
  disk_total_gb: number;
  disk_used_gb: number;
  disk_free_gb: number;
}

export interface RagStatus {
  total_documents: number;
  total_chunks: number;
  last_indexed_at: string | null;
}

export interface EndpointMetric {
  path: string;
  request_count: number;
  avg_response_time_ms: number;
}

export interface ApiMetrics {
  endpoints: EndpointMetric[];
}

export interface DependencyVersion {
  name: string;
  version: string;
}

export interface EnvironmentInfo {
  python_version: string;
  dependencies: DependencyVersion[];
  config: Record<string, string>;
}

export interface SystemMonitorData {
  health: HealthData;
  models: ModelConfig;
  database: DatabaseMetrics;
  logs: LogsData;
  slack: SlackStatus;
  resources: SystemResources;
  rag: RagStatus;
  api_metrics: ApiMetrics;
  environment: EnvironmentInfo;
}
