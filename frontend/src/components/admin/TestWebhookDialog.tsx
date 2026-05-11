/**
 * Test Webhook Dialog Component
 * 
 * Dialog for testing webhook endpoints with custom payloads.
 * Features:
 * - JSON payload editor
 * - Pre-filled auth token
 * - Send test request button
 * - Response status with color-coded badge
 * - Response body display
 * - Copy cURL command for external testing
 * - Request/Response tabs
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
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Loader2, Copy, Send } from 'lucide-react';
import type { Webhook, WebhookTestResponse } from '@/types/gateway';
import { testWebhook } from '@/lib/api';

const testWebhookSchema = z.object({
  payload: z.string().min(1, 'Payload is required').refine((val) => {
    try {
      JSON.parse(val);
      return true;
    } catch {
      return false;
    }
  }, 'Must be valid JSON'),
  auth_token: z.string().min(1, 'Auth token is required'),
});

type TestWebhookFormData = z.infer<typeof testWebhookSchema>;

interface TestWebhookDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  webhook: Webhook | null;
}

const DEFAULT_PAYLOAD = JSON.stringify(
  {
    message: 'Test webhook payload',
    timestamp: new Date().toISOString(),
    data: {
      example: 'value',
    },
  },
  null,
  2
);

export function TestWebhookDialog({
  open,
  onOpenChange,
  webhook,
}: TestWebhookDialogProps) {
  const [isTesting, setIsTesting] = React.useState(false);
  const [testResponse, setTestResponse] = React.useState<WebhookTestResponse | null>(null);

  const form = useForm<TestWebhookFormData>({
    resolver: zodResolver(testWebhookSchema),
    defaultValues: {
      payload: DEFAULT_PAYLOAD,
      auth_token: webhook?.auth_token || '',
    },
  });

  React.useEffect(() => {
    if (webhook) {
      form.reset({
        payload: DEFAULT_PAYLOAD,
        auth_token: webhook.auth_token,
      });
      setTestResponse(null);
    }
  }, [webhook, form, open]);

  const handleCopyCurl = () => {
    if (!webhook) return;

    const payload = form.getValues('payload');
    const authToken = form.getValues('auth_token');

    const curlCommand = `curl -X POST '${webhook.webhook_url}' \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer ${authToken}' \\
  -d '${payload.replace(/'/g, "'\\''")}'`;

    navigator.clipboard.writeText(curlCommand);
    toast.success('cURL command copied to clipboard!');
  };

  const onSubmit = async (data: TestWebhookFormData) => {
    if (!webhook) return;

    setIsTesting(true);
    setTestResponse(null);

    try {
      const response = await testWebhook(webhook.webhook_id, {
        payload: data.payload,
        auth_token: data.auth_token,
      });
      
      setTestResponse(response);
      
      if (response.status === 200) {
        toast.success('Webhook test successful!');
      } else {
        toast.error(`Webhook test failed with status ${response.status}`);
      }
    } catch (error) {
      toast.error('Failed to test webhook: ' + (error as Error).message);
      setTestResponse({
        status: 500,
        body: JSON.stringify({ error: (error as Error).message }),
        timestamp: new Date().toISOString(),
      });
    } finally {
      setIsTesting(false);
    }
  };

  const getStatusBadgeVariant = (status: number) => {
    if (status >= 200 && status < 300) return 'default';
    if (status >= 400 && status < 500) return 'destructive';
    if (status >= 500) return 'destructive';
    return 'secondary';
  };

  const getStatusColor = (status: number) => {
    if (status >= 200 && status < 300) return 'text-green-500';
    if (status >= 400 && status < 500) return 'text-yellow-500';
    if (status >= 500) return 'text-red-500';
    return 'text-gray-500';
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Test Webhook</DialogTitle>
          <DialogDescription>
            Send a test request to the webhook endpoint and view the response.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <Tabs defaultValue="request" className="w-full">
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="request">Request</TabsTrigger>
              <TabsTrigger value="response" disabled={!testResponse}>
                Response
              </TabsTrigger>
            </TabsList>

            <TabsContent value="request" className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="payload">Payload (JSON)</Label>
                <Textarea
                  id="payload"
                  {...form.register('payload')}
                  placeholder='{"message": "test"}'
                  className="font-mono text-sm"
                  rows={12}
                />
                {form.formState.errors.payload && (
                  <p className="text-sm text-destructive">
                    {form.formState.errors.payload.message}
                  </p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="auth_token">Auth Token</Label>
                <Textarea
                  id="auth_token"
                  {...form.register('auth_token')}
                  placeholder="Enter auth token"
                  className="font-mono text-sm"
                  rows={2}
                />
                {form.formState.errors.auth_token && (
                  <p className="text-sm text-destructive">
                    {form.formState.errors.auth_token.message}
                  </p>
                )}
              </div>

              {webhook && (
                <Alert>
                  <AlertDescription className="text-sm">
                    <strong>Webhook URL:</strong>
                    <br />
                    <code className="text-xs">{webhook.webhook_url}</code>
                  </AlertDescription>
                </Alert>
              )}
            </TabsContent>

            <TabsContent value="response" className="space-y-4">
              {testResponse && (
                <>
                  <div className="space-y-2">
                    <Label>Response Status</Label>
                    <div className="flex items-center gap-2">
                      <Badge variant={getStatusBadgeVariant(testResponse.status)}>
                        {testResponse.status}
                      </Badge>
                      <span className={`text-sm font-medium ${getStatusColor(testResponse.status)}`}>
                        {testResponse.status >= 200 && testResponse.status < 300
                          ? 'Success'
                          : testResponse.status === 401
                          ? 'Unauthorized'
                          : testResponse.status === 400
                          ? 'Bad Request'
                          : testResponse.status === 404
                          ? 'Not Found'
                          : 'Error'}
                      </span>
                    </div>
                  </div>

                  <div className="space-y-2">
                    <Label>Response Body</Label>
                    <Textarea
                      value={testResponse.body}
                      readOnly
                      className="font-mono text-sm"
                      rows={12}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>Timestamp</Label>
                    <p className="text-sm text-muted-foreground">
                      {new Date(testResponse.timestamp).toLocaleString()}
                    </p>
                  </div>
                </>
              )}
            </TabsContent>
          </Tabs>

          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={handleCopyCurl}
              disabled={!webhook}
            >
              <Copy className="mr-2 h-4 w-4" />
              Copy cURL Command
            </Button>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Close
            </Button>
            <Button type="submit" disabled={isTesting || !webhook}>
              {isTesting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <Send className="mr-2 h-4 w-4" />
              )}
              Send Test Request
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
