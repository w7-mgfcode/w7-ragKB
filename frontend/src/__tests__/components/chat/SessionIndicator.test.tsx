import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SessionIndicator } from '@/components/chat/SessionIndicator';

vi.mock('@/hooks/useGateway', () => ({
  useSession: vi.fn(),
}));

import { useSession } from '@/hooks/useGateway';

const mockSession = {
  session_id: 'sess-abcdef12-3456-7890-abcd-ef1234567890',
  channel_id: 'slack-main',
  user_id: 'user-001',
  chat_id: 'chat-001',
  session_type: 'main',
  activation_mode: 'always',
  tool_allowlist: ['rag', 'web_search'],
  tool_denylist: [],
  message_count: 42,
  token_usage: { input: 1000, output: 500 },
  memory_usage: 35,
  created_at: '2024-01-01T00:00:00Z',
  last_activity_at: new Date().toISOString(), // Recent activity = green health dot
};

describe('SessionIndicator', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders "No active session" when sessionId is null', () => {
    (useSession as any).mockReturnValue({
      session: null,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionIndicator sessionId={null} />);

    expect(screen.getByText('No active session')).toBeInTheDocument();
  });

  it('renders loading state when session is loading', () => {
    (useSession as any).mockReturnValue({
      session: null,
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionIndicator sessionId="sess-abcdef12" />);

    expect(screen.getByText('Loading session...')).toBeInTheDocument();
  });

  it('renders session info when sessionId is provided and session is loaded', () => {
    (useSession as any).mockReturnValue({
      session: mockSession,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionIndicator sessionId={mockSession.session_id} />);

    // Truncated session ID: first 8 chars + '...'
    expect(screen.getByText('sess-abc...')).toBeInTheDocument();

    // Channel badge
    expect(screen.getByText('slack-main')).toBeInTheDocument();

    // Session type badge
    expect(screen.getByText('main')).toBeInTheDocument();

    // Activation mode
    expect(screen.getByText('always')).toBeInTheDocument();

    // Message count
    expect(screen.getByText('42 msgs')).toBeInTheDocument();
  });

  it('renders copy session ID button', () => {
    (useSession as any).mockReturnValue({
      session: mockSession,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionIndicator sessionId={mockSession.session_id} />);

    expect(screen.getByRole('button', { name: /Copy session ID/i })).toBeInTheDocument();
  });

  it('renders memory progress bar when memory_usage exceeds 50%', () => {
    const highMemSession = { ...mockSession, memory_usage: 75 };

    (useSession as any).mockReturnValue({
      session: highMemSession,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionIndicator sessionId={highMemSession.session_id} />);

    expect(screen.getByText('75%')).toBeInTheDocument();
  });

  it('does not render memory bar when memory_usage is below 50%', () => {
    const lowMemSession = { ...mockSession, memory_usage: 30 };

    (useSession as any).mockReturnValue({
      session: lowMemSession,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<SessionIndicator sessionId={lowMemSession.session_id} />);

    expect(screen.queryByText('30%')).not.toBeInTheDocument();
  });

  it('uses provided channelId prop over session channel_id', () => {
    (useSession as any).mockReturnValue({
      session: mockSession,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <SessionIndicator
        sessionId={mockSession.session_id}
        channelId="custom-channel"
      />
    );

    expect(screen.getByText('custom-channel')).toBeInTheDocument();
  });
});
