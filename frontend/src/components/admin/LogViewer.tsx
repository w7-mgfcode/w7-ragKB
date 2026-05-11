import { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { authFetch } from '@/lib/auth-client';
import type { LogsData, LogEntry } from '@/types/systemMonitor';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

const LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const;

interface LogViewerProps {
  initialLogs: LogsData;
}

function levelBadge(level: string) {
  switch (level) {
    case 'DEBUG':
      return <Badge variant="outline" className="text-xs">{level}</Badge>;
    case 'INFO':
      return <Badge className="bg-blue-500 text-white border-blue-500 text-xs">{level}</Badge>;
    case 'WARNING':
      return <Badge variant="secondary" className="bg-yellow-500 text-white border-yellow-500 text-xs">{level}</Badge>;
    case 'ERROR':
      return <Badge variant="destructive" className="text-xs">{level}</Badge>;
    case 'CRITICAL':
      return <Badge variant="destructive" className="bg-red-700 text-white border-red-700 text-xs">{level}</Badge>;
    default:
      return <Badge variant="outline" className="text-xs">{level}</Badge>;
  }
}

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

export default function LogViewer({ initialLogs }: LogViewerProps) {
  const [level, setLevel] = useState('INFO');
  const [logs, setLogs] = useState<LogEntry[]>(initialLogs.records);
  const [totalBuffered, setTotalBuffered] = useState(initialLogs.total_buffered);

  const fetchLogs = useCallback(async (selectedLevel: string) => {
    try {
      const res = await authFetch(`${API_BASE}/api/admin/monitor/logs?level=${selectedLevel}`);
      if (!res.ok) return;
      const data: LogsData = await res.json();
      setLogs(data.records);
      setTotalBuffered(data.total_buffered);
    } catch (err) {
      console.error('Failed to fetch logs:', err);
    }
  }, []);

  useEffect(() => {
    // Re-fetch when level changes (skip initial render since we have initialLogs)
    fetchLogs(level);
  }, [level, fetchLogs]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="text-base">Application Logs</CardTitle>
        <Select value={level} onValueChange={setLevel}>
          <SelectTrigger className="w-[140px]">
            <SelectValue placeholder="Log level" />
          </SelectTrigger>
          <SelectContent>
            {LOG_LEVELS.map((l) => (
              <SelectItem key={l} value={l}>{l}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </CardHeader>
      <CardContent>
        <p className="text-xs text-muted-foreground mb-2">
          {logs.length} records shown · {totalBuffered} buffered
        </p>
        <ScrollArea className="h-[400px] rounded-md border p-3">
          {logs.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">No log entries</p>
          ) : (
            logs.map((entry, i) => (
              <div key={`${entry.timestamp}-${i}`}>
                <div className="flex items-start gap-2 py-1.5 text-sm">
                  <span className="text-xs text-muted-foreground whitespace-nowrap font-mono">
                    {formatTimestamp(entry.timestamp)}
                  </span>
                  {levelBadge(entry.level)}
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    {entry.logger}
                  </span>
                  <span className="break-all">{entry.message}</span>
                </div>
                {i < logs.length - 1 && <Separator />}
              </div>
            ))
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
