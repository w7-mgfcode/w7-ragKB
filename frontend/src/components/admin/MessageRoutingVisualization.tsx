/**
 * Message Routing Visualization Component
 *
 * Displays message flow across channels using a horizontal stacked bar chart.
 * Features:
 * - Horizontal stacked BarChart showing message flow per channel
 * - Bars stacked by session type (main/group/webhook)
 * - CSS shimmer animation on bars when auto-refresh detects changes
 * - Time range selector and auto-refresh toggle
 * - Loading and empty states
 */

import { useState, useEffect, useRef, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
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
import { BarChart, Bar, CartesianGrid, XAxis, YAxis, Legend } from 'recharts';
import { ArrowRightLeft, RefreshCw } from 'lucide-react';
import { useGatewayMetrics, useSessions } from '@/hooks/useGateway';
import { MetricsTimeRange, SessionType } from '@/types/gateway';
import type { Session } from '@/types/gateway';

const SESSION_TYPE_COLORS: Record<string, string> = {
  main: 'hsl(210, 70%, 50%)',
  group: 'hsl(150, 60%, 45%)',
  webhook: 'hsl(35, 80%, 50%)',
};

const chartConfig = {
  main: {
    label: 'Main',
    color: SESSION_TYPE_COLORS.main,
  },
  group: {
    label: 'Group',
    color: SESSION_TYPE_COLORS.group,
  },
  webhook: {
    label: 'Webhook',
    color: SESSION_TYPE_COLORS.webhook,
  },
} satisfies ChartConfig;

interface ChannelFlowData {
  channel: string;
  main: number;
  group: number;
  webhook: number;
  total: number;
}

export function MessageRoutingVisualization() {
  const [timeRange, setTimeRange] = useState<MetricsTimeRange>(MetricsTimeRange.LAST_HOUR);
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [hasChanges, setHasChanges] = useState(false);
  const prevTimestampRef = useRef<string | null>(null);

  const { metrics, loading: metricsLoading, error: metricsError, refetch: refetchMetrics } =
    useGatewayMetrics(timeRange, autoRefresh);
  const { sessions, loading: sessionsLoading, error: sessionsError, refetch: refetchSessions } =
    useSessions(undefined, autoRefresh);

  // Detect changes for shimmer animation
  useEffect(() => {
    if (metrics?.timestamp && prevTimestampRef.current) {
      if (metrics.timestamp !== prevTimestampRef.current) {
        setHasChanges(true);
        const timeout = setTimeout(() => setHasChanges(false), 1500);
        return () => clearTimeout(timeout);
      }
    }
    if (metrics?.timestamp) {
      prevTimestampRef.current = metrics.timestamp;
    }
  }, [metrics?.timestamp]);

  // Build chart data: group sessions by channel, count by type
  const chartData: ChannelFlowData[] = useMemo(() => {
    if (!metrics) return [];

    const channels = Object.keys(metrics.messages_per_channel);
    if (channels.length === 0) return [];

    // Group sessions by channel
    const channelSessionCounts: Record<
      string,
      { main: number; group: number; webhook: number }
    > = {};

    for (const channel of channels) {
      channelSessionCounts[channel] = { main: 0, group: 0, webhook: 0 };
    }

    for (const session of sessions) {
      const ch = session.channel_id;
      if (!channelSessionCounts[ch]) {
        channelSessionCounts[ch] = { main: 0, group: 0, webhook: 0 };
      }

      const msgCount = session.message_count || 0;

      switch (session.session_type) {
        case SessionType.MAIN:
          channelSessionCounts[ch].main += msgCount;
          break;
        case SessionType.GROUP:
          channelSessionCounts[ch].group += msgCount;
          break;
        case SessionType.WEBHOOK:
          channelSessionCounts[ch].webhook += msgCount;
          break;
        default:
          channelSessionCounts[ch].main += msgCount;
      }
    }

    // For channels from metrics that had no sessions, use the total messages as 'main'
    for (const channel of channels) {
      const counts = channelSessionCounts[channel];
      const totalFromSessions = counts.main + counts.group + counts.webhook;
      const totalFromMetrics = metrics.messages_per_channel[channel] || 0;

      if (totalFromSessions === 0 && totalFromMetrics > 0) {
        counts.main = totalFromMetrics;
      }
    }

    return Object.entries(channelSessionCounts)
      .map(([channel, counts]) => ({
        channel,
        main: counts.main,
        group: counts.group,
        webhook: counts.webhook,
        total: counts.main + counts.group + counts.webhook,
      }))
      .sort((a, b) => b.total - a.total);
  }, [metrics, sessions]);

  // Summary stats
  const totalMessages = useMemo(() => {
    return chartData.reduce((sum, d) => sum + d.total, 0);
  }, [chartData]);

  const sessionTypeSummary = useMemo(() => {
    const summary = { main: 0, group: 0, webhook: 0 };
    for (const d of chartData) {
      summary.main += d.main;
      summary.group += d.group;
      summary.webhook += d.webhook;
    }
    return summary;
  }, [chartData]);

  const loading = metricsLoading || sessionsLoading;
  const error = metricsError || sessionsError;

  const handleRefresh = () => {
    refetchMetrics();
    refetchSessions();
  };

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Message Routing</CardTitle>
          <CardDescription>Message flow visualization across channels</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-12 text-destructive">
            <p>Error: {error}</p>
            <Button onClick={handleRefresh} className="mt-4" size="sm">
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Shimmer animation style */}
      <style>{`
        @keyframes shimmer {
          0% { opacity: 1; }
          50% { opacity: 0.7; }
          100% { opacity: 1; }
        }
        .chart-shimmer .recharts-bar-rectangle {
          animation: shimmer 1.5s ease-in-out;
        }
      `}</style>

      {/* Controls */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ArrowRightLeft className="h-5 w-5" />
                Message Routing Visualization
              </CardTitle>
              <CardDescription>
                Message flow across channels by session type
              </CardDescription>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                <Label htmlFor="routing-auto-refresh" className="text-sm">
                  Auto-refresh
                </Label>
                <Switch
                  id="routing-auto-refresh"
                  checked={autoRefresh}
                  onCheckedChange={setAutoRefresh}
                />
              </div>
              <Select
                value={timeRange}
                onValueChange={(value) => setTimeRange(value as MetricsTimeRange)}
              >
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Select time range" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={MetricsTimeRange.LAST_HOUR}>Last Hour</SelectItem>
                  <SelectItem value={MetricsTimeRange.LAST_24H}>Last 24 Hours</SelectItem>
                  <SelectItem value={MetricsTimeRange.LAST_7D}>Last 7 Days</SelectItem>
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

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{loading ? '...' : totalMessages}</div>
            <p className="text-xs text-muted-foreground">Across all channels</p>
          </CardContent>
        </Card>
        {Object.entries(sessionTypeSummary).map(([type, count]) => (
          <Card key={type}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium capitalize">{type}</CardTitle>
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: SESSION_TYPE_COLORS[type] }}
              />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{loading ? '...' : count}</div>
              <p className="text-xs text-muted-foreground">
                {totalMessages > 0
                  ? `${((count / totalMessages) * 100).toFixed(1)}% of total`
                  : 'No messages'}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Chart */}
      <Card>
        <CardHeader>
          <CardTitle>Channel Message Flow</CardTitle>
          <CardDescription>
            Horizontal stacked bars showing message distribution by session type
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-8 w-8 text-muted-foreground animate-spin" />
              <p className="ml-2 text-sm text-muted-foreground">Loading message flow data...</p>
            </div>
          ) : chartData.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <ArrowRightLeft className="h-8 w-8 text-muted-foreground" />
              <p className="text-muted-foreground">No message routing data available.</p>
            </div>
          ) : (
            <div className={hasChanges ? 'chart-shimmer' : ''}>
              <ChartContainer
                config={chartConfig}
                className="min-h-[300px] w-full"
              >
                <BarChart
                  accessibilityLayer
                  data={chartData}
                  layout="vertical"
                  margin={{ top: 10, right: 30, left: 20, bottom: 10 }}
                >
                  <CartesianGrid horizontal={false} />
                  <XAxis type="number" tickLine={false} axisLine={false} />
                  <YAxis
                    type="category"
                    dataKey="channel"
                    tickLine={false}
                    axisLine={false}
                    width={120}
                    tick={{ fontSize: 12 }}
                  />
                  <ChartTooltip content={<ChartTooltipContent />} />
                  <Legend />
                  <Bar
                    dataKey="main"
                    stackId="messages"
                    fill="var(--color-main)"
                    radius={[0, 0, 0, 0]}
                    name="Main"
                  />
                  <Bar
                    dataKey="group"
                    stackId="messages"
                    fill="var(--color-group)"
                    radius={[0, 0, 0, 0]}
                    name="Group"
                  />
                  <Bar
                    dataKey="webhook"
                    stackId="messages"
                    fill="var(--color-webhook)"
                    radius={[4, 4, 4, 4]}
                    name="Webhook"
                  />
                </BarChart>
              </ChartContainer>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Channel Details */}
      {!loading && chartData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Channel Breakdown</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
              {chartData.map((item) => (
                <div
                  key={item.channel}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div>
                    <p className="text-sm font-medium">{item.channel}</p>
                    <div className="flex items-center gap-2 mt-1">
                      <Badge variant="outline" className="text-xs" style={{ borderColor: SESSION_TYPE_COLORS.main }}>
                        Main: {item.main}
                      </Badge>
                      <Badge variant="outline" className="text-xs" style={{ borderColor: SESSION_TYPE_COLORS.group }}>
                        Group: {item.group}
                      </Badge>
                      <Badge variant="outline" className="text-xs" style={{ borderColor: SESSION_TYPE_COLORS.webhook }}>
                        Webhook: {item.webhook}
                      </Badge>
                    </div>
                  </div>
                  <span className="text-lg font-bold">{item.total}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
