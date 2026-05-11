import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChannelActivityHeatmap } from '@/components/admin/ChannelActivityHeatmap';

vi.mock('@/hooks/useGateway', () => ({
  useSessions: vi.fn(),
}));

import { useSessions } from '@/hooks/useGateway';

// Helper to create a session with a specific last_activity_at datetime
function makeSession(id: string, channelId: string, lastActivity: string, messageCount: number) {
  return {
    session_id: id,
    channel_id: channelId,
    user_id: 'user-001',
    chat_id: 'chat-001',
    session_type: 'main',
    activation_mode: 'always',
    tool_allowlist: [],
    tool_denylist: [],
    message_count: messageCount,
    token_usage: {},
    created_at: '2024-01-01T00:00:00Z',
    last_activity_at: lastActivity,
  };
}

describe('ChannelActivityHeatmap', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the heatmap title and description', () => {
    (useSessions as any).mockReturnValue({
      sessions: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelActivityHeatmap />);

    expect(screen.getByText('Channel Activity Heatmap')).toBeInTheDocument();
    expect(screen.getByText(/Message activity distribution by day of week and hour/)).toBeInTheDocument();
  });

  it('renders 7-day row labels (Mon through Sun)', () => {
    // Generate sessions across recent dates so the grid populates
    const now = new Date();
    const sessions = [
      makeSession('s1', 'slack-main', now.toISOString(), 5),
    ];

    (useSessions as any).mockReturnValue({
      sessions,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelActivityHeatmap />);

    // The day labels should be present
    expect(screen.getByText('Mon')).toBeInTheDocument();
    expect(screen.getByText('Tue')).toBeInTheDocument();
    expect(screen.getByText('Wed')).toBeInTheDocument();
    expect(screen.getByText('Thu')).toBeInTheDocument();
    expect(screen.getByText('Fri')).toBeInTheDocument();
    expect(screen.getByText('Sat')).toBeInTheDocument();
    expect(screen.getByText('Sun')).toBeInTheDocument();
  });

  it('renders peak hour summary card', () => {
    const now = new Date();
    const sessions = [
      makeSession('s1', 'slack-main', now.toISOString(), 10),
    ];

    (useSessions as any).mockReturnValue({
      sessions,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelActivityHeatmap />);

    expect(screen.getByText('Peak Activity')).toBeInTheDocument();
    expect(screen.getByText('Total Activity')).toBeInTheDocument();
    expect(screen.getByText('Average Per Slot')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    (useSessions as any).mockReturnValue({
      sessions: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelActivityHeatmap />);

    expect(screen.getByText('Loading activity data...')).toBeInTheDocument();
  });

  it('renders error state with retry button', () => {
    (useSessions as any).mockReturnValue({
      sessions: [],
      loading: false,
      error: 'Failed to fetch sessions',
      refetch: vi.fn(),
    });

    render(<ChannelActivityHeatmap />);

    expect(screen.getByText(/Failed to fetch sessions/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });

  it('renders empty state when no sessions match filters', () => {
    // Sessions outside the time range (very old)
    (useSessions as any).mockReturnValue({
      sessions: [
        makeSession('s1', 'slack-main', '2020-01-01T00:00:00Z', 5),
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelActivityHeatmap />);

    expect(screen.getByText(/No activity data available/)).toBeInTheDocument();
  });

  it('renders Active Channels section when channels exist', () => {
    const now = new Date();
    const sessions = [
      makeSession('s1', 'slack-main', now.toISOString(), 5),
      makeSession('s2', 'telegram-bot', now.toISOString(), 3),
    ];

    (useSessions as any).mockReturnValue({
      sessions,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelActivityHeatmap />);

    expect(screen.getByText('Active Channels')).toBeInTheDocument();
    expect(screen.getByText(/slack-main/)).toBeInTheDocument();
    expect(screen.getByText(/telegram-bot/)).toBeInTheDocument();
  });
});
