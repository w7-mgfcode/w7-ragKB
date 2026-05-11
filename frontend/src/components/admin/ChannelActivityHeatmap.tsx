/**
 * Channel Activity Heatmap Component
 *
 * 7x24 CSS Grid heatmap showing message activity by day of week and hour.
 * Features:
 * - Aggregates session timestamps into a 7x24 grid (Mon-Sun, 0-23 hours)
 * - HSL color scaling from low to high activity
 * - CSS Grid layout with proper day/hour labels
 * - Channel filter dropdown
 * - Time range selector (last 7 days / 30 days)
 * - Tooltip on hover showing exact count
 * - Peak hour summary stat card
 */

import { useState, useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
  TooltipProvider,
} from '@/components/ui/tooltip';
import { CalendarDays, RefreshCw, TrendingUp } from 'lucide-react';
import { useSessions } from '@/hooks/useGateway';
import { getDay, getHours, subDays, startOfDay } from 'date-fns';

// ============================================================================
// Constants
// ============================================================================

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const HOURS = Array.from({ length: 24 }, (_, i) => i);

// Map getDay() (0=Sun..6=Sat) to our Monday-first ordering (0=Mon..6=Sun)
function toMondayIndex(jsDay: number): number {
  return jsDay === 0 ? 6 : jsDay - 1;
}

function getCellColor(count: number, maxCount: number): string {
  if (count === 0 || maxCount === 0) return 'hsl(210, 20%, 95%)';
  const ratio = Math.min(count / maxCount, 1);
  // Interpolate from low (light) to high (dark blue)
  const lightness = 95 - ratio * 55; // 95% -> 40%
  const saturation = 20 + ratio * 60; // 20% -> 80%
  return `hsl(210, ${saturation}%, ${lightness}%)`;
}

function getTextColor(count: number, maxCount: number): string {
  if (maxCount === 0) return 'hsl(210, 20%, 40%)';
  const ratio = count / maxCount;
  return ratio > 0.5 ? 'white' : 'hsl(210, 20%, 30%)';
}

// ============================================================================
// Component
// ============================================================================

export function ChannelActivityHeatmap() {
  const [channelFilter, setChannelFilter] = useState<string>('all');
  const [timeRange, setTimeRange] = useState<number>(7); // days
  const { sessions, loading, error, refetch } = useSessions(undefined, false);

  // Get unique channels for filter
  const channels = useMemo(() => {
    const channelSet = new Set<string>();
    for (const session of sessions) {
      if (session.channel_id) channelSet.add(session.channel_id);
    }
    return Array.from(channelSet).sort();
  }, [sessions]);

  // Filter sessions by channel and time range
  const filteredSessions = useMemo(() => {
    const cutoff = startOfDay(subDays(new Date(), timeRange));

    return sessions.filter((session) => {
      if (channelFilter !== 'all' && session.channel_id !== channelFilter) return false;
      const activityDate = new Date(session.last_activity_at);
      return activityDate >= cutoff;
    });
  }, [sessions, channelFilter, timeRange]);

  // Build 7x24 grid data
  const gridData = useMemo(() => {
    // Initialize grid: grid[dayIndex][hour] = count
    const grid: number[][] = Array.from({ length: 7 }, () => Array(24).fill(0));

    for (const session of filteredSessions) {
      const activityDate = new Date(session.last_activity_at);
      const dayIndex = toMondayIndex(getDay(activityDate));
      const hour = getHours(activityDate);
      // Use message_count as a weight; if 0, count as 1 activity
      const weight = Math.max(session.message_count, 1);
      grid[dayIndex][hour] += weight;
    }

    return grid;
  }, [filteredSessions]);

  // Compute max value for color scaling
  const maxCount = useMemo(() => {
    let max = 0;
    for (const row of gridData) {
      for (const val of row) {
        if (val > max) max = val;
      }
    }
    return max;
  }, [gridData]);

  // Total activity
  const totalActivity = useMemo(() => {
    let total = 0;
    for (const row of gridData) {
      for (const val of row) {
        total += val;
      }
    }
    return total;
  }, [gridData]);

  // Average per cell
  const avgActivity = useMemo(() => {
    return totalActivity / (7 * 24);
  }, [totalActivity]);

  // Find peak hour
  const peak = useMemo(() => {
    let peakDay = 0;
    let peakHour = 0;
    let peakVal = 0;

    for (let d = 0; d < 7; d++) {
      for (let h = 0; h < 24; h++) {
        if (gridData[d][h] > peakVal) {
          peakVal = gridData[d][h];
          peakDay = d;
          peakHour = h;
        }
      }
    }

    return { day: DAYS[peakDay], hour: peakHour, count: peakVal };
  }, [gridData]);

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Channel Activity Heatmap</CardTitle>
          <CardDescription>Message activity by day and hour</CardDescription>
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
      {/* Controls */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <CalendarDays className="h-5 w-5" />
                Channel Activity Heatmap
              </CardTitle>
              <CardDescription>
                Message activity distribution by day of week and hour
              </CardDescription>
            </div>
            <div className="flex items-center gap-3">
              <Select value={channelFilter} onValueChange={setChannelFilter}>
                <SelectTrigger className="w-[180px]">
                  <SelectValue placeholder="Filter by channel" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Channels</SelectItem>
                  {channels.map((ch) => (
                    <SelectItem key={ch} value={ch}>
                      {ch}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={String(timeRange)}
                onValueChange={(v) => setTimeRange(Number(v))}
              >
                <SelectTrigger className="w-[150px]">
                  <SelectValue placeholder="Time range" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="7">Last 7 days</SelectItem>
                  <SelectItem value="30">Last 30 days</SelectItem>
                </SelectContent>
              </Select>
              <Button variant="outline" size="sm" onClick={refetch} disabled={loading}>
                <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
      </Card>

      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Activity</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{loading ? '...' : totalActivity}</div>
            <p className="text-xs text-muted-foreground">
              Messages in last {timeRange} days
              {channelFilter !== 'all' ? ` (${channelFilter})` : ''}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Average Per Slot</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{loading ? '...' : avgActivity.toFixed(1)}</div>
            <p className="text-xs text-muted-foreground">Messages per day/hour slot</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Peak Activity</CardTitle>
            <TrendingUp className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{loading ? '...' : peak.count}</div>
            <p className="text-xs text-muted-foreground">
              Peak: {peak.day} {peak.hour}:00, avg {avgActivity.toFixed(0)} messages
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Heatmap */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Activity Grid</CardTitle>
          <CardDescription>Rows = days (Mon-Sun), Columns = hours (0-23)</CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <RefreshCw className="h-8 w-8 text-muted-foreground animate-spin" />
              <p className="ml-2 text-sm text-muted-foreground">Loading activity data...</p>
            </div>
          ) : filteredSessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 gap-2">
              <CalendarDays className="h-8 w-8 text-muted-foreground" />
              <p className="text-muted-foreground">No activity data available for the selected filters.</p>
            </div>
          ) : (
            <TooltipProvider>
              <div className="overflow-x-auto">
                {/* Hour labels */}
                <div
                  className="grid gap-[2px] mb-1"
                  style={{
                    gridTemplateColumns: '60px repeat(24, minmax(28px, 1fr))',
                  }}
                >
                  <div /> {/* Empty corner cell */}
                  {HOURS.map((hour) => (
                    <div
                      key={`h-${hour}`}
                      className="text-center text-xs text-muted-foreground font-medium"
                    >
                      {hour}
                    </div>
                  ))}
                </div>

                {/* Grid rows */}
                {DAYS.map((day, dayIndex) => (
                  <div
                    key={day}
                    className="grid gap-[2px] mb-[2px]"
                    style={{
                      gridTemplateColumns: '60px repeat(24, minmax(28px, 1fr))',
                    }}
                  >
                    {/* Day label */}
                    <div className="flex items-center text-xs font-medium text-muted-foreground pr-2 justify-end">
                      {day}
                    </div>

                    {/* Hour cells */}
                    {HOURS.map((hour) => {
                      const count = gridData[dayIndex][hour];
                      return (
                        <Tooltip key={`${dayIndex}-${hour}`}>
                          <TooltipTrigger asChild>
                            <div
                              className="rounded-sm flex items-center justify-center text-[10px] font-medium cursor-default transition-all hover:ring-2 hover:ring-ring hover:ring-offset-1"
                              style={{
                                backgroundColor: getCellColor(count, maxCount),
                                color: getTextColor(count, maxCount),
                                minHeight: '28px',
                              }}
                              title={`${day} ${hour}:00 - ${count} messages`}
                            >
                              {count > 0 ? count : ''}
                            </div>
                          </TooltipTrigger>
                          <TooltipContent>
                            <div className="text-xs">
                              <p className="font-medium">
                                {day} {String(hour).padStart(2, '0')}:00 -{' '}
                                {String(hour).padStart(2, '0')}:59
                              </p>
                              <p>
                                {count} message{count !== 1 ? 's' : ''}
                              </p>
                              {count > 0 && maxCount > 0 && (
                                <p className="text-muted-foreground">
                                  {((count / maxCount) * 100).toFixed(0)}% of peak
                                </p>
                              )}
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      );
                    })}
                  </div>
                ))}
              </div>
            </TooltipProvider>
          )}

          {/* Color Legend */}
          {!loading && filteredSessions.length > 0 && (
            <div className="flex items-center gap-3 mt-4 pt-3 border-t">
              <span className="text-xs text-muted-foreground">Less</span>
              <div className="flex gap-[2px]">
                {[0, 0.2, 0.4, 0.6, 0.8, 1].map((ratio) => (
                  <div
                    key={ratio}
                    className="w-6 h-4 rounded-sm"
                    style={{ backgroundColor: getCellColor(ratio * maxCount, maxCount) }}
                  />
                ))}
              </div>
              <span className="text-xs text-muted-foreground">More</span>
              <span className="text-xs text-muted-foreground ml-2">
                (max: {maxCount} messages)
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Active Channels */}
      {!loading && channels.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Active Channels</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {channels.map((ch) => {
                const sessionCount = sessions.filter((s) => s.channel_id === ch).length;
                return (
                  <Badge
                    key={ch}
                    variant={channelFilter === ch ? 'default' : 'outline'}
                    className="cursor-pointer"
                    onClick={() =>
                      setChannelFilter(channelFilter === ch ? 'all' : ch)
                    }
                  >
                    {ch} ({sessionCount})
                  </Badge>
                );
              })}
              {channelFilter !== 'all' && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setChannelFilter('all')}
                  className="text-xs h-6"
                >
                  Clear filter
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
