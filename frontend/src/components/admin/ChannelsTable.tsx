/**
 * Channels Table Component
 * 
 * Displays and manages messaging platform channels (Slack, Telegram, Discord, WhatsApp).
 * Features:
 * - List all channels with status indicators
 * - Filter by channel type
 * - Search by channel ID
 * - Add/Edit/Delete channels
 * - Test channel connections
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
import { ArrowUpDown, MoreHorizontal, Plus, MessageSquare, AlertCircle, Wand2 } from 'lucide-react';
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { useChannels } from '@/hooks/useGateway';
import type { Channel, ChannelType } from '@/types/gateway';
import { ChannelDialog } from './ChannelDialog';
import { ChannelConfigWizard } from './ChannelConfigWizard';
import { createChannel, updateChannel, deleteChannel, testChannelConnection } from '@/lib/api';
import { toast } from 'sonner';

export function ChannelsTable() {
  const { channels, loading, error, refetch } = useChannels();
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([]);
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({});
  const [rowSelection, setRowSelection] = React.useState({});
  const [channelTypeFilter, setChannelTypeFilter] = React.useState<string>('all');
  const [dialogOpen, setDialogOpen] = React.useState(false);
  const [selectedChannel, setSelectedChannel] = React.useState<Channel | null>(null);
  const [isDeleting, setIsDeleting] = React.useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [channelToDelete, setChannelToDelete] = React.useState<Channel | null>(null);
  const [wizardOpen, setWizardOpen] = React.useState(false);

  const columns: ColumnDef<Channel>[] = [
    {
      accessorKey: 'channel_id',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Channel ID
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => <div className="font-medium">{row.getValue('channel_id')}</div>,
    },
    {
      accessorKey: 'channel_type',
      header: 'Type',
      cell: ({ row }) => {
        const type = row.getValue('channel_type') as ChannelType;
        const icons = {
          slack: '💬',
          telegram: '✈️',
          discord: '🎮',
          whatsapp: '📱',
        };
        return (
          <div className="flex items-center gap-2">
            <span>{icons[type]}</span>
            <span className="capitalize">{type}</span>
          </div>
        );
      },
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.getValue('status') as string;
        const variant =
          status === 'connected'
            ? 'default'
            : status === 'error'
            ? 'destructive'
            : 'secondary';
        return (
          <Badge variant={variant} className="capitalize">
            {status}
          </Badge>
        );
      },
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
      id: 'actions',
      enableHiding: false,
      cell: ({ row }) => {
        const channel = row.original;

        const handleTestConnection = async () => {
          try {
            const result = await testChannelConnection(channel.channel_id);
            if (result.success) {
              toast.success('Connection test successful!');
            } else {
              toast.error('Connection test failed: ' + result.message);
            }
          } catch (error) {
            toast.error('Connection test failed: ' + (error as Error).message);
          }
        };

        const handleEdit = () => {
          setSelectedChannel(channel);
          setDialogOpen(true);
        };

        const handleDelete = () => {
          setChannelToDelete(channel);
          setDeleteDialogOpen(true);
        };

        return (
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" className="h-8 w-8 p-0" disabled={isDeleting}>
                <span className="sr-only">Open menu</span>
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuLabel>Actions</DropdownMenuLabel>
              <DropdownMenuItem
                onClick={() => navigator.clipboard.writeText(channel.channel_id)}
              >
                Copy channel ID
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem onClick={handleTestConnection}>
                Test connection
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleEdit}>
                Edit channel
              </DropdownMenuItem>
              <DropdownMenuItem className="text-destructive" onClick={handleDelete}>
                Delete channel
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        );
      },
    },
  ];

  // Filter data by channel type
  const filteredData = React.useMemo(() => {
    if (!channels) return [];
    if (channelTypeFilter === 'all') return channels;
    return channels.filter((channel) => channel.channel_type === channelTypeFilter);
  }, [channels, channelTypeFilter]);

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
        <AlertTitle>Error Loading Channels</AlertTitle>
        <AlertDescription className="space-y-2">
          <p>Unable to fetch channel data from the backend.</p>
          <p className="text-sm">Error: {error}</p>
          <p className="text-sm mt-2">Required endpoint: <code className="bg-muted px-1 py-0.5 rounded">/api/gateway/channels</code></p>
          <Button onClick={refetch} className="mt-4" size="sm">
            Retry
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  const handleAddChannel = () => {
    setSelectedChannel(null);
    setDialogOpen(true);
  };

  const handleSaveChannel = async (data: any) => {
    if (selectedChannel) {
      // Edit existing channel
      await updateChannel(selectedChannel.channel_id, {
        config: {
          api_token: data.api_token,
          webhook_url: data.webhook_url || undefined,
          rate_limit_per_minute: data.rate_limit_per_minute,
        },
        enabled: data.enabled,
      });
    } else {
      // Create new channel
      await createChannel({
        channel_id: data.channel_id,
        channel_type: data.channel_type,
        config: {
          api_token: data.api_token,
          webhook_url: data.webhook_url || undefined,
          rate_limit_per_minute: data.rate_limit_per_minute,
        },
        enabled: data.enabled,
      });
    }
    refetch();
  };

  const handleTestConnection = async (data: any) => {
    try {
      const result = await testChannelConnection(data.channel_id || 'test');
      return result.success;
    } catch (error) {
      return false;
    }
  };

  const handleConfirmDelete = async () => {
    if (!channelToDelete) return;
    
    setIsDeleting(true);
    try {
      await deleteChannel(channelToDelete.channel_id);
      toast.success('Channel deleted successfully!');
      refetch();
    } catch (error) {
      toast.error('Failed to delete channel: ' + (error as Error).message);
    } finally {
      setIsDeleting(false);
      setDeleteDialogOpen(false);
      setChannelToDelete(null);
    }
  };

  return (
    <div className="w-full space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Input
            placeholder="Search by channel ID..."
            value={(table.getColumn('channel_id')?.getFilterValue() as string) ?? ''}
            onChange={(event) =>
              table.getColumn('channel_id')?.setFilterValue(event.target.value)
            }
            className="max-w-sm"
          />
          <Select value={channelTypeFilter} onValueChange={setChannelTypeFilter}>
            <SelectTrigger className="w-[180px]">
              <SelectValue placeholder="Filter by type" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All types</SelectItem>
              <SelectItem value="slack">Slack</SelectItem>
              <SelectItem value="telegram">Telegram</SelectItem>
              <SelectItem value="discord">Discord</SelectItem>
              <SelectItem value="whatsapp">WhatsApp</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setWizardOpen(true)}>
            <Wand2 className="mr-2 h-4 w-4" />
            Setup Wizard
          </Button>
          <Button onClick={handleAddChannel}>
            <Plus className="mr-2 h-4 w-4" />
            Add Channel
          </Button>
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
                  Loading channels...
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
                    <MessageSquare className="h-8 w-8 text-muted-foreground" />
                    <p className="text-muted-foreground">No channels found.</p>
                    <Button variant="outline" size="sm" onClick={handleAddChannel}>
                      <Plus className="mr-2 h-4 w-4" />
                      Add your first channel
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
          {table.getFilteredRowModel().rows.length} channel(s) total
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

      <ChannelDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        channel={selectedChannel}
        onSave={handleSaveChannel}
        onTestConnection={handleTestConnection}
      />

      <ChannelConfigWizard
        open={wizardOpen}
        onOpenChange={setWizardOpen}
        onSuccess={refetch}
      />

      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Channel</AlertDialogTitle>
            <AlertDialogDescription>
              Deleting this channel will archive all associated sessions. This action cannot be undone.
              {channelToDelete && (
                <div className="mt-4 p-3 bg-muted rounded-md">
                  <p className="font-medium">Channel: {channelToDelete.channel_id}</p>
                  <p className="text-sm capitalize">Type: {channelToDelete.channel_type}</p>
                </div>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? 'Deleting...' : 'Delete Channel'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
