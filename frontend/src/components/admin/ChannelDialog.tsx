/**
 * Channel Dialog Component
 * 
 * Dialog for creating or editing messaging channel integrations.
 * Features:
 * - Form validation with zod
 * - Platform-specific help text and configuration
 * - Test Connection button to verify API token
 * - Support for Slack, Telegram, Discord, WhatsApp
 * - Webhook URL display for webhook-based channels
 * - Rate limiting configuration
 */

import * as React from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import * as z from 'zod';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, CheckCircle2, AlertCircle, Info, Copy } from 'lucide-react';
import { ChannelType, type Channel } from '@/types/gateway';
import { createChannel, updateChannel, testChannelConnection } from '@/lib/api';

const channelSchema = z.object({
  channel_id: z.string().min(1, 'Channel ID is required').max(100, 'Channel ID must be at most 100 characters'),
  channel_type: z.nativeEnum(ChannelType),
  api_token: z.string().min(1, 'API token is required'),
  webhook_url: z.string().url('Must be a valid URL').optional().or(z.literal('')),
  rate_limit_per_minute: z.number().min(1, 'Rate limit must be greater than 0').max(1000, 'Rate limit must be at most 1000'),
  enabled: z.boolean(),
});

type ChannelFormData = z.infer<typeof channelSchema>;

interface ChannelDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  channel?: Channel | null;
  onSuccess?: () => void;
}

// Platform-specific help text and configuration
const PLATFORM_INFO = {
  slack: {
    name: 'Slack',
    tokenLabel: 'Bot User OAuth Token',
    tokenPlaceholder: 'xoxb-...',
    tokenHelp: 'Create a Slack App at api.slack.com/apps, add a bot user, and copy the Bot User OAuth Token. Required scopes: channels:history, channels:read, chat:write, files:read, users:read.',
    webhookRequired: false,
    webhookHelp: '',
    defaultRateLimit: 60,
  },
  telegram: {
    name: 'Telegram',
    tokenLabel: 'Bot Token',
    tokenPlaceholder: '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11',
    tokenHelp: 'Create a bot via @BotFather on Telegram and copy the bot token. The token format is: <bot_id>:<auth_token>',
    webhookRequired: true,
    webhookHelp: 'Telegram requires a webhook URL for receiving messages. After creating the channel, configure your webhook endpoint to point to the generated URL.',
    defaultRateLimit: 30,
  },
  discord: {
    name: 'Discord',
    tokenLabel: 'Bot Token',
    tokenPlaceholder: 'paste-your-discord-bot-token-here (format: base64.base64.base64)',
    tokenHelp: 'Create a Discord Application at discord.com/developers/applications, add a bot, and copy the bot token. Required intents: GUILDS, GUILD_MESSAGES, MESSAGE_CONTENT, DIRECT_MESSAGES.',
    webhookRequired: false,
    webhookHelp: '',
    defaultRateLimit: 50,
  },
  whatsapp: {
    name: 'WhatsApp',
    tokenLabel: 'Access Token',
    tokenPlaceholder: 'EAAxxxxxxxxxx...',
    tokenHelp: 'Create a WhatsApp Business App via Meta for Developers (developers.facebook.com), generate a permanent access token, and copy it here. Requires WhatsApp Business API access.',
    webhookRequired: true,
    webhookHelp: 'WhatsApp requires a webhook URL for receiving messages. After creating the channel, configure your Meta App webhook to point to the generated URL with verify token.',
    defaultRateLimit: 20,
  },
};

function generateId(type: string): string {
  return `${type}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

export function ChannelDialog({
  open,
  onOpenChange,
  channel,
  onSuccess,
}: ChannelDialogProps) {
  const [isSaving, setIsSaving] = React.useState(false);
  const [isTesting, setIsTesting] = React.useState(false);
  const [testResult, setTestResult] = React.useState<'success' | 'error' | null>(null);
  const [testMessage, setTestMessage] = React.useState<string>('');
  const [generatedWebhookUrl, setGeneratedWebhookUrl] = React.useState<string>('');

  const isEditing = !!channel;

  const form = useForm<ChannelFormData>({
    resolver: zodResolver(channelSchema),
    defaultValues: {
      channel_id: channel?.channel_id || '',
      channel_type: channel?.channel_type || ChannelType.SLACK,
      api_token: channel?.config?.api_token || '',
      webhook_url: channel?.config?.webhook_url || '',
      rate_limit_per_minute: channel?.config?.rate_limit_per_minute || 60,
      enabled: channel?.enabled ?? true,
    },
  });

  const selectedType = form.watch('channel_type');
  const platformInfo = PLATFORM_INFO[selectedType];

  React.useEffect(() => {
    if (channel) {
      form.reset({
        channel_id: channel.channel_id,
        channel_type: channel.channel_type,
        api_token: channel.config?.api_token || '',
        webhook_url: channel.config?.webhook_url || '',
        rate_limit_per_minute: channel.config?.rate_limit_per_minute || 60,
        enabled: channel.enabled,
      });
      setGeneratedWebhookUrl(channel.config?.webhook_url || '');
    } else {
      const defaultType = ChannelType.SLACK;
      form.reset({
        channel_id: generateId(defaultType),
        channel_type: defaultType,
        api_token: '',
        webhook_url: '',
        rate_limit_per_minute: PLATFORM_INFO[defaultType].defaultRateLimit,
        enabled: true,
      });
      setGeneratedWebhookUrl('');
    }
    setTestResult(null);
    setTestMessage('');
  }, [channel, form, open]);

  // Update channel_id and rate_limit when channel_type changes
  React.useEffect(() => {
    if (!isEditing) {
      const currentType = form.getValues('channel_type');
      form.setValue('channel_id', generateId(currentType));
      form.setValue('rate_limit_per_minute', PLATFORM_INFO[currentType].defaultRateLimit);
    }
  }, [form.watch('channel_type'), isEditing, form]);

  const handleTestConnection = async () => {
    const isValid = await form.trigger(['channel_id', 'api_token']);
    if (!isValid) return;

    setIsTesting(true);
    setTestResult(null);
    setTestMessage('');

    try {
      if (isEditing) {
        // Test existing channel
        const result = await testChannelConnection(channel.channel_id);
        setTestResult(result.success ? 'success' : 'error');
        setTestMessage(result.message);
        toast.success(result.message);
      } else {
        // For new channels, we can't test until they're created
        // Just validate the token format
        const token = form.getValues('api_token');
        const type = form.getValues('channel_type');
        
        let isValidFormat = false;
        switch (type) {
          case ChannelType.SLACK:
            isValidFormat = token.startsWith('xoxb-');
            break;
          case ChannelType.TELEGRAM:
            isValidFormat = /^\d+:[A-Za-z0-9_-]+$/.test(token);
            break;
          case ChannelType.DISCORD:
            isValidFormat = token.length > 50; // Discord tokens are long base64 strings
            break;
          case ChannelType.WHATSAPP:
            isValidFormat = token.startsWith('EAA');
            break;
        }

        if (isValidFormat) {
          setTestResult('success');
          setTestMessage('Token format appears valid. Full connection test will occur after creation.');
          toast.success('Token format validated successfully!');
        } else {
          setTestResult('error');
          setTestMessage(`Invalid token format for ${platformInfo.name}. Please check the token and try again.`);
          toast.error('Invalid token format');
        }
      }
    } catch (error) {
      setTestResult('error');
      setTestMessage((error as Error).message);
      toast.error('Connection test failed: ' + (error as Error).message);
    } finally {
      setIsTesting(false);
    }
  };

  const handleCopyWebhookUrl = () => {
    if (generatedWebhookUrl) {
      navigator.clipboard.writeText(generatedWebhookUrl);
      toast.success('Webhook URL copied to clipboard!');
    }
  };

  const onSubmit = async (data: ChannelFormData) => {
    setIsSaving(true);
    try {
      const payload = {
        channel_id: data.channel_id,
        channel_type: data.channel_type,
        api_token: data.api_token,
        webhook_url: data.webhook_url || undefined,
        rate_limit_per_minute: data.rate_limit_per_minute,
        enabled: data.enabled,
      };

      if (isEditing) {
        await updateChannel(channel.channel_id, payload);
        toast.success('Channel updated successfully!');
      } else {
        const created = await createChannel(payload);
        // Store generated webhook URL if present
        if (created.config?.webhook_url) {
          setGeneratedWebhookUrl(created.config.webhook_url);
        }
        toast.success('Channel created successfully!');
      }
      
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      toast.error('Failed to save channel: ' + (error as Error).message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Channel' : 'Create New Channel'}</DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Update the channel configuration below.'
              : 'Configure a new messaging platform integration.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="channel_type">Channel Type</Label>
            <Select
              value={form.watch('channel_type')}
              onValueChange={(value) => form.setValue('channel_type', value as ChannelType)}
              disabled={isEditing}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select platform" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ChannelType.SLACK}>Slack</SelectItem>
                <SelectItem value={ChannelType.TELEGRAM}>Telegram</SelectItem>
                <SelectItem value={ChannelType.DISCORD}>Discord</SelectItem>
                <SelectItem value={ChannelType.WHATSAPP}>WhatsApp</SelectItem>
              </SelectContent>
            </Select>
            {form.formState.errors.channel_type && (
              <p className="text-sm text-destructive">{form.formState.errors.channel_type.message}</p>
            )}
          </div>

          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription className="text-sm">
              <strong>{platformInfo.name} Setup:</strong> {platformInfo.tokenHelp}
            </AlertDescription>
          </Alert>

          <div className="space-y-2">
            <Label htmlFor="channel_id">Channel ID</Label>
            <Input
              id="channel_id"
              {...form.register('channel_id')}
              placeholder={`${selectedType}-123`}
              disabled={isEditing}
            />
            {form.formState.errors.channel_id && (
              <p className="text-sm text-destructive">{form.formState.errors.channel_id.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="api_token">{platformInfo.tokenLabel}</Label>
            <Input
              id="api_token"
              {...form.register('api_token')}
              type="password"
              placeholder={platformInfo.tokenPlaceholder}
              className="font-mono text-sm"
            />
            {form.formState.errors.api_token && (
              <p className="text-sm text-destructive">{form.formState.errors.api_token.message}</p>
            )}
          </div>

          {platformInfo.webhookRequired && (
            <>
              <div className="space-y-2">
                <Label htmlFor="webhook_url">Webhook URL (Optional)</Label>
                <Input
                  id="webhook_url"
                  {...form.register('webhook_url')}
                  placeholder="https://your-domain.com/webhook"
                  className="font-mono text-sm"
                />
                {form.formState.errors.webhook_url && (
                  <p className="text-sm text-destructive">{form.formState.errors.webhook_url.message}</p>
                )}
              </div>
              <Alert>
                <Info className="h-4 w-4" />
                <AlertDescription className="text-sm">
                  {platformInfo.webhookHelp}
                </AlertDescription>
              </Alert>
            </>
          )}

          {generatedWebhookUrl && isEditing && (
            <div className="space-y-2">
              <Label>Generated Webhook URL</Label>
              <div className="flex gap-2">
                <Input value={generatedWebhookUrl} readOnly className="font-mono text-sm" />
                <Button type="button" variant="outline" size="icon" onClick={handleCopyWebhookUrl}>
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <p className="text-xs text-muted-foreground">
                Configure this URL in your {platformInfo.name} settings to receive messages.
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="rate_limit_per_minute">Rate Limit (messages per minute)</Label>
            <Input
              id="rate_limit_per_minute"
              type="number"
              {...form.register('rate_limit_per_minute', { valueAsNumber: true })}
              min={1}
              max={1000}
            />
            {form.formState.errors.rate_limit_per_minute && (
              <p className="text-sm text-destructive">{form.formState.errors.rate_limit_per_minute.message}</p>
            )}
            <p className="text-xs text-muted-foreground">
              Maximum number of messages to send per minute. Recommended: {platformInfo.defaultRateLimit}
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <Switch
              id="enabled"
              checked={form.watch('enabled')}
              onCheckedChange={(checked) => form.setValue('enabled', checked)}
            />
            <Label htmlFor="enabled">Enable this channel</Label>
          </div>

          {testResult && (
            <Alert variant={testResult === 'success' ? 'default' : 'destructive'}>
              {testResult === 'success' ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <AlertCircle className="h-4 w-4" />
              )}
              <AlertDescription>{testMessage}</AlertDescription>
            </Alert>
          )}

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleTestConnection}
              disabled={isTesting || isSaving}
            >
              {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Test Connection
            </Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving || isTesting}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEditing ? 'Update' : 'Create'} Channel
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
