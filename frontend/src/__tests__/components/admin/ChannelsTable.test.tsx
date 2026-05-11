import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ChannelsTable } from '@/components/admin/ChannelsTable';

// Mock child dialog/wizard components to isolate unit tests
vi.mock('@/components/admin/ChannelDialog', () => ({
  ChannelDialog: () => null,
}));
vi.mock('@/components/admin/ChannelConfigWizard', () => ({
  ChannelConfigWizard: () => null,
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/hooks/useGateway', () => ({
  useChannels: vi.fn(),
}));

vi.mock('@/lib/api', () => ({
  createChannel: vi.fn(),
  updateChannel: vi.fn(),
  deleteChannel: vi.fn(),
  testChannelConnection: vi.fn(),
}));

import { useChannels } from '@/hooks/useGateway';

describe('ChannelsTable', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state', () => {
    (useChannels as any).mockReturnValue({
      channels: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelsTable />);
    expect(screen.getByText('Loading channels...')).toBeInTheDocument();
  });

  it('renders channels data in table', () => {
    (useChannels as any).mockReturnValue({
      channels: [
        {
          channel_id: 'slack-main',
          channel_type: 'slack',
          status: 'connected',
          config: {
            api_token: 'xoxb-test',
            rate_limit_per_minute: 60,
            max_message_length: 4000,
            supports_threads: true,
            supports_buttons: false,
            supports_embeds: false,
            custom_config: {},
          },
          enabled: true,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        {
          channel_id: 'telegram-bot',
          channel_type: 'telegram',
          status: 'disconnected',
          config: {
            api_token: 'tg-test',
            rate_limit_per_minute: 30,
            max_message_length: 4096,
            supports_threads: false,
            supports_buttons: true,
            supports_embeds: false,
            custom_config: {},
          },
          enabled: false,
          created_at: '2024-02-01T00:00:00Z',
          updated_at: '2024-02-01T00:00:00Z',
        },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelsTable />);
    expect(screen.getByText('slack-main')).toBeInTheDocument();
    expect(screen.getByText('telegram-bot')).toBeInTheDocument();
    expect(screen.getByText('slack')).toBeInTheDocument();
    expect(screen.getByText('telegram')).toBeInTheDocument();
  });

  it('renders empty state with "No channels found."', () => {
    (useChannels as any).mockReturnValue({
      channels: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelsTable />);
    expect(screen.getByText('No channels found.')).toBeInTheDocument();
  });

  it('search input filters channels', async () => {
    const user = userEvent.setup();

    (useChannels as any).mockReturnValue({
      channels: [
        {
          channel_id: 'slack-main',
          channel_type: 'slack',
          status: 'connected',
          config: {
            api_token: 'xoxb-test',
            rate_limit_per_minute: 60,
            max_message_length: 4000,
            supports_threads: true,
            supports_buttons: false,
            supports_embeds: false,
            custom_config: {},
          },
          enabled: true,
          created_at: '2024-01-01T00:00:00Z',
          updated_at: '2024-01-01T00:00:00Z',
        },
        {
          channel_id: 'discord-guild',
          channel_type: 'discord',
          status: 'connected',
          config: {
            api_token: 'dc-test',
            rate_limit_per_minute: 60,
            max_message_length: 2000,
            supports_threads: true,
            supports_buttons: true,
            supports_embeds: true,
            custom_config: {},
          },
          enabled: true,
          created_at: '2024-01-15T00:00:00Z',
          updated_at: '2024-01-15T00:00:00Z',
        },
      ],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelsTable />);

    const searchInput = screen.getByPlaceholderText('Search by channel ID...');
    await user.type(searchInput, 'slack');

    await waitFor(() => {
      expect(screen.getByText('slack-main')).toBeInTheDocument();
      expect(screen.queryByText('discord-guild')).not.toBeInTheDocument();
    });
  });

  it('"Add Channel" button exists', () => {
    (useChannels as any).mockReturnValue({
      channels: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelsTable />);
    expect(screen.getByRole('button', { name: /Add Channel/i })).toBeInTheDocument();
  });

  it('"Setup Wizard" button exists', () => {
    (useChannels as any).mockReturnValue({
      channels: [],
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(<ChannelsTable />);
    expect(screen.getByRole('button', { name: /Setup Wizard/i })).toBeInTheDocument();
  });

  it('renders error state with retry button', () => {
    const refetchFn = vi.fn();
    (useChannels as any).mockReturnValue({
      channels: [],
      loading: false,
      error: 'Network error',
      refetch: refetchFn,
    });

    render(<ChannelsTable />);
    expect(screen.getByText('Error Loading Channels')).toBeInTheDocument();
    expect(screen.getByText(/Network error/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Retry/i })).toBeInTheDocument();
  });
});
