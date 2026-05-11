/**
 * Send Message Dialog Component
 * 
 * Allows sending inter-session messages with:
 * - Target session selection (combobox with search)
 * - Message content (textarea)
 * - Optional metadata (JSON)
 * - Message preview
 * - Validation and error handling
 */

import { useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import * as z from 'zod';
import { Check, ChevronsUpDown, Send } from 'lucide-react';

import { Button } from '@/components/ui/button';
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
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { cn } from '@/lib/utils';
import { sendMessageToSession } from '@/lib/api';
import { useSessions } from '@/hooks/useGateway';

const formSchema = z.object({
  target_session_id: z.string().min(1, 'Target session is required'),
  message: z.string().min(1, 'Message is required').max(4000, 'Message must be at most 4000 characters'),
  metadata: z.string().optional().refine(
    (val) => {
      if (!val || val.trim() === '') return true;
      try {
        JSON.parse(val);
        return true;
      } catch {
        return false;
      }
    },
    { message: 'Metadata must be valid JSON' }
  ),
});

interface SendMessageDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  defaultSessionId?: string;
  onSuccess?: () => void;
}

export function SendMessageDialog({
  open,
  onOpenChange,
  defaultSessionId,
  onSuccess,
}: SendMessageDialogProps) {
  const [comboboxOpen, setComboboxOpen] = useState(false);
  const [sending, setSending] = useState(false);
  const { sessions, loading: sessionsLoading } = useSessions();

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      target_session_id: defaultSessionId || '',
      message: '',
      metadata: '',
    },
  });

  const selectedSessionId = form.watch('target_session_id');
  const selectedSession = sessions.find((s) => s.session_id === selectedSessionId);

  const handleSubmit = async (data: z.infer<typeof formSchema>) => {
    setSending(true);
    try {
      const payload: { message: string; metadata?: string } = {
        message: data.message,
      };

      if (data.metadata && data.metadata.trim() !== '') {
        payload.metadata = data.metadata;
      }

      await sendMessageToSession(data.target_session_id, payload);

      toast.success('Message sent successfully!', {
        description: `Sent to session: ${data.target_session_id}`,
      });

      form.reset();
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      toast.error('Failed to send message', {
        description: error instanceof Error ? error.message : 'Unknown error',
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Send Inter-Session Message</DialogTitle>
          <DialogDescription>
            Send a message from one session to another. The target session will receive this message
            as if it came from the user.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form id="send-message-form" onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
            {/* Target Session Selector */}
            <FormField
              control={form.control}
              name="target_session_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Target Session</FormLabel>
                  <Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
                    <PopoverTrigger asChild>
                      <FormControl>
                        <Button
                          variant="outline"
                          role="combobox"
                          aria-expanded={comboboxOpen}
                          className="w-full justify-between"
                          disabled={sessionsLoading}
                        >
                          {field.value
                            ? sessions.find((s) => s.session_id === field.value)?.session_id ||
                              field.value
                            : 'Select session...'}
                          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                        </Button>
                      </FormControl>
                    </PopoverTrigger>
                    <PopoverContent className="w-[560px] p-0">
                      <Command>
                        <CommandInput placeholder="Search sessions..." className="h-9" />
                        <CommandList>
                          <CommandEmpty>No session found.</CommandEmpty>
                          <CommandGroup>
                            {sessions.map((session) => (
                              <CommandItem
                                key={session.session_id}
                                value={session.session_id}
                                onSelect={(currentValue) => {
                                  field.onChange(currentValue === field.value ? '' : currentValue);
                                  setComboboxOpen(false);
                                }}
                              >
                                <div className="flex flex-col">
                                  <span className="font-medium">{session.session_id}</span>
                                  <span className="text-xs text-muted-foreground">
                                    {session.channel_id} • {session.user_id} • {session.session_type}
                                  </span>
                                </div>
                                <Check
                                  className={cn(
                                    'ml-auto h-4 w-4',
                                    field.value === session.session_id
                                      ? 'opacity-100'
                                      : 'opacity-0'
                                  )}
                                />
                              </CommandItem>
                            ))}
                          </CommandGroup>
                        </CommandList>
                      </Command>
                    </PopoverContent>
                  </Popover>
                  <FormDescription>
                    Select the session that will receive this message
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Message Content */}
            <FormField
              control={form.control}
              name="message"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Message</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder="Enter your message here..."
                      rows={6}
                      className="resize-none"
                    />
                  </FormControl>
                  <div className="flex items-center justify-between">
                    <FormDescription>
                      The message content that will be sent to the target session
                    </FormDescription>
                    <span className="text-xs text-muted-foreground tabular-nums">
                      {field.value.length}/4000
                    </span>
                  </div>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Optional Metadata */}
            <FormField
              control={form.control}
              name="metadata"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Metadata (Optional)</FormLabel>
                  <FormControl>
                    <Textarea
                      {...field}
                      placeholder='{"key": "value"}'
                      rows={3}
                      className="resize-none font-mono text-sm"
                    />
                  </FormControl>
                  <FormDescription>
                    Optional JSON metadata to attach to the message
                  </FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* Message Preview */}
            {selectedSession && form.watch('message') && (
              <Alert>
                <AlertDescription>
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Preview:</p>
                    <div className="rounded-md bg-muted p-3 text-sm">
                      <p className="text-xs text-muted-foreground mb-1">
                        To: {selectedSession.session_id} ({selectedSession.channel_id})
                      </p>
                      <p className="whitespace-pre-wrap">{form.watch('message')}</p>
                    </div>
                  </div>
                </AlertDescription>
              </Alert>
            )}
          </form>
        </Form>

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              form.reset();
              onOpenChange(false);
            }}
            disabled={sending}
          >
            Cancel
          </Button>
          <Button type="submit" form="send-message-form" disabled={sending || sessionsLoading}>
            <Send className="mr-2 h-4 w-4" />
            {sending ? 'Sending...' : 'Send Message'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
