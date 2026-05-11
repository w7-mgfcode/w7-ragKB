/**
 * Generate Approval Code Dialog Component
 * 
 * Dialog for generating new approval codes for DM pairing.
 * Features:
 * - Select channel
 * - Enter user ID and optional user name
 * - Generate approval code
 * - Display generated code with copy button
 */

import * as React from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import * as z from 'zod';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useChannels } from '@/hooks/useGateway';
import { generateApprovalCode } from '@/lib/api';
import { toast } from 'sonner';
import { Copy, CheckCircle } from 'lucide-react';

const formSchema = z.object({
  channel_id: z.string().min(1, 'Channel is required'),
  user_id: z.string().min(1, 'User ID is required'),
  user_name: z.string().optional(),
});

type FormData = z.infer<typeof formSchema>;

interface GenerateCodeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess: () => void;
}

export function GenerateCodeDialog({ open, onOpenChange, onSuccess }: GenerateCodeDialogProps) {
  const { channels, loading: channelsLoading } = useChannels();
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [generatedCode, setGeneratedCode] = React.useState<string | null>(null);

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      channel_id: '',
      user_id: '',
      user_name: '',
    },
  });

  const onSubmit = async (data: FormData) => {
    setIsSubmitting(true);
    try {
      const result = await generateApprovalCode({
        channel_id: data.channel_id,
        user_id: data.user_id,
        user_name: data.user_name || undefined,
      });
      
      setGeneratedCode(result.approval_code || null);
      toast.success('Approval code generated successfully!');
      onSuccess();
    } catch (error) {
      toast.error('Failed to generate approval code: ' + (error as Error).message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleClose = () => {
    form.reset();
    setGeneratedCode(null);
    onOpenChange(false);
  };

  const handleCopyCode = () => {
    if (generatedCode) {
      navigator.clipboard.writeText(generatedCode);
      toast.success('Code copied to clipboard');
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>Generate Approval Code</DialogTitle>
          <DialogDescription>
            Create a new approval code for a user to enable DM access.
          </DialogDescription>
        </DialogHeader>

        {generatedCode ? (
          <div className="space-y-4">
            <Alert>
              <CheckCircle className="h-4 w-4" />
              <AlertDescription>
                Approval code generated successfully! Share this code with the user.
              </AlertDescription>
            </Alert>

            <div className="space-y-2">
              <label className="text-sm font-medium">Approval Code</label>
              <div className="flex items-center gap-2">
                <code className="flex-1 px-4 py-3 bg-muted rounded text-lg font-mono text-center">
                  {generatedCode}
                </code>
                <Button variant="outline" size="icon" onClick={handleCopyCode}>
                  <Copy className="h-4 w-4" />
                </Button>
              </div>
              <p className="text-sm text-muted-foreground">
                This code will expire in 15 minutes.
              </p>
            </div>

            <DialogFooter>
              <Button onClick={handleClose}>Done</Button>
            </DialogFooter>
          </div>
        ) : (
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <FormField
                control={form.control}
                name="channel_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Channel</FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      defaultValue={field.value}
                      disabled={channelsLoading || isSubmitting}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="Select a channel" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {channels?.map((channel) => (
                          <SelectItem key={channel.channel_id} value={channel.channel_id}>
                            {channel.channel_id} ({channel.channel_type})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormDescription>
                      The messaging channel where the user will send DMs.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="user_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>User ID</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="user123"
                        {...field}
                        disabled={isSubmitting}
                      />
                    </FormControl>
                    <FormDescription>
                      The platform-specific user ID (e.g., Telegram user ID, Discord user ID).
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="user_name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>User Name (Optional)</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="John Doe"
                        {...field}
                        disabled={isSubmitting}
                      />
                    </FormControl>
                    <FormDescription>
                      Optional display name for easier identification.
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={handleClose}
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isSubmitting}>
                  {isSubmitting ? 'Generating...' : 'Generate Code'}
                </Button>
              </DialogFooter>
            </form>
          </Form>
        )}
      </DialogContent>
    </Dialog>
  );
}
