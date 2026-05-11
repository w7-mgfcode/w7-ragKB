import { useState, useEffect } from 'react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useChannels } from '@/hooks/useGateway';
import { ChannelType, ChannelStatus } from '@/types/gateway';
import { MessageSquare, Send, Gamepad2, Phone, Globe } from 'lucide-react';
import { cn } from '@/lib/utils';

const STORAGE_KEY = 'selectedChannel';

const channelIcons: Record<ChannelType, React.ReactNode> = {
  [ChannelType.SLACK]: <MessageSquare className="h-4 w-4" />,
  [ChannelType.TELEGRAM]: <Send className="h-4 w-4" />,
  [ChannelType.DISCORD]: <Gamepad2 className="h-4 w-4" />,
  [ChannelType.WHATSAPP]: <Phone className="h-4 w-4" />,
};

interface ChannelSelectorProps {
  selectedChannelId: string | null;
  onChannelChange: (channelId: string | null) => void;
}

export const ChannelSelector = ({
  selectedChannelId,
  onChannelChange,
}: ChannelSelectorProps) => {
  const { channels, loading } = useChannels(undefined, true);
  const [initialized, setInitialized] = useState(false);

  // Load initial value from localStorage on mount
  useEffect(() => {
    if (!initialized) {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        onChannelChange(stored);
      }
      setInitialized(true);
    }
  }, [initialized, onChannelChange]);

  const handleChange = (value: string) => {
    const channelId = value === 'web-direct' ? null : value;
    if (channelId) {
      localStorage.setItem(STORAGE_KEY, channelId);
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
    onChannelChange(channelId);
  };

  const enabledChannels = channels.filter((ch) => ch.enabled);

  return (
    <Select
      value={selectedChannelId ?? 'web-direct'}
      onValueChange={handleChange}
      disabled={loading}
    >
      <SelectTrigger className="h-8 w-[200px] text-xs">
        <SelectValue placeholder="Select channel" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="web-direct">
          <span className="flex items-center gap-2">
            <Globe className="h-4 w-4" />
            <span>Web (Direct)</span>
          </span>
        </SelectItem>
        {enabledChannels.map((channel) => (
          <SelectItem key={channel.channel_id} value={channel.channel_id}>
            <span className="flex items-center gap-2">
              {channelIcons[channel.channel_type]}
              <span className="truncate max-w-[120px]">
                {channel.channel_id}
              </span>
              <span
                className={cn(
                  'inline-block h-2 w-2 rounded-full shrink-0',
                  channel.status === ChannelStatus.CONNECTED
                    ? 'bg-green-500'
                    : 'bg-red-500'
                )}
              />
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
};
