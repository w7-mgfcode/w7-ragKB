/**
 * Browser CDP Command History Drawer Component
 * 
 * Displays Chrome DevTools Protocol (CDP) command history for a browser instance.
 * Features:
 * - Timeline view of CDP commands with timestamp, command name, parameters, result, duration
 * - Filter by command type (Page.*, Runtime.*, Input.*, etc.)
 * - Search by command name
 * - Color-coded badges for command status (success/error)
 * - Export log to CSV
 * - Expandable command details showing full parameters and results
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
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Download, X, CheckCircle2, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import { getBrowserCDPLog } from '@/lib/api';
import type { BrowserCDPCommand } from '@/types/gateway';

interface BrowserCDPHistoryProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string | null;
}

export function BrowserCDPHistory({
  open,
  onOpenChange,
  sessionId,
}: BrowserCDPHistoryProps) {
  const [commands, setCommands] = React.useState<BrowserCDPCommand[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [commandTypeFilter, setCommandTypeFilter] = React.useState<string>('all');
  const [searchQuery, setSearchQuery] = React.useState('');
  const [expandedCommands, setExpandedCommands] = React.useState<Set<number>>(new Set());

  // Fetch CDP log when drawer opens or sessionId changes
  React.useEffect(() => {
    if (!open || !sessionId) {
      return;
    }

    const fetchCDPLog = async () => {
      try {
        setLoading(true);
        setError(null);
        const data = await getBrowserCDPLog(sessionId, 200);
        setCommands(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch CDP log');
      } finally {
        setLoading(false);
      }
    };

    fetchCDPLog();
  }, [open, sessionId]);

  // Extract unique command types for filter dropdown
  const commandTypes = React.useMemo(() => {
    const types = new Set<string>();
    commands.forEach((cmd) => {
      const domain = cmd.command.split('.')[0];
      if (domain) {
        types.add(domain);
      }
    });
    return Array.from(types).sort();
  }, [commands]);

  // Filter commands based on type and search query
  const filteredCommands = React.useMemo(() => {
    return commands.filter((cmd) => {
      // Filter by command type
      if (commandTypeFilter !== 'all') {
        const domain = cmd.command.split('.')[0];
        if (domain !== commandTypeFilter) {
          return false;
        }
      }

      // Filter by search query
      if (searchQuery) {
        const query = searchQuery.toLowerCase();
        return cmd.command.toLowerCase().includes(query);
      }

      return true;
    });
  }, [commands, commandTypeFilter, searchQuery]);

  const toggleCommandExpansion = (commandId: number) => {
    setExpandedCommands((prev) => {
      const next = new Set(prev);
      if (next.has(commandId)) {
        next.delete(commandId);
      } else {
        next.add(commandId);
      }
      return next;
    });
  };

  const handleExportCSV = () => {
    if (!sessionId || filteredCommands.length === 0) return;

    // CSV header
    const headers = ['Timestamp', 'Command', 'Duration (ms)', 'Status', 'Parameters', 'Result', 'Error'];
    
    // CSV rows
    const rows = filteredCommands.map((cmd) => {
      const timestamp = new Date(cmd.timestamp).toISOString();
      const status = cmd.error ? 'error' : 'success';
      const params = JSON.stringify(cmd.params || {});
      const result = JSON.stringify(cmd.result || {});
      const error = cmd.error || '';
      
      return [
        timestamp,
        cmd.command,
        cmd.duration_ms.toString(),
        status,
        params,
        result,
        error,
      ].map((field) => `"${field.replace(/"/g, '""')}"`).join(',');
    });

    const csv = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `cdp-log-${sessionId}-${Date.now()}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast.success('CDP log exported successfully!');
  };

  const getCommandBadge = (command: BrowserCDPCommand) => {
    if (command.error) {
      return (
        <Badge variant="destructive" className="flex items-center gap-1">
          <AlertCircle className="h-3 w-3" />
          Error
        </Badge>
      );
    }
    return (
      <Badge variant="default" className="flex items-center gap-1 bg-green-600">
        <CheckCircle2 className="h-3 w-3" />
        Success
      </Badge>
    );
  };

  if (!sessionId) {
    return null;
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[90vh]">
        <div className="mx-auto w-full max-w-5xl">
          <DrawerHeader>
            <div className="flex items-center justify-between">
              <div>
                <DrawerTitle>CDP Command History</DrawerTitle>
                <DrawerDescription>
                  Chrome DevTools Protocol commands for session: {sessionId}
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
            {/* Filters */}
            <div className="flex items-center gap-4">
              <Select value={commandTypeFilter} onValueChange={setCommandTypeFilter}>
                <SelectTrigger className="w-[200px]">
                  <SelectValue placeholder="Filter by type" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All commands</SelectItem>
                  {commandTypes.map((type) => (
                    <SelectItem key={type} value={type}>
                      {type}.*
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Input
                placeholder="Search by command name..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="flex-1"
              />

              <div className="text-sm text-muted-foreground whitespace-nowrap">
                {filteredCommands.length} command(s)
              </div>
            </div>

            <Separator />

            {/* Command Timeline */}
            <ScrollArea className="h-[500px] pr-4">
              {loading ? (
                <div className="text-center py-8 text-muted-foreground">
                  Loading CDP command history...
                </div>
              ) : error ? (
                <div className="text-center py-8 text-destructive">
                  <p>Error loading CDP log: {error}</p>
                </div>
              ) : filteredCommands.length > 0 ? (
                <div className="space-y-3">
                  {filteredCommands.map((command) => {
                    const isExpanded = expandedCommands.has(command.command_id);
                    
                    return (
                      <div
                        key={command.command_id}
                        className="border rounded-lg p-4 space-y-3"
                      >
                        {/* Command Header */}
                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-3">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => toggleCommandExpansion(command.command_id)}
                              className="h-6 w-6 p-0"
                            >
                              {isExpanded ? (
                                <ChevronDown className="h-4 w-4" />
                              ) : (
                                <ChevronRight className="h-4 w-4" />
                              )}
                            </Button>
                            <div>
                              <p className="font-mono text-sm font-medium">{command.command}</p>
                              <p className="text-xs text-muted-foreground">
                                {new Date(command.timestamp).toLocaleString()}
                              </p>
                            </div>
                          </div>
                          <div className="flex items-center gap-3">
                            <Badge variant="outline" className="font-mono">
                              {command.duration_ms}ms
                            </Badge>
                            {getCommandBadge(command)}
                          </div>
                        </div>

                        {/* Expanded Details */}
                        {isExpanded && (
                          <div className="space-y-3 pt-2 border-t">
                            {/* Parameters */}
                            <div>
                              <p className="text-sm font-medium mb-1">Parameters:</p>
                              <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">
                                {JSON.stringify(command.params, null, 2)}
                              </pre>
                            </div>

                            {/* Result or Error */}
                            {command.error ? (
                              <div>
                                <p className="text-sm font-medium mb-1 text-destructive">Error:</p>
                                <pre className="text-xs bg-destructive/10 text-destructive p-3 rounded overflow-x-auto">
                                  {command.error}
                                </pre>
                              </div>
                            ) : command.result ? (
                              <div>
                                <p className="text-sm font-medium mb-1">Result:</p>
                                <pre className="text-xs bg-muted p-3 rounded overflow-x-auto">
                                  {JSON.stringify(command.result, null, 2)}
                                </pre>
                              </div>
                            ) : null}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="text-center py-8 text-muted-foreground">
                  No CDP commands found
                  {(commandTypeFilter !== 'all' || searchQuery) && ' matching your filters'}
                </div>
              )}
            </ScrollArea>
          </div>

          <DrawerFooter>
            <div className="flex gap-2">
              <Button
                onClick={handleExportCSV}
                variant="outline"
                disabled={filteredCommands.length === 0}
              >
                <Download className="mr-2 h-4 w-4" />
                Export CSV
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
