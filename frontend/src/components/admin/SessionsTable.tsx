/**
 * Sessions Table Component
 * 
 * Displays and manages conversation sessions across all channels.
 * Features:
 * - List all sessions with metadata
 * - Filter by channel, session type, activation mode
 * - Search by session ID or user ID
 * - View session history
 * - Send messages to sessions
 * - Archive sessions
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
import { ArrowUpDown, MoreHorizontal, Layers, MessageSquare, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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
import { useSessions } from '@/hooks/useGateway';
import type { Session, SessionType, ActivationMode } from '@/types/gateway';
import { archiveSession } from '@/lib/api';
import { toast } from 'sonner';
import { SessionDetailDrawer } from './SessionDetailDrawer';
import { SendMessageDialog } from './SendMessageDialog';
import { ToolAllowlistEditor } from './ToolAllowlistEditor';

export function SessionsTable() {
  const { sessions, loading, error, refetch } = useSessions();
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = React.useState({});
  const [sessionTypeFilter, setSessionTypeFilter] = React.useState<string>('all');
  const [activationModeFilter, setActivationModeFilter] = React.useState<string>('all');
  const [detailDrawerOpen, setDetailDrawerOpen] = React.useState(false);
  const [sendMessageOpen, setSendMessageOpen] = React.useState(false);
  const [toolAllowlistOpen, setToolAllowlistOpen] = React.useState(false);
  const [selectedSessionId, setSelectedSessionId] = React.useState<string | null>(null);
  const [selectedSession, setSelectedSession] = React.useState<Session | null>(null);

  const columns: ColumnDef<Session>[] = [
    {
      accessorKey: 'session_id',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Session ID
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => (
        <div className="font-mono text-sm">{row.getValue('session_id')}</div>
      ),
    },
    {
      accessorKey: 'channel_id',
      header: 'Channel',
      cell: ({ row }) => <div className="font-medium">{row.getValue('channel_id')}</div>,
    },
    {
      accessorKey: 'user_id',
      header: 'User ID',
      cell: ({ row }) => <div>{row.getValue('user_id')}</div>,
    },
    {
      accessorKey: 'session_type',
      header: 'Type',
      cell: ({ row }) => {
        const type = row.getValue('session_type') as SessionType;
        const variants: Record<SessionType, 'default' | 'secondary' | 'outline'> = {
          main: 'default',
          group: 'secondary',
          webhook: 'outline',
        };
        return (
          <Badge variant={variants[type]} className="capitalize">
            {type}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'activation_mode',
      header: 'Activation',
      cell: ({ row }) => {
        const mode = row.getValue('activation_mode') as ActivationMode;
        return <span className="capitalize text-sm">{mode}</span>;
      },
    },
    {
      accessorKey: 'message_count',
      header: 'Messages',
      cell: ({ row }) => {
        const count = row.getValue('message_count') as number;
        return <div className="text-center">{count}</div>;
      },
    },
    {
      accessorKey: 'last_activity_at',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Last Activity
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => {
        const date = new Date(row.getValue('last_activity_at'));
        return <div>{date.toLocaleString()}</div>;
      },
    },
    {
      id: 'actions',
      enableHiding: false,
      cell: ({ row }) => {
        const session = row.original;

        const handleViewHistory = () => {
          setSelectedSessionId(session.session_id);
          setDetailDrawerOpen(true);
        };

        const handleSendMessage = () => {
          setSelectedSessionId(session.session_id);
          setSendMessageOpen(true);
        };

        const handleEditTools = () => {
          setSelectedSession(session);
          setToolAllowlistOpen(true);
        };

        const handleArchive = async () => {
          if (!confirm(`Archive session "${session.session_id}"?`)) {
            return;
          }

          try {
            await archiveSession(session.session_id);
            toast.success('Session archived successfully!');
            refetch();
          } catch (error) {
            toast.error('Failed to archive session: ' + (error as Error).message);
          }
        };

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0">
                <span className="sr-only">Open menu</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Actions</DropdownMenuLabel>
              <DropdownMenuItem
                onClick={() => navigator.clipboard.writeText(session.session_id)}
              >
                Copy session ID
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleViewHistory}>
                View history
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleSendMessage}>
                Send message
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleEditTools}>
                Edit tool allowlist
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleArchive}>
                Archive session
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];

  // Filter data by session type and activation mode
  const filteredData = React.useMemo(() => {
    if (!sessions) return [];
    let filtered = sessions;

    if (sessionTypeFilter !== 'all') {
      filtered = filtered.filter((session) => session.session_type === sessionTypeFilter);
    }

    if (activationModeFilter !== 'all') {
      filtered = filtered.filter(
        (session) => session.activation_mode === activationModeFilter
      );
    }

    return filtered;
  }, [sessions, sessionTypeFilter, activationModeFilter]);

  const table = useReactTable({
    data: filteredData,
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

  if (error) {
    return (
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertTitle>Error Loading Sessions</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>Unable to fetch session data from the backend.</p>
          <p className="text-sm">Error: {error}</p>
          <p className="text-sm mt-2">Required endpoint: <code className="bg-muted px-1 py-0.5 rounded">/api/gateway/sessions</code></p>
          <Button onClick={refetch} className="mt-4" size="sm">
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-4 flex-1">
          <Input
            placeholder="Search by session ID or user ID..."
            value={(table.getColumn('session_id')?.getFilterValue() as string) ?? ''}
            onChange={(event) =>
              table.getColumn('session_id')?.setFilterValue(event.target.value)
            }
            className="max-w-sm"
          />
          <Select value={sessionTypeFilter} onValueChange={setSessionTypeFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Session type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All types</SelectItem>
              <SelectItem value="main">Main</SelectItem>
              <SelectItem value="group">Group</SelectItem>
              <SelectItem value="webhook">Webhook</SelectItem>
            </SelectContent>
          </Select>
          <Select value={activationModeFilter} onValueChange={setActivationModeFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Activation mode" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All modes</SelectItem>
              <SelectItem value="always">Always</SelectItem>
              <SelectItem value="mention">Mention</SelectItem>
              <SelectItem value="manual">Manual</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="overflow-hidden rounded-md border">
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
                  Loading sessions...
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
                  <div className="flex flex-col items-center gap-2">
                    <Layers className="h-8 w-8 text-muted-foreground" />
                    <p className="text-muted-foreground">No sessions found.</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end space-x-2 py-4">
        <div className="text-muted-foreground flex-1 text-sm">
          {table.getFilteredRowModel().rows.length} session(s) total
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

      <SessionDetailDrawer
        open={detailDrawerOpen}
        onOpenChange={setDetailDrawerOpen}
        sessionId={selectedSessionId}
      />

      <SendMessageDialog
        open={sendMessageOpen}
        onOpenChange={setSendMessageOpen}
        defaultSessionId={selectedSessionId || undefined}
        onSuccess={() => {
          refetch();
        }}
      />

      {selectedSession && (
        <ToolAllowlistEditor
          open={toolAllowlistOpen}
          onOpenChange={setToolAllowlistOpen}
          session={selectedSession}
          onSuccess={() => {
            refetch();
          }}
        />
      )}
    </div>
  );
}
