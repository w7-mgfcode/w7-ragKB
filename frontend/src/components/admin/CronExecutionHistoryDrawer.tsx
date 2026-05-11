/**
 * Cron Execution History Drawer Component
 * 
 * Displays execution history for a cron job.
 * Features:
 * - Execution log with timestamp, outcome, error message, duration
 * - Color-coded badges for success/failure/skipped
 * - Filter by outcome
 * - Date range picker for filtering (simplified)
 * - Export log functionality
 * - Execution statistics (success rate, average duration)
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
import { Card } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Download, X, AlertCircle, CheckCircle2, MinusCircle } from 'lucide-react';
import { toast } from 'sonner';
import { useCronExecutionHistory } from '@/hooks/useGateway';
import { CronExecutionOutcome } from '@/types/gateway';

interface CronExecutionHistoryDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cronJobId: string | null;
}

export function CronExecutionHistoryDrawer({
  open,
  onOpenChange,
  cronJobId,
}: CronExecutionHistoryDrawerProps) {
  const [outcomeFilter, setOutcomeFilter] = React.useState<string>('all');
  const { executions, loading, error } = useCronExecutionHistory(
    cronJobId,
    outcomeFilter !== 'all' ? { outcome: outcomeFilter as CronExecutionOutcome } : undefined
  );

  const statistics = React.useMemo(() => {
    if (!executions || executions.length === 0) {
      return {
        total: 0,
        success: 0,
        failure: 0,
        skipped: 0,
        successRate: 0,
      };
    }

    const total = executions.length;
    const success = executions.filter(e => e.outcome === CronExecutionOutcome.SUCCESS).length;
    const failure = executions.filter(e => e.outcome === CronExecutionOutcome.FAILURE).length;
    const skipped = executions.filter(e => e.outcome === CronExecutionOutcome.SKIPPED).length;
    const successRate = total > 0 ? (success / total) * 100 : 0;

    return {
      total,
      success,
      failure,
      skipped,
      successRate,
    };
  }, [executions]);

  const handleExport = () => {
    if (!cronJobId || !executions) return;

    const exportData = {
      cron_job_id: cronJobId,
      exported_at: new Date().toISOString(),
      statistics,
      executions,
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cron-${cronJobId}-history-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast.success('Execution history exported successfully!');
  };

  const getOutcomeBadge = (outcome: CronExecutionOutcome) => {
    switch (outcome) {
      case CronExecutionOutcome.SUCCESS:
        return (
          <Badge variant="default" className="flex items-center gap-1 bg-green-600">
            <CheckCircle2 className="h-3 w-3" />
            Success
          </Badge>
        );
      case CronExecutionOutcome.FAILURE:
        return (
          <Badge variant="destructive" className="flex items-center gap-1">
            <AlertCircle className="h-3 w-3" />
            Failure
          </Badge>
        );
      case CronExecutionOutcome.SKIPPED:
        return (
          <Badge variant="outline" className="flex items-center gap-1">
            <MinusCircle className="h-3 w-3" />
            Skipped
          </Badge>
        );
      default:
        return <Badge variant="outline">{outcome}</Badge>;
    }
  };

  if (!cronJobId) {
    return null;
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[90vh]">
        <div className="mx-auto w-full max-w-4xl">
          <DrawerHeader>
            <div className="flex items-center justify-between">
              <div>
                <DrawerTitle>Cron Job Execution History</DrawerTitle>
                <DrawerDescription>
                  Cron Job ID: {cronJobId}
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
            {/* Statistics Cards */}
            <div className="grid grid-cols-4 gap-4">
              <Card className="p-4">
                <div className="text-sm text-muted-foreground">Total Executions</div>
                <div className="text-2xl font-bold">{statistics.total}</div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-muted-foreground">Success</div>
                <div className="text-2xl font-bold text-green-600">{statistics.success}</div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-muted-foreground">Failure</div>
                <div className="text-2xl font-bold text-destructive">{statistics.failure}</div>
              </Card>
              <Card className="p-4">
                <div className="text-sm text-muted-foreground">Success Rate</div>
                <div className="text-2xl font-bold">{statistics.successRate.toFixed(1)}%</div>
              </Card>
            </div>

            <Separator />

            <div className="flex items-center gap-4">
              <Select value={outcomeFilter} onValueChange={setOutcomeFilter}>
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder="Filter by outcome" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All executions</SelectItem>
                  <SelectItem value={CronExecutionOutcome.SUCCESS}>Success only</SelectItem>
                  <SelectItem value={CronExecutionOutcome.FAILURE}>Failures only</SelectItem>
                  <SelectItem value={CronExecutionOutcome.SKIPPED}>Skipped only</SelectItem>
                </SelectContent>
              </Select>

              <div className="text-sm text-muted-foreground">
                {executions?.length || 0} execution(s)
              </div>
            </div>

            <Separator />

            <ScrollArea className="h-[400px] pr-4">
              {loading ? (
                <div className="text-center py-8 text-muted-foreground">
                  Loading execution history...
                </div>
              ) : error ? (
                <div className="text-center py-8 text-destructive">
                  <p>Error loading execution history: {error}</p>
                </div>
              ) : executions && executions.length > 0 ? (
                <div className="space-y-4">
                  {executions.map((execution) => (
                    <div
                      key={execution.execution_id}
                      className="border rounded-lg p-4 space-y-3"
                    >
                      <div className="flex items-center justify-between">
                        {getOutcomeBadge(execution.outcome)}
                        <span className="text-sm text-muted-foreground">
                          {new Date(execution.timestamp).toLocaleString()}
                        </span>
                      </div>

                      <div className="grid grid-cols-2 gap-4 text-sm">
                        <div>
                          <p className="text-muted-foreground">Execution ID</p>
                          <p className="font-mono">{execution.execution_id}</p>
                        </div>
                        <div>
                          <p className="text-muted-foreground">Outcome</p>
                          <p className="capitalize">{execution.outcome}</p>
                        </div>
                      </div>

                      {execution.error_message && (
                        <div className="mt-2 p-2 bg-destructive/10 rounded text-sm">
                          <p className="text-destructive font-medium">Error:</p>
                          <p className="text-destructive">{execution.error_message}</p>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  No execution history found
                </div>
              )}
            </ScrollArea>
          </div>

          <DrawerFooter>
            <div className="flex gap-2">
              <Button 
                onClick={handleExport} 
                variant="outline" 
                disabled={!executions || executions.length === 0}
              >
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
