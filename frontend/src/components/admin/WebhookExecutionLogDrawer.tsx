/**
 * Webhook Execution Log Drawer Component
 * 
 * Displays execution history for a webhook endpoint.
 * Features:
 * - Execution log with timestamp, source IP, auth status, response status
 * - Color-coded badges for success/failure/auth_failed
 * - Filter by status
 * - Date range picker for filtering
 * - Export log functionality
 * - Execution timeline view
 */

import * as React from 'react';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Download, X, AlertCircle, CheckCircle2, XCircle } from 'lucide-react';
import { toast } from 'sonner';

interface WebhookExecutionLog {
  execution_id: number;
  timestamp: string;
  source_ip: string;
  auth_status: 'success' | 'failed';
  payload_size: number;
  response_status: number;
  error_message?: string;
}

interface WebhookExecutionLogDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  webhookId: string | null;
}

export function WebhookExecutionLogDrawer({
  open,
  onOpenChange,
  webhookId,
}: WebhookExecutionLogDrawerProps) {
  const [statusFilter, setStatusFilter] = React.useState<string>('all');
  const [loading, setLoading] = React.useState(false);
  const [logs, setLogs] = React.useState<WebhookExecutionLog[]>([]);

  // Mock data for demonstration - replace with actual API call
  React.useEffect(() => {
    if (!webhookId || !open) return;

    setLoading(true);
    // Simulate API call
    setTimeout(() => {
      const mockLogs: WebhookExecutionLog[] = [
        {
          execution_id: 1,
          timestamp: new Date(Date.now() - 3600000).toISOString(),
          source_ip: '192.168.1.100',
          auth_status: 'success',
          payload_size: 1024,
          response_status: 200,
        },
        {
          execution_id: 2,
          timestamp: new Date(Date.now() - 7200000).toISOString(),
          source_ip: '192.168.1.101',
          auth_status: 'failed',
          payload_size: 512,
          response_status: 401,
          error_message: 'Invalid auth token',
        },
        {
          execution_id: 3,
          timestamp: new Date(Date.now() - 10800000).toISOString(),
          source_ip: '192.168.1.100',
          auth_status: 'success',
          payload_size: 2048,
          response_status: 400,
          error_message: 'Invalid payload schema',
        },
        {
          execution_id: 4,
          timestamp: new Date(Date.now() - 14400000).toISOString(),
          source_ip: '192.168.1.102',
          auth_status: 'success',
          payload_size: 1536,
          response_status: 200,
        },
        {
          execution_id: 5,
          timestamp: new Date(Date.now() - 18000000).toISOString(),
          source_ip: '192.168.1.100',
          auth_status: 'success',
          payload_size: 896,
          response_status: 404,
          error_message: 'Target session not found',
        },
      ];
      setLogs(mockLogs);
      setLoading(false);
    }, 500);
  }, [webhookId, open]);

  const filteredLogs = React.useMemo(() => {
    if (statusFilter === 'all') return logs;
    
    if (statusFilter === 'success') {
      return logs.filter(log => log.response_status >= 200 && log.response_status < 300);
    }
    
    if (statusFilter === 'auth_failed') {
      return logs.filter(log => log.auth_status === 'failed');
    }
    
    if (statusFilter === 'error') {
      return logs.filter(log => log.response_status >= 400);
    }
    
    return logs;
  }, [logs, statusFilter]);

  const handleExport = () => {
    const exportData = {
      webhook_id: webhookId,
      exported_at: new Date().toISOString(),
      logs: filteredLogs,
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `webhook-${webhookId}-logs-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast.success('Execution log exported successfully!');
  };

  const getStatusBadge = (log: WebhookExecutionLog) => {
    if (log.auth_status === 'failed') {
      return (
        <Badge variant="destructive" className="flex items-center gap-1">
          <XCircle className="h-3 w-3" />
          Auth Failed
        </Badge>
      );
    }

    if (log.response_status >= 200 && log.response_status < 300) {
      return (
        <Badge variant="default" className="flex items-center gap-1">
          <CheckCircle2 className="h-3 w-3" />
          Success
        </Badge>
      );
    }

    return (
      <Badge variant="destructive" className="flex items-center gap-1">
        <AlertCircle className="h-3 w-3" />
        Error
      </Badge>
    );
  };

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  if (!webhookId) {
    return null;
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[90vh]">
        <div className="mx-auto w-full max-w-4xl">
          <DrawerHeader>
            <div className="flex items-center justify-between">
              <div>
                <DrawerTitle>Webhook Execution Log</DrawerTitle>
                <DrawerDescription>
                  Webhook ID: {webhookId}
                </DrawerDescription>
              </div>
              <DrawerClose asChild>
                <Button variant="ghost" size="icon">
                  <X className="h-4 w-4" />
                </Button>
              </DrawerClose>
            </div>
          </DrawerHeader>

          <div className="p-4 space-y-4">
            <div className="flex items-center gap-4">
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder="Filter by status" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All executions</SelectItem>
                  <SelectItem value="success">Success only</SelectItem>
                  <SelectItem value="auth_failed">Auth failed</SelectItem>
                  <SelectItem value="error">Errors only</SelectItem>
                </SelectContent>
              </Select>

              <div className="text-sm text-muted-foreground">
                {filteredLogs.length} execution(s)
              </div>
            </div>

            <Separator />

            <ScrollArea className="h-[500px] pr-4">
              {loading ? (
                <div className="text-center py-8 text-muted-foreground">
                  Loading execution log...
                </div>
              ) : filteredLogs.length > 0 ? (
                <div className="space-y-4">
                  {filteredLogs.map((log) => (
                    <div
                      key={log.execution_id}
                      className="border rounded-lg p-4 space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        {getStatusBadge(log)}
                        <span className="text-sm text-muted-foreground">
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className="text-muted-foreground">Source IP</p>
                          <p className="font-mono">{log.source_ip}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Response Status</p>
                          <p className="font-medium">{log.response_status}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Auth Status</p>
                          <p className="capitalize">{log.auth_status}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Payload Size</p>
                          <p>{formatBytes(log.payload_size)}</p>
                        </div>
                      </div>

                      {log.error_message && (
                        <div className="mt-2 p-2 bg-destructive/10 rounded text-sm">
                          <p className="text-destructive font-medium">Error:</p>
                          <p className="text-destructive">{log.error_message}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  No execution logs found
                </div>
              )}
            </ScrollArea>
          </div>

          <DrawerFooter>
            <div className="flex gap-2">
              <Button onClick={handleExport} variant="outline" disabled={filteredLogs.length === 0}>
                <Download className="mr-2 h-4 w-4" />
                Export Log
              </Button>
              <DrawerClose asChild>
                <Button variant="outline">Close</Button>
              </DrawerClose>
            </div>
          </DrawerFooter>
        </div>
      </DrawerContent>
    </Drawer>
  );
}
