import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { ChannelSelector } from '@/components/chat/ChannelSelector';

vi.mock('@/hooks/useGateway', () => ({
  useChannels: vi.fn(),
}));

import { useChannels } from '@/hooks/useGateway';

const mockChannels = [
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
    enabled: true,
    created_at: '2024-02-01T00:00:00Z',
    updated_at: '2024-02-01T00:00:00Z',
  },
  {
    channel_id: 'disabled-channel',
    channel_type: 'discord',
    status: 'disconnected',
    config: {
      api_token: 'dc-test',
      rate_limit_per_minute: 60,
      max_message_length: 2000,
      supports_threads: true,
      supports_buttons: true,
      supports_embeds: true,
      custom_config: {},
    },
    enabled: false,
    created_at: '2024-03-01T00:00:00Z',
    updated_at: '2024-03-01T00:00:00Z',
  },
];

describe('ChannelSelector', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders "Web (Direct)" default option', () => {
    (useChannels as any).mockReturnValue({
      channels: mockChannels,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <ChannelSelector selectedChannelId={null} onChannelChange={vi.fn()} />
    );

    expect(screen.getByText('Web (Direct)')).toBeInTheDocument();
  });

  it('renders select trigger as combobox', () => {
    (useChannels as any).mockReturnValue({
      channels: mockChannels,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <ChannelSelector selectedChannelId={null} onChannelChange={vi.fn()} />
    );

    const trigger = screen.getByRole('combobox');
    expect(trigger).toBeInTheDocument();
  });

  it('displays the select trigger as disabled when loading', () => {
    (useChannels as any).mockReturnValue({
      channels: [],
      loading: true,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <ChannelSelector selectedChannelId={null} onChannelChange={vi.fn()} />
    );

    const trigger = screen.getByRole('combobox');
    expect(trigger).toBeDisabled();
  });

  it('shows the currently selected channel', () => {
    (useChannels as any).mockReturnValue({
      channels: mockChannels,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <ChannelSelector selectedChannelId="slack-main" onChannelChange={vi.fn()} />
    );

    expect(screen.getByText('slack-main')).toBeInTheDocument();
  });

  it('reads from localStorage on mount', () => {
    localStorage.setItem('selectedChannel', 'slack-main');
    const onChannelChange = vi.fn();

    (useChannels as any).mockReturnValue({
      channels: mockChannels,
      loading: false,
      error: null,
      refetch: vi.fn(),
    });

    render(
      <ChannelSelector selectedChannelId={null} onChannelChange={onChannelChange} />
    );

    expect(onChannelChange).toHaveBeenCalledWith('slack-main');
  });
});
