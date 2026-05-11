/**
 * Resource Usage Dashboard Component
 *
 * Resource monitoring dashboard with real-time charts and alert banners.
 * Features:
 * - Inline useResourceHistory hook maintaining a ring buffer of 60 snapshots
 * - 4 chart cards in a 2x2 grid: Memory, Sessions, Browser Instances, DB Pool
 * - Alert banners for memory > 80%, sessions > 50, browsers >= 3, pool > 18
 * - Auto-refresh toggle with interval selector (5s/10s/30s)
 * - VM Budget PieChart showing static container allocation
 */

import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import {
  AreaChart,
  Area,
  LineChart,
  Line,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  ComposedChart,
  CartesianGrid,
  XAxis,
  YAxis,
  Legend,
  Tooltip as RechartsTooltip,
} from 'recharts';
import { AlertCircle, Activity, Monitor, Database, Server, RefreshCw } from 'lucide-react';
import { useGatewayMetrics, useBrowserInstances } from '@/hooks/useGateway';
import { BrowserInstanceStatus } from '@/types/gateway';

// ============================================================================
// Constants
// ============================================================================

const MAX_SNAPSHOTS = 60;
const VM_TOTAL_MB = 4096; // 4 GB
const VM_MEMORY_ALERT_THRESHOLD = 0.8; // 80% of 4 GB = 3276.8 MB
const MAX_SESSIONS_ALERT = 50;
const MAX_BROWSER_INSTANCES = 3;
const MAX_DB_POOL = 20;
const DB_POOL_ALERT = 18;
const MEM_PER_SESSION_MB = 50; // Approximation

const VM_BUDGET = [
  { name: 'PostgreSQL', value: 1024, color: 'hsl(210, 70%, 50%)' },
  { name: 'Slack Bot', value: 1536, color: 'hsl(150, 60%, 45%)' },
  { name: 'RAG Pipeline', value: 1024, color: 'hsl(35, 80%, 50%)' },
  { name: 'Frontend', value: 512, color: 'hsl(280, 60%, 55%)' },
];

// ============================================================================
// Types
// ============================================================================

interface ResourceSnapshot {
  timestamp: string;
  label: string;
  estimatedMemoryMB: number;
  activeSessions: number;
  browserActive: number;
  browserIdle: number;
  browserClosed: number;
  browserTotal: number;
  dbPoolUsed: number;
  dbPoolFree: number;
}

// ============================================================================
// Chart Configs
// ============================================================================

const memoryChartConfig = {
  estimatedMemoryMB: {
    label: 'Estimated Memory (MB)',
    color: 'hsl(210, 70%, 50%)',
  },
} satisfies ChartConfig;

const sessionsChartConfig = {
  activeSessions: {
    label: 'Active Sessions',
    color: 'hsl(150, 60%, 45%)',
  },
} satisfies ChartConfig;

const browserChartConfig = {
  active: {
    label: 'Active',
    color: 'hsl(150, 60%, 45%)',
  },
  idle: {
    label: 'Idle',
    color: 'hsl(35, 80%, 50%)',
  },
  closed: {
    label: 'Closed',
    color: 'hsl(0, 0%, 70%)',
  },
} satisfies ChartConfig;

const dbPoolChartConfig = {
  used: {
    label: 'Used',
    color: 'hsl(210, 70%, 50%)',
  },
  free: {
    label: 'Free',
    color: 'hsl(150, 60%, 85%)',
  },
} satisfies ChartConfig;

const budgetChartConfig = {
  PostgreSQL: { label: 'PostgreSQL', color: VM_BUDGET[0].color },
  'Slack Bot': { label: 'Slack Bot', color: VM_BUDGET[1].color },
  'RAG Pipeline': { label: 'RAG Pipeline', color: VM_BUDGET[2].color },
  Frontend: { label: 'Frontend', color: VM_BUDGET[3].color },
} satisfies ChartConfig;

// ============================================================================
// Component
// ============================================================================

export function ResourceUsageDashboard() {
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState<number>(5000);
  const [snapshots, setSnapshots] = useState<ResourceSnapshot[]>([]);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const { metrics, loading: metricsLoading, error: metricsError, refetch: refetchMetrics } =
    useGatewayMetrics(undefined, false); // We control refresh ourselves
  const { instances, loading: instancesLoading, error: instancesError, refetch: refetchInstances } =
    useBrowserInstances(false); // We control refresh ourselves

  // Manual refresh
  const handleRefresh = useCallback(() => {
    refetchMetrics();
    refetchInstances();
  }, [refetchMetrics, refetchInstances]);

  // Auto-refresh with configurable interval
  useEffect(() => {
    // Always do an initial fetch
    handleRefresh();

    if (autoRefresh) {
      intervalRef.current = setInterval(handleRefresh, refreshInterval);
      return () => {
        if (intervalRef.current) clearInterval(intervalRef.current);
      };
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }
  }, [autoRefresh, refreshInterval, handleRefresh]);

  // Snapshot ring buffer: append snapshot when metrics change
  useEffect(() => {
    if (!metrics) return;

    const activeSessions = metrics.active_sessions ?? 0;
    const estimatedMemoryMB = activeSessions * MEM_PER_SESSION_MB;

    const browserActive = instances.filter(
      (i) => i.status === BrowserInstanceStatus.ACTIVE
    ).length;
    const browserIdle = instances.filter(
      (i) => i.status === BrowserInstanceStatus.IDLE
    ).length;
    const browserClosed = instances.filter(
      (i) => i.status === BrowserInstanceStatus.CLOSED
    ).length;
    const browserTotal = instances.length;

    const dbPoolUsed = Math.min(activeSessions, MAX_DB_POOL);
    const dbPoolFree = MAX_DB_POOL - dbPoolUsed;

    const now = new Date();
    const snapshot: ResourceSnapshot = {
      timestamp: now.toISOString(),
      label: now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }),
      estimatedMemoryMB,
      activeSessions,
      browserActive,
      browserIdle,
      browserClosed,
      browserTotal,
      dbPoolUsed,
      dbPoolFree,
    };

    setSnapshots((prev) => {
      const next = [...prev, snapshot];
      if (next.length > MAX_SNAPSHOTS) {
        return next.slice(next.length - MAX_SNAPSHOTS);
      }
      return next;
    });
  }, [metrics, instances]);

  // Current values for alerts
  const currentSnapshot = snapshots.length > 0 ? snapshots[snapshots.length - 1] : null;
  const memoryPercent = currentSnapshot
    ? (currentSnapshot.estimatedMemoryMB / VM_TOTAL_MB) * 100
    : 0;

  // Alert conditions
  const alerts = useMemo(() => {
    if (!currentSnapshot) return [];
    const result: Array<{ title: string; description: string; severity: 'warning' | 'destructive' }> = [];

    if (currentSnapshot.estimatedMemoryMB > VM_TOTAL_MB * VM_MEMORY_ALERT_THRESHOLD) {
      result.push({
        title: 'High Memory Usage',
        description: `Estimated memory usage is ${currentSnapshot.estimatedMemoryMB.toFixed(0)} MB (>${(VM_TOTAL_MB * VM_MEMORY_ALERT_THRESHOLD / 1024).toFixed(1)} GB threshold). Consider archiving idle sessions.`,
        severity: 'destructive',
      });
    }

    if (currentSnapshot.activeSessions > MAX_SESSIONS_ALERT) {
      result.push({
        title: 'High Session Count',
        description: `Active sessions (${currentSnapshot.activeSessions}) exceeds ${MAX_SESSIONS_ALERT}. Monitor for memory pressure.`,
        severity: 'warning',
      });
    }

    if (currentSnapshot.browserTotal >= MAX_BROWSER_INSTANCES) {
      result.push({
        title: 'Browser Instance Limit',
        description: `Browser instances (${currentSnapshot.browserTotal}) have reached the maximum of ${MAX_BROWSER_INSTANCES}. Close idle instances to free resources.`,
        severity: 'destructive',
      });
    }

    if (currentSnapshot.dbPoolUsed > DB_POOL_ALERT) {
      result.push({
        title: 'DB Connection Pool Near Limit',
        description: `Estimated pool usage (${currentSnapshot.dbPoolUsed}/${MAX_DB_POOL}) is nearing the connection limit.`,
        severity: 'warning',
      });
    }

    return result;
  }, [currentSnapshot]);

  // Browser instance bar chart data (latest snapshot)
  const browserBarData = useMemo(() => {
    if (!currentSnapshot) return [];
    return [
      { status: 'Active', count: currentSnapshot.browserActive },
      { status: 'Idle', count: currentSnapshot.browserIdle },
      { status: 'Closed', count: currentSnapshot.browserClosed },
    ];
  }, [currentSnapshot]);

  const loading = metricsLoading || instancesLoading;
  const error = metricsError || instancesError;

  return (
    <div className="space-y-4">
      {/* Controls */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5" />
                Resource Usage Dashboard
              </CardTitle>
              <CardDescription>
                Real-time resource monitoring ({snapshots.length} snapshots collected)
              </CardDescription>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Label htmlFor="resource-auto-refresh" className="text-sm">
                  Auto-refresh
                </Label>
                <Switch
                  id="resource-auto-refresh"
                  checked={autoRefresh}
                  onCheckedChange={setAutoRefresh}
                />
              </div>
              <Select
                value={String(refreshInterval)}
                onValueChange={(value) => setRefreshInterval(Number(value))}
              >
                <SelectTrigger className="w-[120px]">
                  <SelectValue placeholder="Interval" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="5000">5 seconds</SelectItem>
                  <SelectItem value="10000">10 seconds</SelectItem>
                  <SelectItem value="30000">30 seconds</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" onClick={handleRefresh} disabled={loading}>
                <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Error State */}
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error Loading Resource Data</AlertTitle>
          <AlertDescription>
            {error}
            <Button onClick={handleRefresh} className="mt-2" size="sm">
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {/* Alert Banners */}
      {alerts.map((alert, idx) => (
        <Alert key={idx} variant={alert.severity === 'destructive' ? 'destructive' : 'default'}>
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>{alert.title}</AlertTitle>
          <AlertDescription>{alert.description}</AlertDescription>
        </Alert>
      ))}

      {/* 2x2 Chart Grid */}
      <div className="grid gap-4 md:grid-cols-2">
        {/* 1. Memory AreaChart */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle className="text-sm font-medium">Estimated Memory Usage</CardTitle>
              <CardDescription className="text-xs">
                ~{MEM_PER_SESSION_MB} MB per active session
              </CardDescription>
            </div>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {snapshots.length === 0 ? (
              <div className="flex items-center justify-center h-[200px] text-sm text-muted-foreground">
                Waiting for data...
              </div>
            ) : (
              <>
                <div className="text-2xl font-bold mb-2">
                  {currentSnapshot?.estimatedMemoryMB.toFixed(0) ?? 0} MB
                  <span className="text-sm font-normal text-muted-foreground ml-2">
                    / {VM_TOTAL_MB} MB ({memoryPercent.toFixed(1)}%)
                  </span>
                </div>
                <ChartContainer config={memoryChartConfig} className="h-[200px] w-full">
                  <AreaChart data={snapshots} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 10 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 10 }}
                      domain={[0, VM_TOTAL_MB]}
                    />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Area
                      type="monotone"
                      dataKey="estimatedMemoryMB"
                      fill="var(--color-estimatedMemoryMB)"
                      fillOpacity={0.3}
                      stroke="var(--color-estimatedMemoryMB)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ChartContainer>
              </>
            )}
          </CardContent>
        </Card>

        {/* 2. Sessions LineChart */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle className="text-sm font-medium">Active Sessions</CardTitle>
              <CardDescription className="text-xs">
                Session count over time
              </CardDescription>
            </div>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {snapshots.length === 0 ? (
              <div className="flex items-center justify-center h-[200px] text-sm text-muted-foreground">
                Waiting for data...
              </div>
            ) : (
              <>
                <div className="text-2xl font-bold mb-2">
                  {currentSnapshot?.activeSessions ?? 0}
                  <span className="text-sm font-normal text-muted-foreground ml-2">
                    sessions
                  </span>
                </div>
                <ChartContainer config={sessionsChartConfig} className="h-[200px] w-full">
                  <LineChart data={snapshots} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 10 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 10 }} />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Line
                      type="monotone"
                      dataKey="activeSessions"
                      stroke="var(--color-activeSessions)"
                      strokeWidth={2}
                      dot={false}
                      activeDot={{ r: 4 }}
                    />
                  </LineChart>
                </ChartContainer>
              </>
            )}
          </CardContent>
        </Card>

        {/* 3. Browser Instances BarChart */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle className="text-sm font-medium">Browser Instances</CardTitle>
              <CardDescription className="text-xs">
                Count by status (max {MAX_BROWSER_INSTANCES})
              </CardDescription>
            </div>
            <Monitor className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {snapshots.length === 0 ? (
              <div className="flex items-center justify-center h-[200px] text-sm text-muted-foreground">
                Waiting for data...
              </div>
            ) : (
              <>
                <div className="text-2xl font-bold mb-2">
                  {currentSnapshot?.browserTotal ?? 0}
                  <span className="text-sm font-normal text-muted-foreground ml-2">
                    / {MAX_BROWSER_INSTANCES} instances
                  </span>
                </div>
                <ChartContainer config={browserChartConfig} className="h-[200px] w-full">
                  <BarChart data={browserBarData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis dataKey="status" tickLine={false} axisLine={false} />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 10 }}
                      domain={[0, MAX_BROWSER_INSTANCES + 1]}
                      allowDecimals={false}
                    />
                    <RechartsTooltip />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {browserBarData.map((entry, index) => {
                        const colors = [
                          browserChartConfig.active.color,
                          browserChartConfig.idle.color,
                          browserChartConfig.closed.color,
                        ];
                        return <Cell key={`cell-${index}`} fill={colors[index]} />;
                      })}
                    </Bar>
                    {/* Max limit reference line simulated with a horizontal bar */}
                  </BarChart>
                </ChartContainer>
                <div className="flex items-center justify-center gap-1 mt-1">
                  <div className="h-[2px] w-8 bg-red-500" />
                  <span className="text-xs text-red-500">Limit: {MAX_BROWSER_INSTANCES}</span>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* 4. DB Pool ComposedChart */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <div>
              <CardTitle className="text-sm font-medium">DB Connection Pool</CardTitle>
              <CardDescription className="text-xs">
                Estimated used vs free (max {MAX_DB_POOL})
              </CardDescription>
            </div>
            <Database className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {snapshots.length === 0 ? (
              <div className="flex items-center justify-center h-[200px] text-sm text-muted-foreground">
                Waiting for data...
              </div>
            ) : (
              <>
                <div className="text-2xl font-bold mb-2">
                  {currentSnapshot?.dbPoolUsed ?? 0}
                  <span className="text-sm font-normal text-muted-foreground ml-2">
                    / {MAX_DB_POOL} connections
                  </span>
                </div>
                <ChartContainer config={dbPoolChartConfig} className="h-[200px] w-full">
                  <ComposedChart
                    data={snapshots}
                    margin={{ top: 5, right: 10, left: 10, bottom: 5 }}
                  >
                    <CartesianGrid vertical={false} strokeDasharray="3 3" />
                    <XAxis
                      dataKey="label"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 10 }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tick={{ fontSize: 10 }}
                      domain={[0, MAX_DB_POOL]}
                    />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Area
                      type="monotone"
                      dataKey="dbPoolFree"
                      fill="var(--color-free)"
                      fillOpacity={0.2}
                      stroke="var(--color-free)"
                      strokeWidth={1}
                      stackId="pool"
                    />
                    <Area
                      type="monotone"
                      dataKey="dbPoolUsed"
                      fill="var(--color-used)"
                      fillOpacity={0.4}
                      stroke="var(--color-used)"
                      strokeWidth={2}
                      stackId="pool"
                    />
                  </ComposedChart>
                </ChartContainer>
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* VM Budget PieChart */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Server className="h-4 w-4" />
            VM Memory Budget (4 GB Total)
          </CardTitle>
          <CardDescription>
            Static allocation per container as defined in docker-compose.yml
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col md:flex-row items-center gap-6">
            <ChartContainer config={budgetChartConfig} className="h-[250px] w-[300px]">
              <PieChart>
                <Pie
                  data={VM_BUDGET}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  paddingAngle={2}
                  dataKey="value"
                  nameKey="name"
                  label={({ name, value }) => `${name}: ${value} MB`}
                  labelLine={false}
                >
                  {VM_BUDGET.map((entry, index) => (
                    <Cell key={`budget-${index}`} fill={entry.color} />
                  ))}
                </Pie>
                <RechartsTooltip
                  formatter={(value: number, name: string) => [`${value} MB`, name]}
                />
              </PieChart>
            </ChartContainer>
            <div className="space-y-3 flex-1">
              {VM_BUDGET.map((item) => (
                <div key={item.name} className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: item.color }}
                    />
                    <span className="text-sm">{item.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">{item.value} MB</span>
                    <Badge variant="outline" className="text-xs">
                      {((item.value / VM_TOTAL_MB) * 100).toFixed(0)}%
                    </Badge>
                  </div>
                </div>
              ))}
              <div className="border-t pt-2 flex items-center justify-between">
                <span className="text-sm font-medium">Total</span>
                <span className="text-sm font-bold">
                  {VM_BUDGET.reduce((s, i) => s + i.value, 0)} MB / {VM_TOTAL_MB} MB
                </span>
              </div>
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
