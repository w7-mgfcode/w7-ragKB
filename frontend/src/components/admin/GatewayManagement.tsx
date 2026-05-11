/**
 * Gateway Management Component
 * 
 * Main container for OpenClaw multi-channel gateway features.
 * Provides tabbed interface for managing:
 * - Channels: Messaging platform integrations
 * - Sessions: Conversation contexts
 * - Webhooks: HTTP trigger endpoints
 * - Cron Jobs: Scheduled tasks
 * 
 * Also displays real-time gateway metrics at the top.
 */

import { useState } from 'react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Activity, MessageSquare, Layers, Webhook, Clock, BarChart3, AlertCircle, Monitor, Server, GitBranch } from 'lucide-react';
import { useGatewayMetrics } from '@/hooks/useGateway';
import { ChannelsTable } from './ChannelsTable';
import { SessionsTable } from './SessionsTable';
import { WebhooksTable } from './WebhooksTable';
import { CronJobsTable } from './CronJobsTable';
import { GatewayMetrics } from './GatewayMetrics';
import { BrowserInstanceMonitor } from './BrowserInstanceMonitor';
import { ResourceUsageDashboard } from './ResourceUsageDashboard';
import { SessionRelationshipGraph } from './SessionRelationshipGraph';

export function GatewayManagement() {
  const [activeTab, setActiveTab] = useState('metrics');
  const { metrics, loading: metricsLoading, error: metricsError } = useGatewayMetrics(undefined, true);

  // Show error alert if API endpoints are not available
  if (metricsError) {
    return (
      <div className="space-y-6">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Gateway API Not Available</AlertTitle>
          <AlertDescription className="mt-2 space-y-2">
            <p>The Gateway endpoints are not yet implemented. Backend API endpoints required:</p>
            <ul className="list-disc list-inside mt-2 space-y-1 text-sm">
              <li><code className="bg-muted px-1 py-0.5 rounded">/api/gateway/channels</code></li>
              <li><code className="bg-muted px-1 py-0.5 rounded">/api/gateway/sessions</code></li>
              <li><code className="bg-muted px-1 py-0.5 rounded">/api/gateway/webhooks</code></li>
              <li><code className="bg-muted px-1 py-0.5 rounded">/api/gateway/cron-jobs</code></li>
              <li><code className="bg-muted px-1 py-0.5 rounded">/api/gateway/metrics</code></li>
            </ul>
            <p className="mt-2 text-sm">Error details: {metricsError}</p>
          </AlertDescription>
        </Alert>
        
        {/* Keep the tab structure visible but disabled */}
        <Card>
          <CardHeader>
            <CardTitle>Gateway Management</CardTitle>
            <CardDescription>
              Manage multi-channel messaging, sessions, webhooks, and scheduled tasks
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Tabs value={activeTab} onValueChange={setActiveTab}>
              <TabsList className="grid w-full grid-cols-8">
                <TabsTrigger value="metrics" disabled className="flex items-center gap-2">
                  <BarChart3 className="h-4 w-4" />
                  Metrics
                </TabsTrigger>
                <TabsTrigger value="channels" disabled className="flex items-center gap-2">
                  <MessageSquare className="h-4 w-4" />
                  Channels
                </TabsTrigger>
                <TabsTrigger value="sessions" disabled className="flex items-center gap-2">
                  <Layers className="h-4 w-4" />
                  Sessions
                </TabsTrigger>
                <TabsTrigger value="webhooks" disabled className="flex items-center gap-2">
                  <Webhook className="h-4 w-4" />
                  Webhooks
                </TabsTrigger>
                <TabsTrigger value="cron-jobs" disabled className="flex items-center gap-2">
                  <Clock className="h-4 w-4" />
                  Cron Jobs
                </TabsTrigger>
                <TabsTrigger value="browser" disabled className="flex items-center gap-2">
                  <Monitor className="h-4 w-4" />
                  Browser
                </TabsTrigger>
                <TabsTrigger value="resources" disabled className="flex items-center gap-2">
                  <Server className="h-4 w-4" />
                  Resources
                </TabsTrigger>
                <TabsTrigger value="graph" disabled className="flex items-center gap-2">
                  <GitBranch className="h-4 w-4" />
                  Graph
                </TabsTrigger>
              </TabsList>
            </Tabs>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Gateway Metrics Cards */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Active Sessions</CardTitle>
            <Layers className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsLoading ? '...' : metrics?.active_sessions ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Concurrent conversation contexts
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Queue Depth</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsLoading ? '...' : metrics?.queue_depth ?? 0}
            </div>
            <p className="text-xs text-muted-foreground">
              Pending messages in queue
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Messages</CardTitle>
            <MessageSquare className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {metricsLoading
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
            <CardTitle className="text-sm font-medium">Channel Health</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="flex gap-2">
              {metricsLoading ? (
                <span className="text-sm">Loading...</span>
              ) : (
                <>
                  {Object.entries(metrics?.channel_health ?? {}).map(([channelId, status]) => (
                    <Badge
                      key={channelId}
                      variant={
                        status === 'connected'
                          ? 'default'
                          : status === 'error'
                          ? 'destructive'
                          : 'secondary'
                      }
                    >
                      {channelId.split('-')[0]}
                    </Badge>
                  ))}
                  {Object.keys(metrics?.channel_health ?? {}).length === 0 && (
                    <span className="text-sm text-muted-foreground">No channels</span>
                  )}
                </>
              )}
            </div>
            <p className="text-xs text-muted-foreground mt-1">
              Active channel status
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Gateway Management Tabs */}
      <Card>
        <CardHeader>
          <CardTitle>Gateway Management</CardTitle>
          <CardDescription>
            Manage multi-channel messaging, sessions, webhooks, and scheduled tasks
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Tabs value={activeTab} onValueChange={setActiveTab}>
            <TabsList className="grid w-full grid-cols-8">
              <TabsTrigger value="metrics" className="flex items-center gap-2">
                <BarChart3 className="h-4 w-4" />
                Metrics
              </TabsTrigger>
              <TabsTrigger value="channels" className="flex items-center gap-2">
                <MessageSquare className="h-4 w-4" />
                Channels
              </TabsTrigger>
              <TabsTrigger value="sessions" className="flex items-center gap-2">
                <Layers className="h-4 w-4" />
                Sessions
              </TabsTrigger>
              <TabsTrigger value="webhooks" className="flex items-center gap-2">
                <Webhook className="h-4 w-4" />
                Webhooks
              </TabsTrigger>
              <TabsTrigger value="cron-jobs" className="flex items-center gap-2">
                <Clock className="h-4 w-4" />
                Cron Jobs
              </TabsTrigger>
              <TabsTrigger value="browser" className="flex items-center gap-2">
                <Monitor className="h-4 w-4" />
                Browser
              </TabsTrigger>
              <TabsTrigger value="resources" className="flex items-center gap-2">
                <Server className="h-4 w-4" />
                Resources
              </TabsTrigger>
              <TabsTrigger value="graph" className="flex items-center gap-2">
                <GitBranch className="h-4 w-4" />
                Graph
              </TabsTrigger>
            </TabsList>

            <TabsContent value="metrics" className="mt-6">
              <GatewayMetrics />
            </TabsContent>

            <TabsContent value="channels" className="mt-6">
              <ChannelsTable />
            </TabsContent>

            <TabsContent value="sessions" className="mt-6">
              <SessionsTable />
            </TabsContent>

            <TabsContent value="webhooks" className="mt-6">
              <WebhooksTable />
            </TabsContent>

            <TabsContent value="cron-jobs" className="mt-6">
              <CronJobsTable />
            </TabsContent>

            <TabsContent value="browser" className="mt-6">
              <BrowserInstanceMonitor />
            </TabsContent>

            <TabsContent value="resources" className="mt-6">
              <ResourceUsageDashboard />
            </TabsContent>

            <TabsContent value="graph" className="mt-6">
              <SessionRelationshipGraph />
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </div>
  );
}
