# Visual Verification Checklist

Manual verification of all OpenClaw gateway components. Open the app at `http://localhost:8080` and walk through each item.

## Admin Dashboard → Gateway Management

### Metrics Tab (default)
- [ ] 4 metric cards visible: Active Sessions, Queue Depth, Total Messages, Channel Health
- [ ] Channel health badges show correct colors (green=connected, red=error, gray=disconnected)
- [ ] Numbers update when auto-refresh is on

### Metrics → Overview Sub-tab
- [ ] Active Sessions gauge with progress bar
- [ ] Queue Depth gauge with color-coded bar (green < 10, yellow < 50, red >= 50)
- [ ] Channel Health grid with status badges

### Metrics → Channels Sub-tab
- [ ] Bar chart renders messages per channel
- [ ] Chart has proper axis labels

### Metrics → Performance Sub-tab
- [ ] Total Messages count
- [ ] Connected Channels count
- [ ] Last Updated timestamp

### Metrics → Routing Sub-tab
- [ ] MessageRoutingVisualization renders stacked bar chart
- [ ] 3 layers visible: Channels → Session Types → Agent Response
- [ ] CSS shimmer animation on active links when auto-refresh detects new messages

### Metrics → Activity Sub-tab
- [ ] 7×24 heatmap grid visible (days of week × hours)
- [ ] Color scaling from cool to warm
- [ ] Tooltip on cell hover shows exact count
- [ ] Channel filter dropdown works
- [ ] Peak hour summary card shows correct data

### Channels Tab
- [ ] Table displays channels with ID, Type, Status, Enabled, Created columns
- [ ] Search by channel ID works
- [ ] Filter by channel type dropdown works
- [ ] "Add Channel" button opens ChannelDialog
- [ ] "Setup Wizard" button opens ChannelConfigWizard
- [ ] Wizard: 4 steps (Platform → Credentials → Settings → Review)
- [ ] Wizard: Back/Next navigation works
- [ ] Wizard: Platform cards are selectable
- [ ] Wizard: Test connection button works
- [ ] Row actions menu: Test connection, Edit, Delete

### Sessions Tab
- [ ] Table displays sessions with columns
- [ ] Search filters work
- [ ] Click row opens SessionDetailDrawer
- [ ] Drawer shows session metadata, message history
- [ ] Drawer footer: Export, Compact, Send Message, Close buttons
- [ ] Compact button opens SessionCompactionInterface
- [ ] Compaction: Strategy selector (Summarize, Keep Last N, Archive All)
- [ ] Compaction: Before/After panels show metrics

### Webhooks Tab
- [ ] Table displays webhooks
- [ ] "Create Webhook" button opens WebhookDialog
- [ ] Dialog: Session combobox search works
- [ ] Dialog: "Open Editor" button shows WebhookTransformEditor inline
- [ ] Transform Editor: 3 panels (Input, Rules, Output)
- [ ] Transform Editor: Add/remove rules works
- [ ] Transform Editor: JSON and Visual tabs sync

### Cron Jobs Tab
- [ ] Table displays cron jobs
- [ ] "Create Cron Job" button opens CronJobDialog
- [ ] Dialog: Common Presets tab with preset buttons
- [ ] Dialog: Custom Expression tab with input
- [ ] Dialog: Visual Builder tab with CronExpressionBuilder
- [ ] Builder: 5 rows (minute, hour, day, month, weekday)
- [ ] Builder: Mode selectors (Every, Specific, Range, Interval)
- [ ] Builder: Natural language input parses correctly
- [ ] Builder: Human-readable description updates
- [ ] Next 5 execution times preview

### Browser Tab
- [ ] BrowserInstanceMonitor renders
- [ ] Shows browser instance count (max 3)

### Resources Tab
- [ ] ResourceUsageDashboard renders
- [ ] 4 chart cards: Memory, Sessions, Browser, DB Pool
- [ ] Alert banners when thresholds exceeded
- [ ] VM Budget PieChart shows allocation
- [ ] Auto-refresh toggle works

### Graph Tab
- [ ] SessionRelationshipGraph renders adjacency matrix
- [ ] Sessions as rows/columns
- [ ] Cell colors indicate message count
- [ ] Cluster badges above matrix
- [ ] Click cell navigates to session

## Chat Page

### Channel Selector
- [ ] Dropdown in chat header bar
- [ ] "Web (Direct)" default option
- [ ] Connected channels listed with platform icons
- [ ] Status dots (green/red) per channel
- [ ] Selection persists in localStorage

### Session Indicator
- [ ] Compact bar next to channel selector
- [ ] Shows session_id (truncated), channel badge, session_type
- [ ] Memory usage mini-progress bar
- [ ] Tooltip with full session details
- [ ] Health dot color based on memory + idle time

### Platform-Specific Rendering
- [ ] Telegram inline keyboard buttons render as grid
- [ ] Discord embed cards render with colored left border
- [ ] Platform hint text below input (e.g., "Supports Markdown. Max 2000 chars.")

## Responsive
- [ ] Mobile: sidebar collapses to sheet
- [ ] Mobile: channel selector still accessible
- [ ] Tab grid doesn't overflow on smaller screens
