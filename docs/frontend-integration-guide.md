# Frontend Integration Guide

## Architecture Overview

The w7-ragKB frontend is a React 18 SPA built with Vite, TypeScript, Tailwind CSS, and Shadcn UI. It communicates with the backend via REST API calls authenticated with JWT tokens.

```
frontend/src/
├── components/
│   ├── admin/          # Admin dashboard components
│   │   ├── GatewayManagement.tsx    # Main gateway container (8 tabs)
│   │   ├── GatewayMetrics.tsx       # Metrics dashboard (5 inner tabs)
│   │   ├── ChannelsTable.tsx        # Channel CRUD table
│   │   ├── SessionsTable.tsx        # Session management table
│   │   ├── WebhooksTable.tsx        # Webhook CRUD table
│   │   ├── CronJobsTable.tsx        # Cron job management table
│   │   ├── BrowserInstanceMonitor.tsx
│   │   ├── SessionRelationshipGraph.tsx  # Session adjacency matrix
│   │   ├── MessageRoutingVisualization.tsx # Message flow chart
│   │   ├── ResourceUsageDashboard.tsx    # Resource monitoring
│   │   ├── ChannelActivityHeatmap.tsx    # Activity heatmap
│   │   ├── ChannelConfigWizard.tsx       # Channel setup wizard
│   │   ├── WebhookTransformEditor.tsx    # Transform rules editor
│   │   ├── CronExpressionBuilder.tsx     # Visual cron builder
│   │   └── SessionCompactionInterface.tsx # Memory compaction
│   ├── chat/           # Chat UI components
│   │   ├── ChatLayout.tsx          # Main chat layout
│   │   ├── ChatInput.tsx           # Message input with file upload
│   │   ├── MessageList.tsx         # Message display list
│   │   ├── MessageItem.tsx         # Individual message rendering
│   │   ├── ChannelSelector.tsx     # Multi-channel selector
│   │   ├── SessionIndicator.tsx    # Session info bar
│   │   ├── TelegramKeyboard.tsx    # Telegram inline keyboards
│   │   └── DiscordEmbedPreview.tsx # Discord embed cards
│   ├── documents/      # Document browser components
│   │   ├── DocumentTree.tsx           # Hierarchical file tree with sync badges
│   │   ├── DocumentViewer.tsx         # Document preview with sync info
│   │   ├── DocumentEditor.tsx         # Markdown editor with save/cancel
│   │   ├── SearchBar.tsx              # Document search with debounce
│   │   ├── StatsPanel.tsx             # Aggregate document statistics
│   │   ├── CreateDocumentDialog.tsx   # New document creation dialog
│   │   ├── BulkActionsToolbar.tsx     # Multi-select actions (delete/move/reindex)
│   │   ├── SyncStatusBadge.tsx        # Color-coded sync status indicator
│   │   ├── ConflictResolutionDialog.tsx # Side-by-side conflict comparison
│   │   └── ReindexDialog.tsx          # Re-index confirmation with progress
│   └── ui/             # Shadcn UI primitives
├── hooks/
│   ├── useGateway.ts   # All gateway data hooks
│   ├── useDocuments.ts # Document CRUD + sync status hooks (React Query)
│   ├── useDocumentWebSocket.ts # Real-time sync via WebSocket
│   ├── useAuth.ts      # Authentication state
│   └── use-mobile.ts   # Responsive breakpoint
├── lib/
│   ├── api.ts          # API client functions
│   ├── documents-api.ts # Document-specific API client (CRUD + sync + reindex)
│   ├── auth-client.ts  # Auth token management
│   └── utils.ts        # Utility functions (cn, etc.)
├── pages/
│   ├── Chat.tsx         # Main chat page
│   ├── Documents.tsx    # Document browser page
│   └── Admin.tsx        # Admin dashboard page
└── types/
    ├── gateway.ts       # Gateway type definitions
    ├── documents.ts     # Document, sync, and conflict types
    └── database.types.ts # Core database types
```

## Component Hierarchy

```
Admin Page
└── GatewayManagement
    ├── Metric Cards (4x)
    └── Tabs
        ├── GatewayMetrics
        │   ├── Overview (gauges + health grid)
        │   ├── Channels (bar chart)
        │   ├── Performance (stats)
        │   ├── Routing (MessageRoutingVisualization)
        │   └── Activity (ChannelActivityHeatmap)
        ├── ChannelsTable
        │   ├── ChannelDialog (create/edit)
        │   └── ChannelConfigWizard (guided setup)
        ├── SessionsTable
        │   ├── SessionDetailDrawer
        │   │   └── SessionCompactionInterface
        │   └── SendMessageDialog
        ├── WebhooksTable
        │   └── WebhookDialog
        │       └── WebhookTransformEditor
        ├── CronJobsTable
        │   └── CronJobDialog
        │       └── CronExpressionBuilder
        ├── Resources (ResourceUsageDashboard)
        ├── Sessions Graph (SessionRelationshipGraph)
        └── Browser (BrowserInstanceMonitor)

Chat Page
├── ChannelSelector (header)
├── SessionIndicator (header)
├── ChatSidebar
├── MessageList
│   └── MessageItem
│       ├── TelegramKeyboard (conditional)
│       └── DiscordEmbedPreview (conditional)
└── ChatInput

Documents Page
├── StatsPanel
├── SearchBar
├── DocumentTree
│   └── SyncStatusBadge (per document)
├── DocumentViewer
│   ├── SyncStatusBadge
│   └── ReindexDialog (on demand)
├── DocumentEditor (when editing)
├── BulkActionsToolbar
├── CreateDocumentDialog
├── ReindexDialog
└── ConflictResolutionDialog
```

## Hook Usage

All gateway data fetching uses custom hooks from `hooks/useGateway.ts`:

```typescript
// Fetch all channels with auto-refresh
const { channels, loading, error, refetch } = useChannels(filters?, autoRefresh?);

// Fetch a single session
const { session, loading, error, refetch } = useSession(sessionId);

// Fetch session message history with pagination
const { messages, loading, error, loadMore, hasMore } = useSessionHistory(sessionId, limit?);

// Fetch gateway metrics (auto-refresh every 5s by default)
const { metrics, loading, error, refetch } = useGatewayMetrics(timeRange?, autoRefresh?);

// Resource history ring buffer (60 snapshots max)
const { snapshots, addSnapshot } = useResourceHistory(maxSnapshots?);
```

### Document Hooks (`hooks/useDocuments.ts`)

```typescript
// Fetch document tree
const { tree, loading, refetch } = useDocumentTree();

// Fetch document stats
const { stats, loading, refetch } = useDocumentStats();

// Fetch a single document (pass null to skip)
const { document, loading, error, refetch } = useDocument(path);

// Sync status hooks (React Query with 30s staleTime, 60s polling)
const { data: syncStatuses } = useSyncStatuses();
const { data: syncStatus } = useSyncStatus(path);

// Mutation hooks for re-indexing and conflict resolution
const reindexMutation = useReindexDocument();
const reindexDirMutation = useReindexDirectory();
const reindexAllMutation = useReindexAll();
const resolveMutation = useResolveConflict();

// Cache invalidation
const { invalidateAll, invalidateSyncStatuses } = useInvalidateDocuments();
```

### WebSocket Hook (`hooks/useDocumentWebSocket.ts`)

```typescript
// Enable real-time sync updates — auto-reconnects with exponential backoff
const { status } = useDocumentWebSocket(true);
// status: 'connected' | 'disconnected' | 'reconnecting'
```

Events handled: `document_created`, `document_updated`, `document_deleted`, `sync_status_update`, `reindex_complete`. Each event invalidates the relevant React Query cache.

### Hook Patterns

- All hooks return `{ data, loading, error, refetch }`
- Auto-refresh is optional, uses `setInterval` with cleanup
- Errors are strings, displayed in Alert components
- Hooks use `useCallback` for stable function references
- Document sync hooks use React Query with `staleTime: 30_000` and `refetchInterval: 60_000` as polling fallback

## API Client

All API calls go through `lib/api.ts`, which uses `authFetch` (adds JWT Authorization header).

```typescript
// CRUD pattern
const channels = await listChannels(filters?);
const channel = await getChannel(channelId);
const created = await createChannel(data);
const updated = await updateChannel(channelId, data);
await deleteChannel(channelId);

// Action endpoints
const result = await testChannelConnection(channelId);
await archiveSession(sessionId);
await compactSession(sessionId, strategy, keepCount?);
const preview = await previewCronSchedule(schedule, timezone);
```

## Adding a New Tab to GatewayManagement

1. Create your component in `components/admin/YourComponent.tsx`
2. Import it in `GatewayManagement.tsx`
3. Add a `TabsTrigger` in the `TabsList`
4. Add a `TabsContent` with your component
5. Update the `grid-cols-N` class on `TabsList` to accommodate the new tab

```tsx
// In GatewayManagement.tsx
import { YourComponent } from './YourComponent';

// In TabsList (update grid-cols-N)
<TabsTrigger value="your-tab" className="flex items-center gap-2">
  <YourIcon className="h-4 w-4" />
  Your Tab
</TabsTrigger>

// In TabsContent
<TabsContent value="your-tab" className="mt-6">
  <YourComponent />
</TabsContent>
```

## Adding a New Chart

1. Import Recharts components:
   ```tsx
   import { BarChart, Bar, XAxis, YAxis, CartesianGrid } from 'recharts';
   import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
   ```

2. Define chart config:
   ```tsx
   const chartConfig = {
     dataKey: { label: 'Display Name', color: 'hsl(var(--chart-1))' },
   } satisfies ChartConfig;
   ```

3. Render:
   ```tsx
   <ChartContainer config={chartConfig} className="min-h-[300px] w-full">
     <BarChart data={chartData}>
       <CartesianGrid vertical={false} />
       <XAxis dataKey="name" />
       <YAxis />
       <ChartTooltip content={<ChartTooltipContent />} />
       <Bar dataKey="value" fill="var(--color-dataKey)" radius={4} />
     </BarChart>
   </ChartContainer>
   ```

## Testing

### Unit Tests (Vitest)

```bash
cd frontend && npx vitest --run
```

Tests are in `src/__tests__/` and use `@testing-library/react`. Mock API with `vi.mock('@/lib/api')`.

### E2E Tests (Playwright)

```bash
cd frontend && npx playwright test
```

Tests are in `tests/`. Mock API endpoints with `page.route()`. Follow patterns in `tests/mocks.ts`.

## Type System

All gateway types are in `types/gateway.ts`:
- Enums: `ChannelType`, `ChannelStatus`, `SessionType`, `ActivationMode`, etc.
- Interfaces: `Channel`, `Session`, `Webhook`, `CronJob`, `GatewayMetrics`, etc.
- Filter interfaces: `ChannelFilters`, `SessionFilters`, etc.
- Form data interfaces: `ChannelFormData`, `WebhookFormData`, etc.

## Styling Conventions

- Use Tailwind CSS utility classes
- Use `cn()` from `lib/utils` for conditional classes
- Use Shadcn UI components for all interactive elements
- Icons from `lucide-react`
- Toast notifications via `sonner`
- Charts via `recharts` wrapped in Shadcn's `ChartContainer`
