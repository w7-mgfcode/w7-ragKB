/**
 * Security Audit Log Component
 * 
 * Displays security events including:
 * - Blocked tool attempts
 * - Failed webhook authentication
 * - DM pairing failures
 * - Unauthorized access attempts
 * 
 * Features:
 * - Filter by event type and severity
 * - Date range filtering
 * - Search by session_id or user_id
 * - Export log to CSV
 */

import * as React from 'react';
import {
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type ColumnFiltersState,
  type SortingState,
  type VisibilityState,
} from '@tanstack/react-table';
import { ArrowUpDown, Download, Calendar as CalendarIcon } from 'lucide-react';
import { format } from 'date-fns';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Calendar } from '@/components/ui/calendar';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { useSecurityAudit } from '@/hooks/useSecurityAudit';
import { SecurityEventType, SecurityEventSeverity, type SecurityAuditEvent } from '@/types/gateway';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';

export function SecurityAuditLog() {
  const { events, loading, error, filters, updateFilters, clearFilters, refetch, exportLog } = useSecurityAudit();
  const [sorting, setSorting] = React.useState<SortingState>([{ id: 'timestamp', desc: true }]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = React.useState({});
  const [dateRange, setDateRange] = React.useState<{ from?: Date; to?: Date }>({});
  const [isExporting, setIsExporting] = React.useState(false);

  const getSeverityColor = (severity: SecurityEventSeverity): string => {
    switch (severity) {
      case SecurityEventSeverity.ERROR:
        return 'destructive';
      case SecurityEventSeverity.WARNING:
        return 'default';
      case SecurityEventSeverity.INFO:
        return 'secondary';
      default:
        return 'secondary';
    }
  };

  const getEventTypeLabel = (eventType: SecurityEventType): string => {
    switch (eventType) {
      case SecurityEventType.BLOCKED_TOOL:
        return 'Blocked Tool';
      case SecurityEventType.FAILED_WEBHOOK_AUTH:
        return 'Failed Webhook Auth';
      case SecurityEventType.DM_PAIRING_FAILURE:
        return 'DM Pairing Failure';
      case SecurityEventType.UNAUTHORIZED_ACCESS:
        return 'Unauthorized Access';
      default:
        return eventType;
    }
  };

  const columns: ColumnDef<SecurityAuditEvent>[] = [
    {
      accessorKey: 'timestamp',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Timestamp
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => {
        const timestamp = new Date(row.getValue('timestamp'));
        return (
          <div className="font-mono text-sm">
            {format(timestamp, 'yyyy-MM-dd HH:mm:ss')}
          </div>
        );
      },
    },
    {
      accessorKey: 'event_type',
      header: 'Event Type',
      cell: ({ row }) => {
        const eventType = row.getValue('event_type') as SecurityEventType;
        return (
          <Badge variant="outline" className="font-medium">
            {getEventTypeLabel(eventType)}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'severity',
      header: 'Severity',
      cell: ({ row }) => {
        const severity = row.getValue('severity') as SecurityEventSeverity;
        return (
          <Badge variant={getSeverityColor(severity) as any} className="capitalize">
            {severity}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'session_id',
      header: 'Session ID',
      cell: ({ row }) => {
        const sessionId = row.getValue('session_id') as string | undefined;
        return (
          <div className="font-mono text-xs text-muted-foreground max-w-[200px] truncate">
            {sessionId || '-'}
          </div>
        );
      },
    },
    {
      accessorKey: 'user_id',
      header: 'User ID',
      cell: ({ row }) => {
        const userId = row.getValue('user_id') as string | undefined;
        return (
          <div className="font-mono text-xs text-muted-foreground">
            {userId || '-'}
          </div>
        );
      },
    },
    {
      accessorKey: 'details',
      header: 'Details',
      cell: ({ row }) => {
        const details = row.getValue('details') as string;
        return (
          <div className="max-w-[300px] truncate text-sm" title={details}>
            {details}
          </div>
        );
      },
    },
  ];

  const table = useReactTable({
    data: events,
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
    },
  });

  const handleExport = async () => {
    try {
      setIsExporting(true);
      await exportLog();
      toast.success('Security audit log exported successfully');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to export log');
    } finally {
      setIsExporting(false);
    }
  };

  const handleDateRangeChange = (range: { from?: Date; to?: Date }) => {
    setDateRange(range);
    updateFilters({
      start_date: range.from ? format(range.from, 'yyyy-MM-dd') : undefined,
      end_date: range.to ? format(range.to, 'yyyy-MM-dd') : undefined,
    });
  };

  const handleClearFilters = () => {
    clearFilters();
    setDateRange({});
    table.getColumn('session_id')?.setFilterValue('');
  };

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Security Audit Log</CardTitle>
          <CardDescription>Error loading security events</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-destructive">{error}</div>
          <Button onClick={refetch} className="mt-4">
            Retry
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Security Audit Log</CardTitle>
        <CardDescription>
          View security events including blocked tools, failed authentication, and unauthorized access attempts
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-4">
          {/* Filters */}
          <div className="flex flex-wrap gap-4">
            {/* Event Type Filter */}
            <Select
              value={filters.event_type || 'all'}
              onValueChange={(value) =>
                updateFilters({ event_type: value === 'all' ? undefined : (value as SecurityEventType) })
              }
            >
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Event Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Event Types</SelectItem>
                <SelectItem value={SecurityEventType.BLOCKED_TOOL}>Blocked Tool</SelectItem>
                <SelectItem value={SecurityEventType.FAILED_WEBHOOK_AUTH}>Failed Webhook Auth</SelectItem>
                <SelectItem value={SecurityEventType.DM_PAIRING_FAILURE}>DM Pairing Failure</SelectItem>
                <SelectItem value={SecurityEventType.UNAUTHORIZED_ACCESS}>Unauthorized Access</SelectItem>
              </SelectContent>
            </Select>

            {/* Severity Filter */}
            <Select
              value={filters.severity || 'all'}
              onValueChange={(value) =>
                updateFilters({ severity: value === 'all' ? undefined : (value as SecurityEventSeverity) })
              }
            >
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Severity" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Severities</SelectItem>
                <SelectItem value={SecurityEventSeverity.INFO}>Info</SelectItem>
                <SelectItem value={SecurityEventSeverity.WARNING}>Warning</SelectItem>
                <SelectItem value={SecurityEventSeverity.ERROR}>Error</SelectItem>
              </SelectContent>
            </Select>

            {/* Date Range Picker */}
            <Popover>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  className={cn(
                    'w-[240px] justify-start text-left font-normal',
                    !dateRange.from && 'text-muted-foreground'
                  )}
                >
                  <CalendarIcon className="mr-2 h-4 w-4" />
                  {dateRange.from ? (
                    dateRange.to ? (
                      <>
                        {format(dateRange.from, 'LLL dd, y')} - {format(dateRange.to, 'LLL dd, y')}
                      </>
                    ) : (
                      format(dateRange.from, 'LLL dd, y')
                    )
                  ) : (
                    <span>Pick a date range</span>
                  )}
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0" align="start">
                <Calendar
                  initialFocus
                  mode="range"
                  defaultMonth={dateRange.from}
                  selected={{ from: dateRange.from, to: dateRange.to }}
                  onSelect={(range) => handleDateRangeChange(range || {})}
                  numberOfMonths={2}
                />
              </PopoverContent>
            </Popover>

            {/* Search Input */}
            <Input
              placeholder="Search by session ID or user ID..."
              value={(table.getColumn('session_id')?.getFilterValue() as string) ?? ''}
              onChange={(event) => {
                const value = event.target.value;
                table.getColumn('session_id')?.setFilterValue(value);
                table.getColumn('user_id')?.setFilterValue(value);
                updateFilters({ search: value || undefined });
              }}
              className="max-w-sm"
            />

            {/* Clear Filters Button */}
            <Button variant="outline" onClick={handleClearFilters}>
              Clear Filters
            </Button>

            {/* Export Button */}
            <Button
              variant="default"
              onClick={handleExport}
              disabled={isExporting || events.length === 0}
              className="ml-auto"
            >
              <Download className="mr-2 h-4 w-4" />
              {isExporting ? 'Exporting...' : 'Export Log'}
            </Button>
          </div>

          {/* Table */}
          <div className="rounded-md border">
            <Table>
              <TableHeader>
                {table.getHeaderGroups().map((headerGroup) => (
                  <TableRow key={headerGroup.id}>
                    {headerGroup.headers.map((header) => {
                      return (
                        <TableHead key={header.id}>
                          {header.isPlaceholder
                            ? null
                            : flexRender(header.column.columnDef.header, header.getContext())}
                        </TableHead>
                      );
                    })}
                  </TableRow>
                ))}
              </TableHeader>
              <TableBody>
                {loading ? (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      Loading security events...
                    </TableCell>
                  </TableRow>
                ) : table.getRowModel().rows?.length ? (
                  table.getRowModel().rows.map((row) => (
                    <TableRow key={row.id} data-state={row.getIsSelected() && 'selected'}>
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))
                ) : (
                  <TableRow>
                    <TableCell colSpan={columns.length} className="h-24 text-center">
                      No security events found.
                    </TableCell>
                  </TableRow>
                )}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between space-x-2 py-4">
            <div className="text-sm text-muted-foreground">
              Showing {table.getRowModel().rows.length} of {events.length} event(s)
            </div>
            <div className="space-x-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => table.previousPage()}
                disabled={!table.getCanPreviousPage()}
              >
                Previous
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => table.nextPage()}
                disabled={!table.getCanNextPage()}
              >
                Next
              </Button>
            </div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
