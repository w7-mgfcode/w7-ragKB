import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from '@/components/ui/table';
import type { ApiMetrics } from '@/types/systemMonitor';

interface ApiMetricsTableProps {
  metrics: ApiMetrics;
}

export default function ApiMetricsTable({ metrics }: ApiMetricsTableProps) {
  const sorted = [...metrics.endpoints].sort((a, b) => b.request_count - a.request_count);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">API Metrics</CardTitle>
      </CardHeader>
      <CardContent>
        {sorted.length === 0 ? (
          <p className="text-sm text-muted-foreground">No API requests recorded</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Endpoint</TableHead>
                <TableHead className="text-right">Requests</TableHead>
                <TableHead className="text-right">Avg (ms)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.map((ep) => (
                <TableRow key={ep.path}>
                  <TableCell className="font-mono text-xs">{ep.path}</TableCell>
                  <TableCell className="text-right">{ep.request_count.toLocaleString()}</TableCell>
                  <TableCell className="text-right">{ep.avg_response_time_ms.toFixed(1)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
