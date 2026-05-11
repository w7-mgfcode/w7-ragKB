import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { RefreshCw } from 'lucide-react';
import { useSystemMonitor } from '@/hooks/useSystemMonitor';
import HealthCards from './HealthCards';
import ResourceGauges from './ResourceGauges';
import DatabaseMetricsPanel from './DatabaseMetrics';
import LogViewer from './LogViewer';
import ModelConfigPanel from './ModelConfigPanel';
import RagStatusPanel from './RagStatus';
import ApiMetricsTable from './ApiMetricsTable';
import EnvironmentInfoPanel from './EnvironmentInfo';

function LoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-24 w-full" />
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Skeleton className="h-48 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
      <Skeleton className="h-[400px] w-full" />
    </div>
  );
}

export default function SystemMonitor() {
  const { data, loading, error, refresh, lastUpdated } = useSystemMonitor();

  return (
    <div className="p-4 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          {lastUpdated && (
            <p className="text-xs text-muted-foreground">
              Last updated: {lastUpdated.toLocaleTimeString()}
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={refresh} disabled={loading}>
          <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="rounded-md border border-destructive p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {loading && !data && <LoadingSkeleton />}

      {data && (
        <div className="space-y-4">
          {/* Row 1: Health cards — full width */}
          <HealthCards
            services={data.health.services}
            uptimeSeconds={data.health.uptime_seconds}
          />

          {/* Row 2: Resources + Database — 2 columns */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ResourceGauges resources={data.resources} />
            <DatabaseMetricsPanel metrics={data.database} />
          </div>

          {/* Row 3: Log viewer — full width */}
          <LogViewer initialLogs={data.logs} />

          {/* Row 4: Model config + RAG status — 2 columns */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ModelConfigPanel config={data.models} />
            <RagStatusPanel status={data.rag} />
          </div>

          {/* Row 5: API metrics + Environment — 2 columns */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <ApiMetricsTable metrics={data.api_metrics} />
            <EnvironmentInfoPanel info={data.environment} />
          </div>
        </div>
      )}
    </div>
  );
}
