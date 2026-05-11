/**
 * Webhooks Table Component
 * 
 * Displays and manages webhook endpoints for triggering agent actions.
 * Features:
 * - List all webhooks with metadata
 * - Filter by enabled status
 * - Search by webhook ID
 * - Create/Edit/Delete webhooks
 * - Test webhooks with custom payloads
 * - Copy webhook URL and auth token
 * - View execution logs
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
import { ArrowUpDown, MoreHorizontal, Plus, Webhook as WebhookIcon, Copy, Check, AlertCircle } from 'lucide-react';
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
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { useWebhooks } from '@/hooks/useGateway';
import type { Webhook } from '@/types/gateway';
import { WebhookDialog } from './WebhookDialog';
import { TestWebhookDialog } from './TestWebhookDialog';
import { WebhookExecutionLogDrawer } from './WebhookExecutionLogDrawer';
import { deleteWebhook } from '@/lib/api';
import { toast } from 'sonner';

export function WebhooksTable() {
  const [enabledFilter, setEnabledFilter] = React.useState<boolean | undefined>(undefined);
  const { webhooks, loading, error, refetch } = useWebhooks(
    enabledFilter !== undefined ? { enabled: enabledFilter } : undefined
  );
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = React.useState({});
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [testDialogOpen, setTestDialogOpen] = React.useState(false);
  const [logDrawerOpen, setLogDrawerOpen] = React.useState(false);
  const [selectedWebhook, setSelectedWebhook] = React.useState<Webhook | null>(null);
  const [copiedUrl, setCopiedUrl] = React.useState<string | null>(null);

  const handleCopyUrl = (url: string) => {
    navigator.clipboard.writeText(url);
    setCopiedUrl(url);
    toast.success('Webhook URL copied to clipboard!');
    setTimeout(() => setCopiedUrl(null), 2000);
  };

  const columns: ColumnDef<Webhook>[] = [
    {
      accessorKey: 'webhook_id',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Webhook ID
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => <div className="font-medium">{row.getValue('webhook_id')}</div>,
    },
    {
      accessorKey: 'webhook_url',
      header: 'Webhook URL',
      cell: ({ row }) => {
        const url = row.getValue('webhook_url') as string;
        const truncated = url.length > 40 ? url.substring(0, 40) + '...' : url;
        const isCopied = copiedUrl === url;
        
        return (
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm">{truncated}</span>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6"
              onClick={() => handleCopyUrl(url)}
            >
              {isCopied ? (
                <Check className="h-3 w-3 text-green-500" />
              ) : (
                <Copy className="h-3 w-3" />
              )}
            </Button>
          </div>
        );
      },
    },
    {
      accessorKey: 'target_session_id',
      header: 'Target Session',
      cell: ({ row }) => (
        <div className="font-mono text-sm">{row.getValue('target_session_id')}</div>
      ),
    },
    {
      accessorKey: 'enabled',
      header: 'Enabled',
      cell: ({ row }) => {
        const enabled = row.getValue('enabled') as boolean;
        return (
          <Badge variant={enabled ? 'default' : 'outline'}>
            {enabled ? 'Yes' : 'No'}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'created_at',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Created
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => {
        const date = new Date(row.getValue('created_at'));
        return <div>{date.toLocaleDateString()}</div>;
      },
    },
    {
      accessorKey: 'last_triggered_at',
      header: 'Last Triggered',
      cell: ({ row }) => {
        const date = row.getValue('last_triggered_at') as string | undefined;
        return <div>{date ? new Date(date).toLocaleString() : 'Never'}</div>;
      },
    },
    {
      id: 'actions',
      enableHiding: false,
      cell: ({ row }) => {
        const webhook = row.original;

        const handleEdit = () => {
          setSelectedWebhook(webhook);
          setDialogOpen(true);
        };

        const handleTest = () => {
          setSelectedWebhook(webhook);
          setTestDialogOpen(true);
        };

        const handleViewLogs = () => {
          setSelectedWebhook(webhook);
          setLogDrawerOpen(true);
        };

        const handleDelete = async () => {
          if (!confirm(`Delete webhook "${webhook.webhook_id}"?`)) {
            return;
          }

          try {
            await deleteWebhook(webhook.webhook_id);
            toast.success('Webhook deleted successfully!');
            refetch();
          } catch (error) {
            toast.error('Failed to delete webhook: ' + (error as Error).message);
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
                onClick={() => navigator.clipboard.writeText(webhook.webhook_id)}
              >
                Copy webhook ID
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => handleCopyUrl(webhook.webhook_url)}>
                Copy webhook URL
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleTest}>
                Test webhook
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleViewLogs}>
                View execution logs
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleEdit}>
                Edit webhook
              </DropdownMenuItem>
              <DropdownMenuItem className="text-destructive" onClick={handleDelete}>
                Delete webhook
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];

  const table = useReactTable({
    data: webhooks || [],
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
        <AlertTitle>Error Loading Webhooks</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>Unable to fetch webhook data from the backend.</p>
          <p className="text-sm">Error: {error}</p>
          <p className="text-sm mt-2">Required endpoint: <code className="bg-muted px-1 py-0.5 rounded">/api/gateway/webhooks</code></p>
          <Button onClick={refetch} className="mt-4" size="sm">
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const handleAddWebhook = () => {
    setSelectedWebhook(null);
    setDialogOpen(true);
  };

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Input
            placeholder="Search by webhook ID..."
            value={(table.getColumn('webhook_id')?.getFilterValue() as string) ?? ''}
            onChange={(event) =>
              table.getColumn('webhook_id')?.setFilterValue(event.target.value)
            }
            className="max-w-sm"
          />
          <div className="flex items-center space-x-2">
            <Switch
              id="enabled-filter"
              checked={enabledFilter === true}
              onCheckedChange={(checked) => setEnabledFilter(checked ? true : undefined)}
            />
            <Label htmlFor="enabled-filter">Show enabled only</Label>
          </div>
        </div>
        <Button onClick={handleAddWebhook}>
          <Plus className="mr-2 h-4 w-4" />
          Create Webhook
        </Button>
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
                  Loading webhooks...
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
                    <WebhookIcon className="h-8 w-8 text-muted-foreground" />
                    <p className="text-muted-foreground">No webhooks found.</p>
                    <Button variant="outline" size="sm" onClick={handleAddWebhook}>
                      <Plus className="mr-2 h-4 w-4" />
                      Create your first webhook
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-end space-x-2 py-4">
        <div className="text-muted-foreground flex-1 text-sm">
          {table.getFilteredRowModel().rows.length} webhook(s) total
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

      <WebhookDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        webhook={selectedWebhook}
        onSuccess={() => {
          refetch();
        }}
      />

      <TestWebhookDialog
        open={testDialogOpen}
        onOpenChange={setTestDialogOpen}
        webhook={selectedWebhook}
      />

      <WebhookExecutionLogDrawer
        open={logDrawerOpen}
        onOpenChange={setLogDrawerOpen}
        webhookId={selectedWebhook?.webhook_id || null}
      />
    </div>
  );
}
