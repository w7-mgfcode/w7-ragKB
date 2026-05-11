/**
 * Webhook Dialog Component
 * 
 * Dialog for creating or editing webhook endpoints.
 * Features:
 * - Form validation with zod
 * - Auto-generated webhook ID and auth token
 * - Session search with combobox
 * - JSON schema validation for payload_schema
 * - Transform rules editor
 * - Copy URL and token buttons
 * - Test connection to verify target session exists
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
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, Copy, RefreshCw, CheckCircle2, AlertCircle } from 'lucide-react';
import type { Webhook } from '@/types/gateway';
import { createWebhook, updateWebhook, getSession } from '@/lib/api';
import { useSessions } from '@/hooks/useGateway';
import { WebhookTransformEditor } from './WebhookTransformEditor';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Check, ChevronsUpDown } from 'lucide-react';
import { cn } from '@/lib/utils';

const webhookSchema = z.object({
  webhook_id: z.string().min(1, 'Webhook ID is required').max(100, 'Webhook ID must be at most 100 characters'),
  target_session_id: z.string().min(1, 'Target session is required'),
  auth_token: z.string().min(1, 'Auth token is required'),
  payload_schema: z.string().optional().refine((val) => {
    if (!val || val.trim() === '') return true;
    try {
      JSON.parse(val);
      return true;
    } catch {
      return false;
    }
  }, 'Must be valid JSON'),
  transform_rules: z.string().optional().refine((val) => {
    if (!val || val.trim() === '') return true;
    try {
      JSON.parse(val);
      return true;
    } catch {
      return false;
    }
  }, 'Must be valid JSON'),
  enabled: z.boolean(),
});

type WebhookFormData = z.infer<typeof webhookSchema>;

interface WebhookDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  webhook?: Webhook | null;
  onSuccess?: () => void;
}

function generateId(): string {
  return `webhook-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

function generateToken(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return Array.from(array, byte => byte.toString(16).padStart(2, '0')).join('');
}

export function WebhookDialog({
  open,
  onOpenChange,
  webhook,
  onSuccess,
}: WebhookDialogProps) {
  const [isSaving, setIsSaving] = React.useState(false);
  const [isTesting, setIsTesting] = React.useState(false);
  const [testResult, setTestResult] = React.useState<'success' | 'error' | null>(null);
  const [sessionSearchOpen, setSessionSearchOpen] = React.useState(false);
  const [transformEditorOpen, setTransformEditorOpen] = React.useState(false);
  const { sessions } = useSessions();

  const isEditing = !!webhook;

  const form = useForm<WebhookFormData>({
    resolver: zodResolver(webhookSchema),
    defaultValues: {
      webhook_id: webhook?.webhook_id || generateId(),
      target_session_id: webhook?.target_session_id || '',
      auth_token: webhook?.auth_token || generateToken(),
      payload_schema: webhook?.payload_schema ? JSON.stringify(webhook.payload_schema, null, 2) : '',
      transform_rules: webhook?.transform_rules ? JSON.stringify(webhook.transform_rules, null, 2) : '',
      enabled: webhook?.enabled ?? true,
    },
  });

  React.useEffect(() => {
    if (webhook) {
      form.reset({
        webhook_id: webhook.webhook_id,
        target_session_id: webhook.target_session_id,
        auth_token: webhook.auth_token,
        payload_schema: webhook.payload_schema ? JSON.stringify(webhook.payload_schema, null, 2) : '',
        transform_rules: webhook.transform_rules ? JSON.stringify(webhook.transform_rules, null, 2) : '',
        enabled: webhook.enabled,
      });
    } else {
      form.reset({
        webhook_id: generateId(),
        target_session_id: '',
        auth_token: generateToken(),
        payload_schema: '',
        transform_rules: '',
        enabled: true,
      });
    }
    setTestResult(null);
  }, [webhook, form, open]);

  const handleRegenerateToken = () => {
    form.setValue('auth_token', generateToken());
    toast.success('Auth token regenerated!');
  };

  const handleCopyUrl = () => {
    if (webhook?.webhook_url) {
      navigator.clipboard.writeText(webhook.webhook_url);
      toast.success('Webhook URL copied to clipboard!');
    }
  };

  const handleCopyToken = () => {
    const token = form.getValues('auth_token');
    navigator.clipboard.writeText(token);
    toast.success('Auth token copied to clipboard!');
  };

  const handleTestConnection = async () => {
    const isValid = await form.trigger(['target_session_id']);
    if (!isValid) return;

    setIsTesting(true);
    setTestResult(null);

    try {
      const sessionId = form.getValues('target_session_id');
      await getSession(sessionId);
      setTestResult('success');
      toast.success('Target session exists and is accessible!');
    } catch (error) {
      setTestResult('error');
      toast.error('Target session not found or not accessible.');
    } finally {
      setIsTesting(false);
    }
  };

  const onSubmit = async (data: WebhookFormData) => {
    setIsSaving(true);
    try {
      const payload = {
        webhook_id: data.webhook_id,
        target_session_id: data.target_session_id,
        auth_token: data.auth_token,
        payload_schema: data.payload_schema && data.payload_schema.trim() !== '' 
          ? data.payload_schema 
          : undefined,
        transform_rules: data.transform_rules && data.transform_rules.trim() !== '' 
          ? data.transform_rules 
          : undefined,
        enabled: data.enabled,
      };

      if (isEditing) {
        await updateWebhook(webhook.webhook_id, payload);
        toast.success('Webhook updated successfully!');
      } else {
        await createWebhook(payload);
        toast.success('Webhook created successfully!');
      }
      
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      toast.error('Failed to save webhook: ' + (error as Error).message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Webhook' : 'Create New Webhook'}</DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Update the webhook configuration below.'
              : 'Configure a new webhook endpoint to trigger agent actions.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="webhook_id">Webhook ID</Label>
            <Input
              id="webhook_id"
              {...form.register('webhook_id')}
              placeholder="webhook-123"
              disabled={isEditing}
            />
            {form.formState.errors.webhook_id && (
              <p className="text-sm text-destructive">{form.formState.errors.webhook_id.message}</p>
            )}
          </div>

          {isEditing && webhook?.webhook_url && (
            <div className="space-y-2">
              <Label>Webhook URL</Label>
              <div className="flex gap-2">
                <Input value={webhook.webhook_url} readOnly className="font-mono text-sm" />
                <Button type="button" variant="outline" size="icon" onClick={handleCopyUrl}>
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="target_session_id">Target Session</Label>
            <Popover open={sessionSearchOpen} onOpenChange={setSessionSearchOpen}>
              <PopoverTrigger asChild>
                <Button
                  variant="outline"
                  role="combobox"
                  aria-expanded={sessionSearchOpen}
                  className="w-full justify-between font-mono text-sm"
                >
                  {form.watch('target_session_id') || 'Select session...'}
                  <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[600px] p-0">
                <Command>
                  <CommandInput placeholder="Search sessions..." />
                  <CommandEmpty>No session found.</CommandEmpty>
                  <CommandGroup className="max-h-[300px] overflow-y-auto">
                    {sessions?.map((session) => (
                      <CommandItem
                        key={session.session_id}
                        value={session.session_id}
                        onSelect={(value) => {
                          form.setValue('target_session_id', value);
                          setSessionSearchOpen(false);
                        }}
                      >
                        <Check
                          className={cn(
                            'mr-2 h-4 w-4',
                            form.watch('target_session_id') === session.session_id
                              ? 'opacity-100'
                              : 'opacity-0'
                          )}
                        />
                        <div className="flex flex-col">
                          <span className="font-mono text-sm">{session.session_id}</span>
                          <span className="text-xs text-muted-foreground">
                            {session.channel_id} • {session.user_id}
                          </span>
                        </div>
                      </CommandItem>
                    ))}
                  </CommandGroup>
                </Command>
              </PopoverContent>
            </Popover>
            {form.formState.errors.target_session_id && (
              <p className="text-sm text-destructive">{form.formState.errors.target_session_id.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="auth_token">Auth Token</Label>
            <div className="flex gap-2">
              <Input
                id="auth_token"
                {...form.register('auth_token')}
                type="password"
                placeholder="Auto-generated token"
                className="font-mono text-sm"
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={handleRegenerateToken}
                disabled={isEditing}
              >
                <RefreshCw className="h-4 w-4" />
              </Button>
              <Button type="button" variant="outline" size="icon" onClick={handleCopyToken}>
                <Copy className="h-4 w-4" />
              </Button>
            </div>
            {form.formState.errors.auth_token && (
              <p className="text-sm text-destructive">{form.formState.errors.auth_token.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="payload_schema">Payload Schema (Optional JSON Schema)</Label>
            <Textarea
              id="payload_schema"
              {...form.register('payload_schema')}
              placeholder='{"type": "object", "properties": {...}}'
              className="font-mono text-sm"
              rows={4}
            />
            {form.formState.errors.payload_schema && (
              <p className="text-sm text-destructive">{form.formState.errors.payload_schema.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="transform_rules">Transform Rules (Optional JSON)</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setTransformEditorOpen(!transformEditorOpen)}
              >
                {transformEditorOpen ? 'Close Editor' : 'Open Editor'}
              </Button>
            </div>
            {transformEditorOpen ? (
              <WebhookTransformEditor
                value={form.watch('transform_rules') || ''}
                onChange={(val) => form.setValue('transform_rules', val)}
              />
            ) : (
              <Textarea
                id="transform_rules"
                {...form.register('transform_rules')}
                placeholder='{"field_mapping": {...}}'
                className="font-mono text-sm"
                rows={4}
              />
            )}
            {form.formState.errors.transform_rules && (
              <p className="text-sm text-destructive">{form.formState.errors.transform_rules.message}</p>
            )}
          </div>

          <div className="flex items-center space-x-2">
            <Switch
              id="enabled"
              checked={form.watch('enabled')}
              onCheckedChange={(checked) => form.setValue('enabled', checked)}
            />
            <Label htmlFor="enabled">Enable this webhook</Label>
          </div>

          {testResult && (
            <Alert variant={testResult === 'success' ? 'default' : 'destructive'}>
              {testResult === 'success' ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <AlertCircle className="h-4 w-4" />
              )}
              <AlertDescription>
                {testResult === 'success'
                  ? 'Target session exists and is accessible!'
                  : 'Target session not found or not accessible.'}
              </AlertDescription>
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
              {isEditing ? 'Update' : 'Create'} Webhook
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
