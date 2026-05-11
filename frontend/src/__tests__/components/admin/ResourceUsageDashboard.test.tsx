import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ResourceUsageDashboard } from '@/components/admin/ResourceUsageDashboard';

// Mock recharts to avoid rendering issues in jsdom
vi.mock('recharts', () => ({
  AreaChart: ({ children }: any) => <div data-testid="area-chart">{children}</div>,
  Area: () => null,
  LineChart: ({ children }: any) => <div data-testid="line-chart">{children}</div>,
  Line: () => null,
  BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
  Bar: () => null,
  PieChart: ({ children }: any) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => null,
  Cell: () => null,
  ComposedChart: ({ children }: any) => <div data-testid="composed-chart">{children}</div>,
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Legend: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
}));

vi.mock('@/hooks/useGateway', () => ({
  useGatewayMetrics: vi.fn(),
  useBrowserInstances: vi.fn(),
}));

import { useGatewayMetrics, useBrowserInstances } from '@/hooks/useGateway';

describe('ResourceUsageDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('renders dashboard title and chart cards', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: {
        messages_per_channel: { 'slack-main': 100 },
        active_sessions: 5,
        queue_depth: 2,
        channel_health: { 'slack-main': 'connected' },
        timestamp: new Date().toISOString(),
      },
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    (useBrowserInstances as any).mockReturnValue({
      instances: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ResourceUsageDashboard />);

    expect(screen.getByText('Resource Usage Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Estimated Memory Usage')).toBeInTheDocument();
    expect(screen.getByText('Active Sessions')).toBeInTheDocument();
    expect(screen.getByText('Browser Instances')).toBeInTheDocument();
    expect(screen.getByText('DB Connection Pool')).toBeInTheDocument();
  });

  it('renders VM Memory Budget section', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: {
        messages_per_channel: {},
        active_sessions: 5,
        queue_depth: 0,
        channel_health: {},
        timestamp: new Date().toISOString(),
      },
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    (useBrowserInstances as any).mockReturnValue({
      instances: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ResourceUsageDashboard />);

    expect(screen.getByText('VM Memory Budget (4 GB Total)')).toBeInTheDocument();
    expect(screen.getByText('PostgreSQL')).toBeInTheDocument();
    expect(screen.getByText('Slack Bot')).toBeInTheDocument();
    expect(screen.getByText('RAG Pipeline')).toBeInTheDocument();
    expect(screen.getByText('Frontend')).toBeInTheDocument();
  });

  it('renders alert banners when browser instance threshold is exceeded', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: {
        messages_per_channel: {},
        active_sessions: 5,
        queue_depth: 0,
        channel_health: {},
        timestamp: new Date().toISOString(),
      },
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    (useBrowserInstances as any).mockReturnValue({
      instances: [
        { session_id: 's1', url: 'http://a', status: 'active', memory_usage: 100, created_at: new Date().toISOString() },
        { session_id: 's2', url: 'http://b', status: 'active', memory_usage: 100, created_at: new Date().toISOString() },
        { session_id: 's3', url: 'http://c', status: 'idle', memory_usage: 50, created_at: new Date().toISOString() },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ResourceUsageDashboard />);

    expect(screen.getByText('Browser Instance Limit')).toBeInTheDocument();
  });

  it('renders alert banner when session count exceeds threshold', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: {
        messages_per_channel: {},
        active_sessions: 55,
        queue_depth: 0,
        channel_health: {},
        timestamp: new Date().toISOString(),
      },
      loading: false,
      error: null,
      refetch: vi.fn(),
    });
    (useBrowserInstances as any).mockReturnValue({
      instances: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ResourceUsageDashboard />);

    expect(screen.getByText('High Session Count')).toBeInTheDocument();
  });

  it('renders error state', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: null,
      loading: false,
      error: 'Network error',
      refetch: vi.fn(),
    });
    (useBrowserInstances as any).mockReturnValue({
      instances: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ResourceUsageDashboard />);

    expect(screen.getByText('Error Loading Resource Data')).toBeInTheDocument();
  });

  it('renders auto-refresh toggle and interval selector', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    });
    (useBrowserInstances as any).mockReturnValue({
      instances: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<ResourceUsageDashboard />);

    expect(screen.getByText('Auto-refresh')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
    expect(screen.getByText('Refresh')).toBeInTheDocument();
  });
});
