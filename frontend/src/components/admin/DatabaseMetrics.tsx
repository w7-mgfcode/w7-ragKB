import { Card, CardHeader, CardTitle, CardContent, CardFooter } from '@/components/ui/card';
import { Table, TableBody, TableRow, TableCell } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Progress } from '@/components/ui/progress';
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from '@/components/ui/tooltip';
import type { DatabaseMetrics } from '@/types/systemMonitor';

interface DatabaseMetricsPanelProps {
  metrics: DatabaseMetrics;
}

export default function DatabaseMetricsPanel({ metrics }: DatabaseMetricsPanelProps) {
  const poolUsedPercent = metrics.pool_max > 0
    ? Math.round((metrics.pool_used / metrics.pool_max) * 100)
    : 0;

  const rowCounts = [
    { label: 'Conversations', count: metrics.total_conversations },
    { label: 'Messages', count: metrics.total_messages },
    { label: 'Documents', count: metrics.total_documents },
    { label: 'Web Users', count: metrics.total_web_users },
  ];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Database</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Connection Pool</span>
            <div className="flex items-center gap-2">
              <Badge variant="outline">{metrics.pool_used} used</Badge>
              <Badge variant="outline">{metrics.pool_free} free</Badge>
              <Badge variant="secondary">{metrics.pool_max} max</Badge>
            </div>
          </div>
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div>
                  <Progress value={poolUsedPercent} />
                </div>
              </TooltipTrigger>
              <TooltipContent>
                {metrics.pool_used} / {metrics.pool_max} connections used ({poolUsedPercent}%)
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        </div>

        <Table>
          <TableBody>
            {rowCounts.map((row) => (
              <TableRow key={row.label}>
                <TableCell className="font-medium text-muted-foreground">{row.label}</TableCell>
                <TableCell className="text-right">
                  <Badge variant="secondary">{row.count.toLocaleString()}</Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter>
        <p className="text-xs text-muted-foreground">PostgreSQL {metrics.db_version}</p>
      </CardFooter>
    </Card>
  );
}
