/**
 * Enhanced Gateway Metrics Dashboard Component
 * 
 * Displays detailed real-time metrics for the OpenClaw multi-channel gateway:
 * - Messages per channel (bar chart)
 * - Active sessions gauge
 * - Queue depth gauge with color-coded alerts
 * - Channel health grid with status badges
 * - Time range selector
 * - Auto-refresh toggle
 * - CSV export functionality
 * 
 * Requirements: 14.7
 */

import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from '@/components/ui/chart';
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from 'recharts';
import { Download, Activity, Layers, AlertCircle, GitBranch, Flame } from 'lucide-react';
import { useGatewayMetrics } from '@/hooks/useGateway';
import { MetricsTimeRange, ChannelStatus } from '@/types/gateway';
import { MessageRoutingVisualization } from './MessageRoutingVisualization';
import { ChannelActivityHeatmap } from './ChannelActivityHeatmap';

export function GatewayMetrics() {
  const [timeRange, setTimeRange] = useState<MetricsTimeRange>(MetricsTimeRange.LAST_HOUR);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [refreshInterval, setRefreshInterval] = useState<NodeJS.Timeout | null>(null);

  const { metrics, loading, error, refetch } = useGatewayMetrics(timeRange, autoRefresh);

  // Manual refresh when auto-refresh is disabled
  useEffect(() => {
    if (!autoRefresh) {
      if (refreshInterval) {
        clearInterval(refreshInterval);
        setRefreshInterval(null);
      }
    }
  }, [autoRefresh, refreshInterval]);

  // Prepare chart data for messages per channel
  const chartData = Object.entries(metrics?.messages_per_channel ?? {}).map(([channelId, count]) => ({
    channel: channelId,
    messages: count,
  }));

  const chartConfig = {
    messages: {
      label: 'Messages',
      color: 'hsl(var(--chart-1))',
    },
  } satisfies ChartConfig;

  // Calculate queue depth color and percentage
  const getQueueDepthColor = (depth: number): string => {
    if (depth < 10) return 'bg-green-500';
    if (depth < 50) return 'bg-yellow-500';
    return 'bg-red-500';
  };

  const getQueueDepthPercentage = (depth: number): number => {
    // Normalize to 0-100 scale (assuming max queue depth of 100)
    return Math.min((depth / 100) * 100, 100);
  };

  const getChannelStatusVariant = (status: ChannelStatus): 'default' | 'secondary' | 'destructive' => {
    switch (status) {
      case ChannelStatus.CONNECTED:
        return 'default';
      case ChannelStatus.ERROR:
        return 'destructive';
      case ChannelStatus.DISCONNECTED:
        return 'secondary';
      default:
        return 'secondary';
    }
  };

  // CSV export functionality
  const exportToCSV = useCallback(() => {
    if (!metrics) return;

    const csvRows = [
      ['Metric', 'Value'],
      ['Active Sessions', metrics.active_sessions.toString()],
      ['Queue Depth', metrics.queue_depth.toString()],
      ['Timestamp', metrics.timestamp],
      [''],
      ['Channel', 'Messages', 'Status'],
    ];

    Object.entries(metrics.messages_per_channel).forEach(([channelId, count]) => {
      const status = metrics.channel_health[channelId] || 'unknown';
      csvRows.push([channelId, count.toString(), status]);
    });

    const csvContent = csvRows.map((row) => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `gateway-metrics-${new Date().toISOString()}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  }, [metrics]);

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-5 w-5" />
        <AlertTitle>Error Loading Gateway Metrics</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>Unable to fetch metrics data from the backend.</p>
          <p className="text-sm">Error: {error}</p>
          <p className="text-sm mt-2">Required endpoint: <code className="bg-muted px-1 py-0.5 rounded">/api/gateway/metrics</code></p>
          <Button onClick={refetch} className="mt-4" size="sm">
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="space-y-6">
      {/* Controls */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Gateway Metrics Dashboard</CardTitle>
              <CardDescription>Real-time monitoring of multi-channel gateway performance</CardDescription>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Label htmlFor="auto-refresh" className="text-sm">
                  Auto-refresh
                </Label>
                <Switch
                  id="auto-refresh"
                  checked={autoRefresh}
                  onCheckedChange={setAutoRefresh}
                />
              </div>
              <Select value={timeRange} onValueChange={(value) => setTimeRange(value as MetricsTimeRange)}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Select time range" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={MetricsTimeRange.LAST_HOUR}>Last Hour</SelectItem>
                  <SelectItem value={MetricsTimeRange.LAST_24H}>Last 24 Hours</SelectItem>
                  <SelectItem value={MetricsTimeRange.LAST_7D}>Last 7 Days</SelectItem>
                </SelectContent>
              </Select>
              <Button onClick={exportToCSV} variant="outline" size="sm" disabled={!metrics}>
                <Download className="h-4 w-4 mr-2" />
                Export CSV
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Metrics Tabs */}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList>
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="channels">Channels</TabsTrigger>
          <TabsTrigger value="performance">Performance</TabsTrigger>
          <TabsTrigger value="routing" className="flex items-center gap-1">
            <GitBranch className="h-3 w-3" />
            Routing
          </TabsTrigger>
          <TabsTrigger value="activity" className="flex items-center gap-1">
            <Flame className="h-3 w-3" />
            Activity
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            {/* Active Sessions Gauge */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Active Sessions</CardTitle>
                <Layers className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {loading ? '...' : metrics?.active_sessions ?? 0}
                </div>
                <Progress
                  value={((metrics?.active_sessions ?? 0) / 100) * 100}
                  className="mt-2"
                />
                <p className="text-xs text-muted-foreground mt-2">
                  Concurrent conversation contexts
                </p>
              </CardContent>
            </Card>

            {/* Queue Depth Gauge */}
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Queue Depth</CardTitle>
                <Activity className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {loading ? '...' : metrics?.queue_depth ?? 0}
                </div>
                <div className="mt-2">
                  <Progress
                    value={getQueueDepthPercentage(metrics?.queue_depth ?? 0)}
                    className={getQueueDepthColor(metrics?.queue_depth ?? 0)}
                  />
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  {(metrics?.queue_depth ?? 0) < 10 && 'Healthy - Low queue depth'}
                  {(metrics?.queue_depth ?? 0) >= 10 && (metrics?.queue_depth ?? 0) < 50 && 'Warning - Moderate queue depth'}
                  {(metrics?.queue_depth ?? 0) >= 50 && 'Critical - High queue depth'}
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Channel Health Grid */}
          <Card>
            <CardHeader>
              <CardTitle>Channel Health</CardTitle>
              <CardDescription>Status of all connected messaging platforms</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading...</p>
              ) : Object.keys(metrics?.channel_health ?? {}).length === 0 ? (
                <p className="text-sm text-muted-foreground">No channels configured</p>
              ) : (
                <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
                  {Object.entries(metrics?.channel_health ?? {}).map(([channelId, status]) => (
                    <div
                      key={channelId}
                      className="flex items-center justify-between rounded-lg border p-3"
                    >
                      <div className="flex flex-col">
                        <span className="text-sm font-medium">{channelId}</span>
                        <span className="text-xs text-muted-foreground">
                          {metrics?.messages_per_channel[channelId] ?? 0} messages
                        </span>
                      </div>
                      <Badge variant={getChannelStatusVariant(status)}>
                        {status}
                      </Badge>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="channels" className="space-y-4">
          {/* Messages Per Channel Chart */}
          <Card>
            <CardHeader>
              <CardTitle>Messages Per Channel</CardTitle>
              <CardDescription>Message volume across all channels</CardDescription>
            </CardHeader>
            <CardContent>
              {loading ? (
                <p className="text-sm text-muted-foreground">Loading...</p>
              ) : chartData.length === 0 ? (
                <p className="text-sm text-muted-foreground">No data available</p>
              ) : (
                <ChartContainer config={chartConfig} className="min-h-[300px] w-full">
                  <BarChart accessibilityLayer data={chartData}>
                    <CartesianGrid vertical={false} />
                    <XAxis
                      dataKey="channel"
                      tickLine={false}
                      tickMargin={10}
                      axisLine={false}
                    />
                    <YAxis
                      tickLine={false}
                      axisLine={false}
                      tickMargin={10}
                    />
                    <ChartTooltip content={<ChartTooltipContent />} />
                    <Bar dataKey="messages" fill="var(--color-messages)" radius={4} />
                  </BarChart>
                </ChartContainer>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="performance" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {loading
                    ? '...'
                    : Object.values(metrics?.messages_per_channel ?? {}).reduce(
                        (a: number, b: number) => a + b,
                        0
                      )}
                </div>
                <p className="text-xs text-muted-foreground">
                  Across all channels
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Connected Channels</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {loading
                    ? '...'
                    : Object.values(metrics?.channel_health ?? {}).filter(
                        (status) => status === ChannelStatus.CONNECTED
                      ).length}
                </div>
                <p className="text-xs text-muted-foreground">
                  Out of {Object.keys(metrics?.channel_health ?? {}).length} total
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Last Updated</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-sm font-medium">
                  {loading
                    ? '...'
                    : metrics?.timestamp
                    ? new Date(metrics.timestamp).toLocaleTimeString()
                    : 'N/A'}
                </div>
                <p className="text-xs text-muted-foreground">
                  {autoRefresh ? 'Auto-refreshing every 5s' : 'Auto-refresh disabled'}
                </p>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="routing" className="space-y-4">
          <MessageRoutingVisualization />
        </TabsContent>

        <TabsContent value="activity" className="space-y-4">
          <ChannelActivityHeatmap />
        </TabsContent>
      </Tabs>
    </div>
  );
}
