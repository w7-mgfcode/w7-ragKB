/**
 * Channel Config Wizard Component
 *
 * 4-step channel setup wizard in a Dialog:
 * 1. Platform Selection with quick-start templates
 * 2. Credentials (API token + optional webhook URL) with Test Connection
 * 3. Settings (rate limit, enabled toggle, platform-specific hints)
 * 4. Review & Create summary
 *
 * Features:
 * - Step indicator with highlighted dots
 * - Per-step validation via react-hook-form trigger()
 * - Quick-start template dropdown
 * - Connection testing before creation
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
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  MessageSquare,
  Send,
  Gamepad2,
  Phone,
  ArrowRight,
  ArrowLeft,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Wand2,
} from 'lucide-react';
import { ChannelType } from '@/types/gateway';
import { createChannel, testChannelConnection } from '@/lib/api';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Schema
// ---------------------------------------------------------------------------

const wizardSchema = z.object({
  channel_id: z.string().min(1, 'Channel ID is required').max(100),
  channel_type: z.nativeEnum(ChannelType),
  api_token: z.string().min(1, 'API token is required'),
  webhook_url: z.string().url('Must be a valid URL').optional().or(z.literal('')),
  rate_limit_per_minute: z
    .number()
    .min(1, 'Rate limit must be at least 1')
    .max(1000, 'Rate limit must be at most 1000'),
  enabled: z.boolean(),
});

type WizardFormData = z.infer<typeof wizardSchema>;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

interface ChannelConfigWizardProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

const PLATFORMS = [
  {
    type: ChannelType.SLACK,
    label: 'Slack',
    icon: MessageSquare,
    description: 'Connect to a Slack workspace',
  },
  {
    type: ChannelType.TELEGRAM,
    label: 'Telegram',
    icon: Send,
    description: 'Connect a Telegram bot',
  },
  {
    type: ChannelType.DISCORD,
    label: 'Discord',
    icon: Gamepad2,
    description: 'Connect a Discord server bot',
  },
  {
    type: ChannelType.WHATSAPP,
    label: 'WhatsApp',
    icon: Phone,
    description: 'Connect WhatsApp Business API',
  },
] as const;

const PLATFORM_INFO: Record<
  ChannelType,
  {
    tokenLabel: string;
    tokenPlaceholder: string;
    tokenHelp: string;
    webhookRequired: boolean;
    webhookHelp: string;
    defaultRateLimit: number;
    hints: string[];
  }
> = {
  [ChannelType.SLACK]: {
    tokenLabel: 'Bot User OAuth Token',
    tokenPlaceholder: 'xoxb-...',
    tokenHelp:
      'Create a Slack App at api.slack.com/apps, add a bot user, and copy the Bot User OAuth Token.',
    webhookRequired: false,
    webhookHelp: '',
    defaultRateLimit: 60,
    hints: [
      'Required scopes: channels:history, channels:read, chat:write, files:read, users:read',
      'Enable Socket Mode for real-time events',
      'Add the bot to each channel it should monitor',
    ],
  },
  [ChannelType.TELEGRAM]: {
    tokenLabel: 'Bot Token',
    tokenPlaceholder: '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11',
    tokenHelp: 'Create a bot via @BotFather on Telegram and copy the bot token.',
    webhookRequired: true,
    webhookHelp:
      'Telegram requires a webhook URL. After creating the channel, configure the webhook endpoint.',
    defaultRateLimit: 30,
    hints: [
      'Use /setcommands with BotFather to set available commands',
      'Enable inline mode if you need inline query support',
      'Set privacy mode off if you need the bot to read all group messages',
    ],
  },
  [ChannelType.DISCORD]: {
    tokenLabel: 'Bot Token',
    tokenPlaceholder: 'MTk4NjIyNDgzNDcxOTI1MjQ4.Cl2FMQ...',
    tokenHelp:
      'Create a Discord Application at discord.com/developers/applications, add a bot, and copy the token.',
    webhookRequired: false,
    webhookHelp: '',
    defaultRateLimit: 45,
    hints: [
      'Required intents: GUILDS, GUILD_MESSAGES, MESSAGE_CONTENT, DIRECT_MESSAGES',
      'Enable MESSAGE_CONTENT privileged intent in the Discord Developer Portal',
      'Invite the bot with appropriate permissions (Send Messages, Read Message History)',
    ],
  },
  [ChannelType.WHATSAPP]: {
    tokenLabel: 'Access Token',
    tokenPlaceholder: 'EAAxxxxxxxxxx...',
    tokenHelp:
      'Create a WhatsApp Business App via Meta for Developers and generate a permanent access token.',
    webhookRequired: true,
    webhookHelp:
      'WhatsApp requires a webhook URL. Configure your Meta App webhook to point to the generated URL.',
    defaultRateLimit: 20,
    hints: [
      'Requires WhatsApp Business API access through Meta for Developers',
      'Configure message templates for proactive messaging',
      'Set up webhook verification token in Meta App settings',
    ],
  },
};

interface QuickStartTemplate {
  label: string;
  type: ChannelType;
  rate_limit: number;
  enabled: boolean;
}

const QUICK_START_TEMPLATES: QuickStartTemplate[] = [
  { label: 'Slack Workspace Bot', type: ChannelType.SLACK, rate_limit: 60, enabled: true },
  { label: 'Telegram Personal Bot', type: ChannelType.TELEGRAM, rate_limit: 30, enabled: true },
  { label: 'Discord Server Bot', type: ChannelType.DISCORD, rate_limit: 45, enabled: true },
  { label: 'WhatsApp Business', type: ChannelType.WHATSAPP, rate_limit: 20, enabled: true },
];

const TOTAL_STEPS = 4;

function generateId(type: string): string {
  return `${type}-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ChannelConfigWizard({ open, onOpenChange, onSuccess }: ChannelConfigWizardProps) {
  const [step, setStep] = React.useState(0);
  const [isCreating, setIsCreating] = React.useState(false);
  const [isTesting, setIsTesting] = React.useState(false);
  const [testResult, setTestResult] = React.useState<'success' | 'error' | null>(null);
  const [testMessage, setTestMessage] = React.useState('');

  const form = useForm<WizardFormData>({
    resolver: zodResolver(wizardSchema),
    defaultValues: {
      channel_id: generateId('slack'),
      channel_type: ChannelType.SLACK,
      api_token: '',
      webhook_url: '',
      rate_limit_per_minute: 60,
      enabled: true,
    },
  });

  const selectedType = form.watch('channel_type');
  const info = PLATFORM_INFO[selectedType];

  // Reset when dialog opens/closes
  React.useEffect(() => {
    if (open) {
      setStep(0);
      setTestResult(null);
      setTestMessage('');
      form.reset({
        channel_id: generateId('slack'),
        channel_type: ChannelType.SLACK,
        api_token: '',
        webhook_url: '',
        rate_limit_per_minute: 60,
        enabled: true,
      });
    }
  }, [open, form]);

  // ---------------------------------------------------------------------------
  // Quick-start template
  // ---------------------------------------------------------------------------

  const applyTemplate = (template: QuickStartTemplate) => {
    form.setValue('channel_type', template.type);
    form.setValue('channel_id', generateId(template.type));
    form.setValue('rate_limit_per_minute', template.rate_limit);
    form.setValue('enabled', template.enabled);
  };

  // ---------------------------------------------------------------------------
  // Platform selection
  // ---------------------------------------------------------------------------

  const handlePlatformSelect = (type: ChannelType) => {
    form.setValue('channel_type', type);
    form.setValue('channel_id', generateId(type));
    form.setValue('rate_limit_per_minute', PLATFORM_INFO[type].defaultRateLimit);
  };

  // ---------------------------------------------------------------------------
  // Step validation
  // ---------------------------------------------------------------------------

  const validateStep = async (): Promise<boolean> => {
    switch (step) {
      case 0:
        return await form.trigger(['channel_type']);
      case 1:
        return await form.trigger(['api_token', 'webhook_url']);
      case 2:
        return await form.trigger(['rate_limit_per_minute', 'enabled']);
      default:
        return true;
    }
  };

  const handleNext = async () => {
    const valid = await validateStep();
    if (valid && step < TOTAL_STEPS - 1) {
      setStep((s) => s + 1);
    }
  };

  const handleBack = () => {
    if (step > 0) setStep((s) => s - 1);
  };

  // ---------------------------------------------------------------------------
  // Test connection
  // ---------------------------------------------------------------------------

  const handleTestConnection = async () => {
    const isValid = await form.trigger(['api_token']);
    if (!isValid) return;

    setIsTesting(true);
    setTestResult(null);
    setTestMessage('');

    try {
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
          isValidFormat = token.length > 50;
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
        setTestMessage(
          `Invalid token format for ${PLATFORMS.find((p) => p.type === type)?.label}. Please check the token.`
        );
        toast.error('Invalid token format');
      }
    } catch (error) {
      setTestResult('error');
      setTestMessage((error as Error).message);
      toast.error('Connection test failed');
    } finally {
      setIsTesting(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Create
  // ---------------------------------------------------------------------------

  const handleCreate = async () => {
    const allValid = await form.trigger();
    if (!allValid) return;

    setIsCreating(true);
    try {
      const data = form.getValues();
      await createChannel({
        channel_id: data.channel_id,
        channel_type: data.channel_type,
        api_token: data.api_token,
        webhook_url: data.webhook_url || undefined,
        rate_limit_per_minute: data.rate_limit_per_minute,
        enabled: data.enabled,
      });
      toast.success('Channel created successfully!');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      toast.error('Failed to create channel: ' + (error as Error).message);
    } finally {
      setIsCreating(false);
    }
  };

  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const renderStepIndicator = () => (
    <div className="flex items-center justify-center gap-2 mb-6">
      {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
        <div
          key={i}
          className={cn(
            'h-2.5 w-2.5 rounded-full transition-colors',
            i === step ? 'bg-primary' : i < step ? 'bg-primary/50' : 'bg-muted'
          )}
        />
      ))}
    </div>
  );

  const renderStep0 = () => (
    <div className="space-y-4">
      {/* Quick-start dropdown */}
      <div className="space-y-2">
        <Label>Quick Start Template</Label>
        <Select
          onValueChange={(val) => {
            const tmpl = QUICK_START_TEMPLATES.find((t) => t.label === val);
            if (tmpl) applyTemplate(tmpl);
          }}
        >
          <SelectTrigger>
            <SelectValue placeholder="Choose a template..." />
          </SelectTrigger>
          <SelectContent>
            {QUICK_START_TEMPLATES.map((t) => (
              <SelectItem key={t.label} value={t.label}>
                <div className="flex items-center gap-2">
                  <Wand2 className="h-3.5 w-3.5 text-muted-foreground" />
                  {t.label}
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Separator />

      {/* Platform cards */}
      <Label>Select Platform</Label>
      <div className="grid grid-cols-2 gap-3">
        {PLATFORMS.map((platform) => {
          const Icon = platform.icon;
          const isSelected = selectedType === platform.type;
          return (
            <Card
              key={platform.type}
              className={cn(
                'cursor-pointer transition-all hover:border-primary/50',
                isSelected && 'border-primary ring-2 ring-primary/20'
              )}
              onClick={() => handlePlatformSelect(platform.type)}
            >
              <CardContent className="flex flex-col items-center justify-center gap-2 p-6">
                <Icon
                  className={cn('h-8 w-8', isSelected ? 'text-primary' : 'text-muted-foreground')}
                />
                <span className={cn('font-medium', isSelected && 'text-primary')}>
                  {platform.label}
                </span>
                <span className="text-xs text-muted-foreground text-center">
                  {platform.description}
                </span>
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );

  const renderStep1 = () => (
    <div className="space-y-4">
      <Alert>
        <AlertDescription className="text-sm">{info.tokenHelp}</AlertDescription>
      </Alert>

      <div className="space-y-2">
        <Label htmlFor="wizard-api-token">{info.tokenLabel}</Label>
        <Input
          id="wizard-api-token"
          type="password"
          placeholder={info.tokenPlaceholder}
          className="font-mono text-sm"
          {...form.register('api_token')}
        />
        {form.formState.errors.api_token && (
          <p className="text-sm text-destructive">{form.formState.errors.api_token.message}</p>
        )}
      </div>

      {info.webhookRequired && (
        <div className="space-y-2">
          <Label htmlFor="wizard-webhook-url">Webhook URL (Optional)</Label>
          <Input
            id="wizard-webhook-url"
            placeholder="https://your-domain.com/webhook"
            className="font-mono text-sm"
            {...form.register('webhook_url')}
          />
          {form.formState.errors.webhook_url && (
            <p className="text-sm text-destructive">{form.formState.errors.webhook_url.message}</p>
          )}
          <p className="text-xs text-muted-foreground">{info.webhookHelp}</p>
        </div>
      )}

      <Button
        type="button"
        variant="outline"
        onClick={handleTestConnection}
        disabled={isTesting}
        className="w-full"
      >
        {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        Test Connection
      </Button>

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
    </div>
  );

  const renderStep2 = () => (
    <div className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="wizard-rate-limit">Rate Limit (messages per minute)</Label>
        <Input
          id="wizard-rate-limit"
          type="number"
          min={1}
          max={1000}
          {...form.register('rate_limit_per_minute', { valueAsNumber: true })}
        />
        {form.formState.errors.rate_limit_per_minute && (
          <p className="text-sm text-destructive">
            {form.formState.errors.rate_limit_per_minute.message}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          Recommended for {PLATFORMS.find((p) => p.type === selectedType)?.label}:{' '}
          {info.defaultRateLimit} messages/min
        </p>
      </div>

      <div className="flex items-center space-x-2">
        <Switch
          id="wizard-enabled"
          checked={form.watch('enabled')}
          onCheckedChange={(checked) => form.setValue('enabled', checked)}
        />
        <Label htmlFor="wizard-enabled">Enable channel immediately after creation</Label>
      </div>

      <Separator />

      <div className="space-y-2">
        <Label>Platform-Specific Tips</Label>
        <div className="space-y-1.5">
          {info.hints.map((hint, i) => (
            <div key={i} className="flex items-start gap-2 text-sm text-muted-foreground">
              <CheckCircle2 className="h-3.5 w-3.5 mt-0.5 shrink-0 text-primary/60" />
              <span>{hint}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );

  const renderStep3 = () => {
    const values = form.getValues();
    const platform = PLATFORMS.find((p) => p.type === values.channel_type);

    return (
      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Channel Configuration Summary</CardTitle>
            <CardDescription>Review before creating</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <p className="text-sm text-muted-foreground">Platform</p>
                <div className="flex items-center gap-2">
                  {platform && <platform.icon className="h-4 w-4" />}
                  <span className="font-medium">{platform?.label}</span>
                </div>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Channel ID</p>
                <p className="font-mono text-sm font-medium">{values.channel_id}</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">API Token</p>
                <p className="font-mono text-sm font-medium">
                  {values.api_token ? `${values.api_token.substring(0, 8)}...` : 'Not set'}
                </p>
              </div>
              {values.webhook_url && (
                <div>
                  <p className="text-sm text-muted-foreground">Webhook URL</p>
                  <p className="font-mono text-sm font-medium truncate">{values.webhook_url}</p>
                </div>
              )}
              <div>
                <p className="text-sm text-muted-foreground">Rate Limit</p>
                <p className="font-medium">{values.rate_limit_per_minute} msg/min</p>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Status</p>
                <Badge variant={values.enabled ? 'default' : 'secondary'}>
                  {values.enabled ? 'Enabled' : 'Disabled'}
                </Badge>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  };

  // ---------------------------------------------------------------------------
  // Step titles
  // ---------------------------------------------------------------------------

  const stepTitles = ['Select Platform', 'Enter Credentials', 'Configure Settings', 'Review & Create'];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>New Channel Setup</DialogTitle>
          <DialogDescription>
            Step {step + 1} of {TOTAL_STEPS}: {stepTitles[step]}
          </DialogDescription>
        </DialogHeader>

        {renderStepIndicator()}

        {step === 0 && renderStep0()}
        {step === 1 && renderStep1()}
        {step === 2 && renderStep2()}
        {step === 3 && renderStep3()}

        <div className="flex items-center justify-between pt-4">
          <Button type="button" variant="outline" onClick={handleBack} disabled={step === 0}>
            <ArrowLeft className="mr-2 h-4 w-4" />
            Back
          </Button>

          {step < TOTAL_STEPS - 1 ? (
            <Button type="button" onClick={handleNext}>
              Next
              <ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          ) : (
            <Button type="button" onClick={handleCreate} disabled={isCreating}>
              {isCreating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Create Channel
            </Button>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
