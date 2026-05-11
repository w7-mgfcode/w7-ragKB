/**
 * Cron Job Dialog Component
 * 
 * Dialog for creating or editing cron jobs.
 * Features:
 * - Form validation with zod
 * - Auto-generated cron job ID
 * - Session search with combobox
 * - Cron expression validator with visual feedback
 * - Next 5 execution times preview
 * - Cron expression helper with common presets
 * - Visual cron builder with select components
 * - Timezone selection
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, CheckCircle2, AlertCircle } from 'lucide-react';
import type { CronJob } from '@/types/gateway';
import { createCronJob, updateCronJob, previewCronSchedule } from '@/lib/api';
import { useSessions } from '@/hooks/useGateway';
import { CronExpressionBuilder } from './CronExpressionBuilder';
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

const cronJobSchema = z.object({
  cron_job_id: z.string().min(1, 'Cron job ID is required').max(100, 'Cron job ID must be at most 100 characters'),
  schedule: z.string().min(1, 'Schedule is required'),
  target_session_id: z.string().min(1, 'Target session is required'),
  message_template: z.string().min(1, 'Message template is required'),
  timezone: z.string().min(1, 'Timezone is required'),
  enabled: z.boolean(),
});

type CronJobFormData = z.infer<typeof cronJobSchema>;

interface CronJobDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  cronJob?: CronJob | null;
  onSuccess?: () => void;
}

function generateId(): string {
  return `cron-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
}

// Common cron presets
const CRON_PRESETS = [
  { label: 'Every minute', value: '* * * * *' },
  { label: 'Every 5 minutes', value: '*/5 * * * *' },
  { label: 'Every 15 minutes', value: '*/15 * * * *' },
  { label: 'Every 30 minutes', value: '*/30 * * * *' },
  { label: 'Every hour', value: '0 * * * *' },
  { label: 'Every day at midnight', value: '0 0 * * *' },
  { label: 'Every day at 9 AM', value: '0 9 * * *' },
  { label: 'Every Monday at 9 AM', value: '0 9 * * 1' },
  { label: 'First day of month at midnight', value: '0 0 1 * *' },
];

// Common timezones
const TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Europe/Berlin',
  'Asia/Tokyo',
  'Asia/Shanghai',
  'Asia/Singapore',
  'Australia/Sydney',
];

export function CronJobDialog({
  open,
  onOpenChange,
  cronJob,
  onSuccess,
}: CronJobDialogProps) {
  const [isSaving, setIsSaving] = React.useState(false);
  const [sessionSearchOpen, setSessionSearchOpen] = React.useState(false);
  const [schedulePreview, setSchedulePreview] = React.useState<string[]>([]);
  const [scheduleValid, setScheduleValid] = React.useState<boolean | null>(null);
  const [scheduleError, setScheduleError] = React.useState<string | null>(null);
  const { sessions } = useSessions();

  const isEditing = !!cronJob;

  const form = useForm<CronJobFormData>({
    resolver: zodResolver(cronJobSchema),
    defaultValues: {
      cron_job_id: cronJob?.cron_job_id || generateId(),
      schedule: cronJob?.schedule || '0 9 * * *',
      target_session_id: cronJob?.target_session_id || '',
      message_template: cronJob?.message_template || '',
      timezone: cronJob?.timezone || 'UTC',
      enabled: cronJob?.enabled ?? true,
    },
  });

  React.useEffect(() => {
    if (cronJob) {
      form.reset({
        cron_job_id: cronJob.cron_job_id,
        schedule: cronJob.schedule,
        target_session_id: cronJob.target_session_id,
        message_template: cronJob.message_template,
        timezone: cronJob.timezone,
        enabled: cronJob.enabled,
      });
    } else {
      form.reset({
        cron_job_id: generateId(),
        schedule: '0 9 * * *',
        target_session_id: '',
        message_template: '',
        timezone: 'UTC',
        enabled: true,
      });
    }
    setSchedulePreview([]);
    setScheduleValid(null);
    setScheduleError(null);
  }, [cronJob, form, open]);

  // Preview schedule whenever schedule or timezone changes
  React.useEffect(() => {
    const schedule = form.watch('schedule');
    const timezone = form.watch('timezone');

    if (!schedule || !timezone) return;

    const debounce = setTimeout(async () => {
      try {
        const preview = await previewCronSchedule(schedule, timezone);
        if (preview.is_valid) {
          setSchedulePreview(preview.next_executions);
          setScheduleValid(true);
          setScheduleError(null);
        } else {
          setSchedulePreview([]);
          setScheduleValid(false);
          setScheduleError(preview.error_message || 'Invalid cron expression');
        }
      } catch (error) {
        setSchedulePreview([]);
        setScheduleValid(false);
        setScheduleError('Failed to preview schedule');
      }
    }, 500);

    return () => clearTimeout(debounce);
  }, [form.watch('schedule'), form.watch('timezone')]);

  const handlePresetSelect = (preset: string) => {
    form.setValue('schedule', preset);
  };

  const onSubmit = async (data: CronJobFormData) => {
    setIsSaving(true);
    try {
      const payload = {
        cron_job_id: data.cron_job_id,
        schedule: data.schedule,
        target_session_id: data.target_session_id,
        message_template: data.message_template,
        timezone: data.timezone,
        enabled: data.enabled,
      };

      if (isEditing) {
        await updateCronJob(cronJob.cron_job_id, payload);
        toast.success('Cron job updated successfully!');
      } else {
        await createCronJob(payload);
        toast.success('Cron job created successfully!');
      }
      
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      toast.error('Failed to save cron job: ' + (error as Error).message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[800px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEditing ? 'Edit Cron Job' : 'Create New Cron Job'}</DialogTitle>
          <DialogDescription>
            {isEditing
              ? 'Update the cron job configuration below.'
              : 'Configure a new scheduled task to trigger agent actions.'}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="cron_job_id">Cron Job ID</Label>
            <Input
              id="cron_job_id"
              {...form.register('cron_job_id')}
              placeholder="cron-123"
              disabled={isEditing}
            />
            {form.formState.errors.cron_job_id && (
              <p className="text-sm text-destructive">{form.formState.errors.cron_job_id.message}</p>
            )}
          </div>

          <Tabs defaultValue="presets" className="w-full">
            <TabsList className="grid w-full grid-cols-3">
              <TabsTrigger value="presets">Common Presets</TabsTrigger>
              <TabsTrigger value="custom">Custom Expression</TabsTrigger>
              <TabsTrigger value="builder">Visual Builder</TabsTrigger>
            </TabsList>
            
            <TabsContent value="presets" className="space-y-2">
              <Label>Select a preset schedule</Label>
              <div className="grid grid-cols-2 gap-2">
                {CRON_PRESETS.map((preset) => (
                  <Button
                    key={preset.value}
                    type="button"
                    variant="outline"
                    className="justify-start"
                    onClick={() => handlePresetSelect(preset.value)}
                  >
                    <div className="flex flex-col items-start">
                      <span className="text-sm font-medium">{preset.label}</span>
                      <span className="text-xs text-muted-foreground font-mono">{preset.value}</span>
                    </div>
                  </Button>
                ))}
              </div>
            </TabsContent>
            
            <TabsContent value="custom" className="space-y-2">
              <Label htmlFor="schedule">Cron Expression</Label>
              <Input
                id="schedule"
                {...form.register('schedule')}
                placeholder="0 9 * * *"
                className="font-mono"
              />
              <p className="text-xs text-muted-foreground">
                Format: minute hour day month weekday (e.g., "0 9 * * *" = every day at 9 AM)
              </p>
            </TabsContent>

            <TabsContent value="builder" className="space-y-2">
              <CronExpressionBuilder
                value={form.watch('schedule')}
                onChange={(expr) => form.setValue('schedule', expr)}
              />
            </TabsContent>
          </Tabs>

          {form.formState.errors.schedule && (
            <p className="text-sm text-destructive">{form.formState.errors.schedule.message}</p>
          )}

          {scheduleValid !== null && (
            <Alert variant={scheduleValid ? 'default' : 'destructive'}>
              {scheduleValid ? (
                <CheckCircle2 className="h-4 w-4" />
              ) : (
                <AlertCircle className="h-4 w-4" />
              )}
              <AlertDescription>
                {scheduleValid
                  ? 'Valid cron expression'
                  : scheduleError || 'Invalid cron expression'}
              </AlertDescription>
            </Alert>
          )}

          {schedulePreview.length > 0 && (
            <div className="space-y-2">
              <Label>Next 5 Executions</Label>
              <div className="rounded-md border p-3 space-y-1">
                {schedulePreview.map((time, index) => (
                  <div key={index} className="text-sm font-mono">
                    {new Date(time).toLocaleString()}
                  </div>
                ))}
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
              <PopoverContent className="w-[700px] p-0">
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
            <Label htmlFor="message_template">Message Template</Label>
            <Textarea
              id="message_template"
              {...form.register('message_template')}
              placeholder="Daily summary report"
              rows={4}
            />
            {form.formState.errors.message_template && (
              <p className="text-sm text-destructive">{form.formState.errors.message_template.message}</p>
            )}
          </div>

          <div className="space-y-2">
            <Label htmlFor="timezone">Timezone</Label>
            <Select
              value={form.watch('timezone')}
              onValueChange={(value) => form.setValue('timezone', value)}
            >
              <SelectTrigger>
                <SelectValue placeholder="Select timezone" />
              </SelectTrigger>
              <SelectContent>
                {TIMEZONES.map((tz) => (
                  <SelectItem key={tz} value={tz}>
                    {tz}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {form.formState.errors.timezone && (
              <p className="text-sm text-destructive">{form.formState.errors.timezone.message}</p>
            )}
          </div>

          <div className="flex items-center space-x-2">
            <Switch
              id="enabled"
              checked={form.watch('enabled')}
              onCheckedChange={(checked) => form.setValue('enabled', checked)}
            />
            <Label htmlFor="enabled">Enable this cron job</Label>
          </div>

          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving || scheduleValid === false}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEditing ? 'Update' : 'Create'} Cron Job
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
