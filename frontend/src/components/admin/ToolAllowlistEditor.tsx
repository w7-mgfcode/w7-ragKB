/**
 * Tool Allowlist Editor Component
 * 
 * Dialog for managing per-session tool permissions with allowlist and denylist.
 * Features:
 * - Display current tool_allowlist as chips/badges with remove buttons
 * - Add input to add new tool patterns (supports wildcards like "read_*")
 * - Autocomplete for available tools using Combobox
 * - Show tool_denylist separately with red badges
 * - Wildcard pattern tester (input pattern, show matching tools)
 * - Save button to update session configuration
 * - Form validation with zod
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
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Loader2, X, Plus, Check, ChevronsUpDown, Info, TestTube } from 'lucide-react';
import { cn } from '@/lib/utils';
import { updateSessionConfig } from '@/lib/api';
import type { Session } from '@/types/gateway';

// Available tools in the system (from agent.py)
const AVAILABLE_TOOLS = [
  'web_search',
  'retrieve_relevant_documents',
  'list_documents',
  'get_document_content',
  'execute_sql_query',
  'image_analysis',
  'execute_code',
  'list_sessions',
  'get_session_history',
  'send_to_session',
  'navigate_browser',
  'click_element',
  'capture_screenshot',
  'fill_form_field',
  'execute_javascript',
];

// Common wildcard patterns
const WILDCARD_PATTERNS = [
  { pattern: '*', description: 'All tools' },
  { pattern: 'web_*', description: 'All web tools' },
  { pattern: 'read_*', description: 'All read tools' },
  { pattern: 'execute_*', description: 'All execute tools' },
  { pattern: '*_browser', description: 'All browser tools' },
  { pattern: '*_session*', description: 'All session tools' },
];

const toolAllowlistSchema = z.object({
  tool_allowlist: z.array(z.string()).min(1, 'At least one tool pattern is required'),
  tool_denylist: z.array(z.string()),
});

type ToolAllowlistFormData = z.infer<typeof toolAllowlistSchema>;

interface ToolAllowlistEditorProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  session: Session;
  onSuccess?: () => void;
}

/**
 * Match a tool name against a wildcard pattern using fnmatch-style matching
 */
function matchesPattern(toolName: string, pattern: string): boolean {
  if (pattern === '*') return true;
  
  // Convert wildcard pattern to regex
  const regexPattern = pattern
    .replace(/[.+^${}()|[\]\\]/g, '\\$&') // Escape regex special chars
    .replace(/\*/g, '.*') // Convert * to .*
    .replace(/\?/g, '.'); // Convert ? to .
  
  const regex = new RegExp(`^${regexPattern}$`);
  return regex.test(toolName);
}

/**
 * Get tools that match a given pattern
 */
function getMatchingTools(pattern: string): string[] {
  return AVAILABLE_TOOLS.filter(tool => matchesPattern(tool, pattern));
}

export function ToolAllowlistEditor({
  open,
  onOpenChange,
  session,
  onSuccess,
}: ToolAllowlistEditorProps) {
  const [isSaving, setIsSaving] = React.useState(false);
  const [comboboxOpen, setComboboxOpen] = React.useState(false);
  const [newPattern, setNewPattern] = React.useState('');
  const [testPattern, setTestPattern] = React.useState('');
  const [matchingTools, setMatchingTools] = React.useState<string[]>([]);

  const form = useForm<ToolAllowlistFormData>({
    resolver: zodResolver(toolAllowlistSchema),
    defaultValues: {
      tool_allowlist: session.tool_allowlist || ['*'],
      tool_denylist: session.tool_denylist || [],
    },
  });

  // Reset form when session changes or dialog opens
  React.useEffect(() => {
    if (open && session) {
      form.reset({
        tool_allowlist: session.tool_allowlist || ['*'],
        tool_denylist: session.tool_denylist || [],
      });
      setNewPattern('');
      setTestPattern('');
      setMatchingTools([]);
    }
  }, [session, open, form]);

  // Update matching tools when test pattern changes
  React.useEffect(() => {
    if (testPattern.trim()) {
      setMatchingTools(getMatchingTools(testPattern.trim()));
    } else {
      setMatchingTools([]);
    }
  }, [testPattern]);

  const handleAddToAllowlist = (pattern: string) => {
    const trimmedPattern = pattern.trim();
    if (!trimmedPattern) return;

    const currentAllowlist = form.getValues('tool_allowlist');
    if (!currentAllowlist.includes(trimmedPattern)) {
      form.setValue('tool_allowlist', [...currentAllowlist, trimmedPattern]);
      setNewPattern('');
      toast.success(`Added "${trimmedPattern}" to allowlist`);
    } else {
      toast.info('Pattern already in allowlist');
    }
  };

  const handleRemoveFromAllowlist = (pattern: string) => {
    const currentAllowlist = form.getValues('tool_allowlist');
    const newAllowlist = currentAllowlist.filter(p => p !== pattern);
    
    if (newAllowlist.length === 0) {
      toast.error('Cannot remove last pattern. At least one pattern is required.');
      return;
    }
    
    form.setValue('tool_allowlist', newAllowlist);
    toast.success(`Removed "${pattern}" from allowlist`);
  };

  const handleAddToDenylist = (pattern: string) => {
    const trimmedPattern = pattern.trim();
    if (!trimmedPattern) return;

    const currentDenylist = form.getValues('tool_denylist');
    if (!currentDenylist.includes(trimmedPattern)) {
      form.setValue('tool_denylist', [...currentDenylist, trimmedPattern]);
      toast.success(`Added "${trimmedPattern}" to denylist`);
    } else {
      toast.info('Pattern already in denylist');
    }
  };

  const handleRemoveFromDenylist = (pattern: string) => {
    const currentDenylist = form.getValues('tool_denylist');
    form.setValue('tool_denylist', currentDenylist.filter(p => p !== pattern));
    toast.success(`Removed "${pattern}" from denylist`);
  };

  const handleSelectFromCombobox = (value: string) => {
    handleAddToAllowlist(value);
    setComboboxOpen(false);
  };

  const onSubmit = async (data: ToolAllowlistFormData) => {
    setIsSaving(true);
    try {
      await updateSessionConfig(session.session_id, {
        activation_mode: session.activation_mode,
        tool_allowlist: data.tool_allowlist,
        tool_denylist: data.tool_denylist,
      });
      
      toast.success('Tool permissions updated successfully!');
      onSuccess?.();
      onOpenChange(false);
    } catch (error) {
      toast.error('Failed to update tool permissions: ' + (error as Error).message);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[700px] max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Edit Tool Permissions</DialogTitle>
          <DialogDescription>
            Configure which tools the agent can use in this session. Denylist takes precedence over allowlist.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          {/* Session Info */}
          <div className="rounded-md bg-muted p-3 space-y-1">
            <div className="text-sm font-medium">Session: {session.session_id}</div>
            <div className="text-xs text-muted-foreground">
              Channel: {session.channel_id} • User: {session.user_id}
            </div>
          </div>

          {/* Wildcard Pattern Help */}
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription className="text-sm">
              <strong>Wildcard Patterns:</strong> Use <code className="px-1 py-0.5 bg-muted rounded">*</code> to match all tools, 
              <code className="px-1 py-0.5 bg-muted rounded mx-1">web_*</code> for all web tools, 
              <code className="px-1 py-0.5 bg-muted rounded mx-1">*_browser</code> for all browser tools, etc.
            </AlertDescription>
          </Alert>

          {/* Tool Allowlist Section */}
          <div className="space-y-3">
            <div>
              <Label className="text-base font-semibold">Tool Allowlist</Label>
              <p className="text-sm text-muted-foreground mt-1">
                Tools and patterns that are allowed in this session
              </p>
            </div>

            {/* Current Allowlist */}
            <div className="flex flex-wrap gap-2 min-h-[40px] p-3 rounded-md border">
              {form.watch('tool_allowlist').map((pattern) => (
                <Badge
                  key={pattern}
                  variant="default"
                  className="gap-1 bg-green-600 hover:bg-green-700"
                >
                  {pattern}
                  <button
                    type="button"
                    onClick={() => handleRemoveFromAllowlist(pattern)}
                    className="ml-1 hover:bg-green-800 rounded-full p-0.5"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>

            {/* Add to Allowlist */}
            <div className="flex gap-2">
              <div className="flex-1">
                <Input
                  placeholder="Enter tool name or pattern (e.g., web_*, execute_code)"
                  value={newPattern}
                  onChange={(e) => setNewPattern(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      handleAddToAllowlist(newPattern);
                    }
                  }}
                />
              </div>
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={() => handleAddToAllowlist(newPattern)}
                disabled={!newPattern.trim()}
              >
                <Plus className="h-4 w-4" />
              </Button>
              <Popover open={comboboxOpen} onOpenChange={setComboboxOpen}>
                <PopoverTrigger asChild>
                  <Button
                    type="button"
                    variant="outline"
                    role="combobox"
                    aria-expanded={comboboxOpen}
                    className="w-[200px] justify-between"
                  >
                    Select tool...
                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-[300px] p-0">
                  <Command>
                    <CommandInput placeholder="Search tools..." />
                    <CommandList>
                      <CommandEmpty>No tool found.</CommandEmpty>
                      <CommandGroup heading="Common Patterns">
                        {WILDCARD_PATTERNS.map((item) => (
                          <CommandItem
                            key={item.pattern}
                            value={item.pattern}
                            onSelect={handleSelectFromCombobox}
                          >
                            <Check
                              className={cn(
                                'mr-2 h-4 w-4',
                                form.watch('tool_allowlist').includes(item.pattern)
                                  ? 'opacity-100'
                                  : 'opacity-0'
                              )}
                            />
                            <div className="flex flex-col">
                              <span className="font-mono text-sm">{item.pattern}</span>
                              <span className="text-xs text-muted-foreground">
                                {item.description}
                              </span>
                            </div>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                      <CommandGroup heading="Available Tools">
                        {AVAILABLE_TOOLS.map((tool) => (
                          <CommandItem
                            key={tool}
                            value={tool}
                            onSelect={handleSelectFromCombobox}
                          >
                            <Check
                              className={cn(
                                'mr-2 h-4 w-4',
                                form.watch('tool_allowlist').includes(tool)
                                  ? 'opacity-100'
                                  : 'opacity-0'
                              )}
                            />
                            <span className="font-mono text-sm">{tool}</span>
                          </CommandItem>
                        ))}
                      </CommandGroup>
                    </CommandList>
                  </Command>
                </PopoverContent>
              </Popover>
            </div>

            {form.formState.errors.tool_allowlist && (
              <p className="text-sm text-destructive">
                {form.formState.errors.tool_allowlist.message}
              </p>
            )}
          </div>

          <Separator />

          {/* Tool Denylist Section */}
          <div className="space-y-3">
            <div>
              <Label className="text-base font-semibold">Tool Denylist</Label>
              <p className="text-sm text-muted-foreground mt-1">
                Tools and patterns that are explicitly blocked (takes precedence over allowlist)
              </p>
            </div>

            {/* Current Denylist */}
            <div className="flex flex-wrap gap-2 min-h-[40px] p-3 rounded-md border">
              {form.watch('tool_denylist').length === 0 ? (
                <span className="text-sm text-muted-foreground">No denied tools</span>
              ) : (
                form.watch('tool_denylist').map((pattern) => (
                  <Badge
                    key={pattern}
                    variant="destructive"
                    className="gap-1"
                  >
                    {pattern}
                    <button
                      type="button"
                      onClick={() => handleRemoveFromDenylist(pattern)}
                      className="ml-1 hover:bg-red-800 rounded-full p-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))
              )}
            </div>

            {/* Add to Denylist */}
            <div className="flex gap-2">
              <Input
                placeholder="Enter tool name or pattern to deny"
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault();
                    handleAddToDenylist(e.currentTarget.value);
                    e.currentTarget.value = '';
                  }
                }}
              />
              <Button
                type="button"
                variant="outline"
                size="icon"
                onClick={(e) => {
                  const input = e.currentTarget.previousElementSibling as HTMLInputElement;
                  handleAddToDenylist(input.value);
                  input.value = '';
                }}
              >
                <Plus className="h-4 w-4" />
              </Button>
            </div>
          </div>

          <Separator />

          {/* Pattern Tester */}
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <TestTube className="h-4 w-4" />
              <Label className="text-base font-semibold">Pattern Tester</Label>
            </div>
            <p className="text-sm text-muted-foreground">
              Test a wildcard pattern to see which tools it matches
            </p>

            <Input
              placeholder="Enter pattern to test (e.g., web_*, execute_*)"
              value={testPattern}
              onChange={(e) => setTestPattern(e.target.value)}
            />

            {testPattern.trim() && (
              <div className="rounded-md border p-3 space-y-2">
                <div className="text-sm font-medium">
                  Matches {matchingTools.length} tool{matchingTools.length !== 1 ? 's' : ''}:
                </div>
                {matchingTools.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {matchingTools.map((tool) => (
                      <Badge key={tool} variant="outline" className="font-mono text-xs">
                        {tool}
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-muted-foreground">No tools match this pattern</p>
                )}
              </div>
            )}
          </div>

          <DialogFooter className="gap-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Changes
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
