import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GatewayMetrics } from '@/components/admin/GatewayMetrics';

// Mock child visualization components
vi.mock('@/components/admin/MessageRoutingVisualization', () => ({
  MessageRoutingVisualization: () => <div data-testid="mock-routing-vis" />,
}));
vi.mock('@/components/admin/ChannelActivityHeatmap', () => ({
  ChannelActivityHeatmap: () => <div data-testid="mock-heatmap" />,
}));

// Mock recharts to avoid rendering issues in jsdom
vi.mock('recharts', async (importOriginal) => {
  const actual = await importOriginal<typeof import('recharts')>();
  return {
    ...actual,
    BarChart: ({ children }: any) => <div data-testid="bar-chart">{children}</div>,
    Bar: () => null,
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  };
});

vi.mock('@/hooks/useGateway', () => ({
  useGatewayMetrics: vi.fn(),
}));

import { useGatewayMetrics } from '@/hooks/useGateway';

const mockMetrics = {
  messages_per_channel: {
    'slack-main': 150,
    'telegram-bot': 75,
  },
  active_sessions: 12,
  queue_depth: 3,
  channel_health: {
    'slack-main': 'connected',
    'telegram-bot': 'disconnected',
  },
  timestamp: '2024-01-15T12:00:00Z',
};

describe('GatewayMetrics', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders controls: auto-refresh switch, time range selector, and export button', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: mockMetrics,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<GatewayMetrics />);

    expect(screen.getByText('Auto-refresh')).toBeInTheDocument();
    expect(screen.getByRole('switch')).toBeInTheDocument();
    expect(screen.getByText('Export CSV')).toBeInTheDocument();
    expect(screen.getByText('Gateway Metrics Dashboard')).toBeInTheDocument();
  });

  it('renders overview tab with active session and queue depth cards', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: mockMetrics,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<GatewayMetrics />);

    // The overview tab is the default tab
    expect(screen.getByText('Active Sessions')).toBeInTheDocument();
    expect(screen.getByText('Queue Depth')).toBeInTheDocument();
    expect(screen.getByText('12')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('Concurrent conversation contexts')).toBeInTheDocument();
  });

  it('renders channel health section in overview', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: mockMetrics,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<GatewayMetrics />);

    expect(screen.getByText('Channel Health')).toBeInTheDocument();
    expect(screen.getByText('slack-main')).toBeInTheDocument();
    expect(screen.getByText('telegram-bot')).toBeInTheDocument();
    expect(screen.getByText('connected')).toBeInTheDocument();
    expect(screen.getByText('disconnected')).toBeInTheDocument();
  });

  it('renders error state when metrics fail', () => {
    const refetchFn = vi.fn();
    (useGatewayMetrics as any).mockReturnValue({
      metrics: null,
      loading: false,
      error: 'Failed to fetch gateway metrics: 500',
      refetch: refetchFn,
    });

    render(<GatewayMetrics />);

    expect(screen.getByText('Error Loading Gateway Metrics')).toBeInTheDocument();
    expect(screen.getByText(/Failed to fetch gateway metrics/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });

  it('renders loading indicators when metrics are loading', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<GatewayMetrics />);

    // When loading and metrics is null, the active sessions and queue depth show '...'
    const loadingIndicators = screen.getAllByText('...');
    expect(loadingIndicators.length).toBeGreaterThanOrEqual(2);
  });

  it('renders queue depth health indicator text', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: { ...mockMetrics, queue_depth: 3 },
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<GatewayMetrics />);

    expect(screen.getByText('Healthy - Low queue depth')).toBeInTheDocument();
  });

  it('renders tab triggers for all metric sections', () => {
    (useGatewayMetrics as any).mockReturnValue({
      metrics: mockMetrics,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<GatewayMetrics />);

    expect(screen.getByRole('tab', { name: /Overview/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Channels/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Performance/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Routing/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /Activity/i })).toBeInTheDocument();
  });
});
