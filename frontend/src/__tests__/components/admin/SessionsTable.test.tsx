import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { SessionsTable } from '@/components/admin/SessionsTable';

// Mock child components
vi.mock('@/components/admin/SessionDetailDrawer', () => ({
  SessionDetailDrawer: () => null,
}));
vi.mock('@/components/admin/SendMessageDialog', () => ({
  SendMessageDialog: () => null,
}));
vi.mock('@/components/admin/ToolAllowlistEditor', () => ({
  ToolAllowlistEditor: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/hooks/useGateway', () => ({
  useSessions: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  archiveSession: vi.fn(),
}));

import { useSessions } from '@/hooks/useGateway';

const mockSessions = [
  {
    session_id: 'sess-abc-123',
    channel_id: 'slack-main',
    user_id: 'user-001',
    chat_id: 'chat-001',
    session_type: 'main',
    activation_mode: 'always',
    tool_allowlist: ['rag', 'web_search'],
    tool_denylist: [],
    message_count: 42,
    token_usage: { input: 1000, output: 500 },
    created_at: '2024-01-01T00:00:00Z',
    last_activity_at: '2024-01-15T12:30:00Z',
  },
  {
    session_id: 'sess-def-456',
    channel_id: 'telegram-bot',
    user_id: 'user-002',
    chat_id: 'chat-002',
    session_type: 'group',
    activation_mode: 'mention',
    tool_allowlist: [],
    tool_denylist: ['browser'],
    message_count: 10,
    token_usage: { input: 200, output: 100 },
    created_at: '2024-02-01T00:00:00Z',
    last_activity_at: '2024-02-10T08:00:00Z',
  },
];

describe('SessionsTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    (useSessions as any).mockReturnValue({
      sessions: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionsTable />);
    expect(screen.getByText('Loading sessions...')).toBeInTheDocument();
  });

  it('renders sessions data in table', () => {
    (useSessions as any).mockReturnValue({
      sessions: mockSessions,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionsTable />);
    expect(screen.getByText('sess-abc-123')).toBeInTheDocument();
    expect(screen.getByText('sess-def-456')).toBeInTheDocument();
    expect(screen.getByText('slack-main')).toBeInTheDocument();
    expect(screen.getByText('telegram-bot')).toBeInTheDocument();
    expect(screen.getByText('user-001')).toBeInTheDocument();
    expect(screen.getByText('user-002')).toBeInTheDocument();
  });

  it('renders empty state with "No sessions found."', () => {
    (useSessions as any).mockReturnValue({
      sessions: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionsTable />);
    expect(screen.getByText('No sessions found.')).toBeInTheDocument();
  });

  it('search input filters sessions', async () => {
    const user = userEvent.setup();

    (useSessions as any).mockReturnValue({
      sessions: mockSessions,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionsTable />);

    const searchInput = screen.getByPlaceholderText('Search by session ID or user ID...');
    await user.type(searchInput, 'sess-abc');

    await waitFor(() => {
      expect(screen.getByText('sess-abc-123')).toBeInTheDocument();
      expect(screen.queryByText('sess-def-456')).not.toBeInTheDocument();
    });
  });

  it('renders error state with retry button', () => {
    const refetchFn = vi.fn();
    (useSessions as any).mockReturnValue({
      sessions: [],
      loading: false,
      error: 'Failed to fetch sessions: 500',
      refetch: refetchFn,
    });

    render(<SessionsTable />);
    expect(screen.getByText('Error Loading Sessions')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });

  it('displays session count in footer', () => {
    (useSessions as any).mockReturnValue({
      sessions: mockSessions,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionsTable />);
    expect(screen.getByText('2 session(s) total')).toBeInTheDocument();
  });
});
