/**
 * Browser Instance Monitor Component
 * 
 * Displays and manages active browser instances with per-session isolation.
 * Features:
 * - List all active browser instances
 * - Display session ID, URL, status, memory usage, created timestamp
 * - Show screenshot preview thumbnails
 * - View screenshot gallery (opens dialog)
 * - View CDP command history (opens dialog)
 * - Close browser instances with confirmation
 * - Alert when approaching browser instance limit (max 3)
 * - Summary cards for total instances and memory usage
 */

import * as React from 'react';
import {
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from '@tanstack/react-table';
import { ArrowUpDown, X, Image, FileText, Monitor } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
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
import { ScrollArea } from '@/components/ui/scroll-area';
import { useBrowserInstances } from '@/hooks/useGateway';
import type { BrowserInstance, BrowserInstanceStatus } from '@/types/gateway';
import { closeBrowserInstance } from '@/lib/api';
import { toast } from 'sonner';
import { BrowserScreenshotGallery } from './BrowserScreenshotGallery';
import { BrowserCDPHistory } from './BrowserCDPHistory';

const MAX_BROWSER_INSTANCES = 3;

export function BrowserInstanceMonitor() {
  const { instances, loading, error, refetch } = useBrowserInstances(true);
  const [sorting, setSorting] = React.useState<SortingState>([]);
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [instanceToClose, setInstanceToClose] = React.useState<BrowserInstance | null>(null);
  const [isClosing, setIsClosing] = React.useState(false);
  const [screenshotGalleryOpen, setScreenshotGalleryOpen] = React.useState(false);
  const [selectedSessionForScreenshots, setSelectedSessionForScreenshots] = React.useState<string | null>(null);
  const [cdpHistoryOpen, setCdpHistoryOpen] = React.useState(false);
  const [selectedSessionForCDP, setSelectedSessionForCDP] = React.useState<string | null>(null);

  const totalMemoryUsage = React.useMemo(() => {
    return instances.reduce((sum, instance) => sum + instance.memory_usage, 0);
  }, [instances]);

  const columns: ColumnDef<BrowserInstance>[] = [
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
        <div className="font-mono text-sm max-w-[200px] truncate" title={row.getValue('session_id')}>
          {row.getValue('session_id')}
        </div>
      ),
    },
    {
      accessorKey: 'url',
      header: 'URL',
      cell: ({ row }) => {
        const url = row.getValue('url') as string;
        return (
          <div className="max-w-[300px] truncate" title={url}>
            {url || 'about:blank'}
          </div>
        );
      },
    },
    {
      accessorKey: 'status',
      header: 'Status',
      cell: ({ row }) => {
        const status = row.getValue('status') as BrowserInstanceStatus;
        const variant =
          status === 'active'
            ? 'default'
            : status === 'idle'
            ? 'secondary'
            : 'outline';
        return (
          <Badge variant={variant} className="capitalize">
            {status}
          </Badge>
        );
      },
    },
    {
      accessorKey: 'memory_usage',
      header: ({ column }) => {
        return (
          <Button
            variant="ghost"
            onClick={() => column.toggleSorting(column.getIsSorted() === 'asc')}
          >
            Memory (MB)
            <ArrowUpDown className="ml-2 h-4 w-4" />
          </Button>
        );
      },
      cell: ({ row }) => {
        const memory = row.getValue('memory_usage') as number;
        return <div className="text-center">{memory.toFixed(1)}</div>;
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
        return <div>{date.toLocaleString()}</div>;
      },
    },
    {
      id: 'screenshot',
      header: 'Screenshot',
      cell: ({ row }) => {
        const instance = row.original;
        return (
          <div className="flex items-center gap-2">
            {instance.screenshot_url ? (
              <img
                src={instance.screenshot_url}
                alt="Browser screenshot"
                className="w-16 h-12 object-cover rounded border"
              />
            ) : (
              <div className="w-16 h-12 bg-muted rounded border flex items-center justify-center">
                <Monitor className="h-4 w-4 text-muted-foreground" />
              </div>
            )}
          </div>
        );
      },
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: ({ row }) => {
        const instance = row.original;

        const handleViewScreenshots = () => {
          setSelectedSessionForScreenshots(instance.session_id);
          setScreenshotGalleryOpen(true);
        };

        const handleViewCDPLog = () => {
          setSelectedSessionForCDP(instance.session_id);
          setCdpHistoryOpen(true);
        };

        const handleClose = () => {
          setInstanceToClose(instance);
          setDeleteDialogOpen(true);
        };

        return (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleViewScreenshots}
              disabled={isClosing}
            >
              <Image className="h-4 w-4 mr-1" />
              Screenshots
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleViewCDPLog}
              disabled={isClosing}
            >
              <FileText className="h-4 w-4 mr-1" />
              CDP Log
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleClose}
              disabled={isClosing}
            >
              <X className="h-4 w-4 mr-1" />
              Close
            </Button>
          </div>
        );
      },
    },
  ];

  const table = useReactTable({
    data: instances,
    columns,
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    state: {
      sorting,
    },
  });

  const handleConfirmClose = async () => {
    if (!instanceToClose) return;

    setIsClosing(true);
    try {
      await closeBrowserInstance(instanceToClose.session_id);
      toast.success('Browser instance closed successfully!');
      refetch();
    } catch (error) {
      toast.error('Failed to close browser instance: ' + (error as Error).message);
    } finally {
      setIsClosing(false);
      setDeleteDialogOpen(false);
      setInstanceToClose(null);
    }
  };

  if (error) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Browser Instances</CardTitle>
          <CardDescription>Active browser automation sessions</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="text-center py-12 text-destructive">
            <p>Error loading browser instances: {error}</p>
            <Button onClick={refetch} className="mt-4">
              Retry
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {/* Summary Cards */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Instances</CardTitle>
            <Monitor className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{instances.length}</div>
            <p className="text-xs text-muted-foreground">
              Max {MAX_BROWSER_INSTANCES} concurrent instances
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Memory Usage</CardTitle>
            <Monitor className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{totalMemoryUsage.toFixed(1)} MB</div>
            <p className="text-xs text-muted-foreground">
              Across all browser instances
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Alert when approaching limit */}
      {instances.length >= 2 && (
        <Alert variant={instances.length >= MAX_BROWSER_INSTANCES ? 'destructive' : 'default'}>
          <Monitor className="h-4 w-4" />
          <AlertTitle>
            {instances.length >= MAX_BROWSER_INSTANCES
              ? 'Browser Instance Limit Reached'
              : 'Approaching Browser Instance Limit'}
          </AlertTitle>
          <AlertDescription>
            {instances.length >= MAX_BROWSER_INSTANCES
              ? `You have reached the maximum of ${MAX_BROWSER_INSTANCES} concurrent browser instances. Close an instance to create a new one.`
              : `You have ${instances.length} of ${MAX_BROWSER_INSTANCES} browser instances active. Consider closing idle instances to free resources.`}
          </AlertDescription>
        </Alert>
      )}

      {/* Browser Instances Table */}
      <Card>
        <CardHeader>
          <CardTitle>Browser Instances</CardTitle>
          <CardDescription>
            Active browser automation sessions with per-session isolation
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[500px]">
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
                        Loading browser instances...
                      </TableCell>
                    </TableRow>
                  ) : table.getRowModel().rows?.length ? (
                    table.getRowModel().rows.map((row) => (
                      <TableRow key={row.id}>
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
                          <Monitor className="h-8 w-8 text-muted-foreground" />
                          <p className="text-muted-foreground">No active browser instances.</p>
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </TableBody>
              </Table>
            </div>
          </ScrollArea>
        </CardContent>
      </Card>

      {/* Close Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Close Browser Instance</AlertDialogTitle>
            <AlertDialogDescription>
              This will terminate the browser session and free its resources. Any unsaved state will be lost.
              {instanceToClose && (
                <div className="mt-4 p-3 bg-muted rounded-md">
                  <p className="font-medium font-mono text-sm">Session: {instanceToClose.session_id}</p>
                  <p className="text-sm">URL: {instanceToClose.url || 'about:blank'}</p>
                  <p className="text-sm">Memory: {instanceToClose.memory_usage.toFixed(1)} MB</p>
                </div>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isClosing}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmClose}
              disabled={isClosing}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isClosing ? 'Closing...' : 'Close Instance'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Screenshot Gallery Dialog */}
      {selectedSessionForScreenshots && (
        <BrowserScreenshotGallery
          open={screenshotGalleryOpen}
          onOpenChange={setScreenshotGalleryOpen}
          sessionId={selectedSessionForScreenshots}
        />
      )}

      {/* CDP Command History Drawer */}
      {selectedSessionForCDP && (
        <BrowserCDPHistory
          open={cdpHistoryOpen}
          onOpenChange={setCdpHistoryOpen}
          sessionId={selectedSessionForCDP}
        />
      )}
    </div>
  );
}
