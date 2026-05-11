/**
 * Webhook Transform Editor Component
 *
 * 3-panel transform rules editor using resizable panels:
 * 1. Input JSON panel (editable sample payload)
 * 2. Transform Rules panel (visual rule list OR raw JSON, toggled by tabs)
 * 3. Output Preview panel (read-only, result of applying rules)
 *
 * Features:
 * - Visual rule editor with add/remove rules
 * - Path validation with inline green check / red X
 * - Raw JSON editor with bidirectional sync
 * - Client-side test: apply rules to input and show output
 */

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from '@/components/ui/resizable';
import { Plus, Minus, Check, X, Play } from 'lucide-react';
import { cn } from '@/lib/utils';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TransformRule {
  id: string;
  source: string;
  target: string;
  type: 'direct' | 'template';
}

interface WebhookTransformEditorProps {
  value: string; // JSON string of current transform_rules
  onChange: (value: string) => void;
  samplePayload?: string; // JSON string of sample input
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function generateRuleId(): string {
  return `rule-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
}

/**
 * Parse a dot-separated path and extract a value from a nested object.
 */
function getByPath(obj: Record<string, any>, path: string): any {
  const parts = path.split('.');
  let current: any = obj;
  for (const part of parts) {
    if (current == null || typeof current !== 'object') return undefined;
    current = current[part];
  }
  return current;
}

/**
 * Set a value at a dot-separated path in a nested object (creates intermediates).
 */
function setByPath(obj: Record<string, any>, path: string, value: any): void {
  const parts = path.split('.');
  let current: any = obj;
  for (let i = 0; i < parts.length - 1; i++) {
    if (current[parts[i]] == null || typeof current[parts[i]] !== 'object') {
      current[parts[i]] = {};
    }
    current = current[parts[i]];
  }
  current[parts[parts.length - 1]] = value;
}

/**
 * Validate whether a JSON path could be valid (simple dot-notation check).
 */
function isValidPath(path: string): boolean {
  if (!path || path.trim() === '') return false;
  return /^[a-zA-Z_$][a-zA-Z0-9_$]*(\.[a-zA-Z_$][a-zA-Z0-9_$]*)*$/.test(path.trim());
}

/**
 * Parse rules array from a JSON string. Returns empty array on failure.
 */
function parseRules(json: string): TransformRule[] {
  try {
    const parsed = JSON.parse(json);
    if (Array.isArray(parsed)) {
      return parsed.map((r: any) => ({
        id: r.id || generateRuleId(),
        source: r.source || '',
        target: r.target || '',
        type: r.type === 'template' ? 'template' : 'direct',
      }));
    }
    // If it's an object with a "rules" key
    if (parsed && Array.isArray(parsed.rules)) {
      return parsed.rules.map((r: any) => ({
        id: r.id || generateRuleId(),
        source: r.source || '',
        target: r.target || '',
        type: r.type === 'template' ? 'template' : 'direct',
      }));
    }
  } catch {
    // ignore parse errors
  }
  return [];
}

function rulesToJson(rules: TransformRule[]): string {
  const clean = rules.map(({ source, target, type }) => ({ source, target, type }));
  return JSON.stringify(clean, null, 2);
}

/**
 * Apply transform rules to an input object and return the output.
 */
function applyRules(
  input: Record<string, any>,
  rules: TransformRule[]
): Record<string, any> {
  const output: Record<string, any> = {};
  for (const rule of rules) {
    if (!rule.source || !rule.target) continue;
    const value = getByPath(input, rule.source);
    if (value !== undefined) {
      setByPath(output, rule.target, value);
    }
  }
  return output;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

const DEFAULT_SAMPLE = JSON.stringify(
  {
    event: 'message.created',
    data: {
      id: '12345',
      text: 'Hello world',
      user: { name: 'Alice', email: 'alice@example.com' },
    },
    timestamp: '2026-02-24T12:00:00Z',
  },
  null,
  2
);

export function WebhookTransformEditor({
  value,
  onChange,
  samplePayload,
}: WebhookTransformEditorProps) {
  const [rules, setRules] = React.useState<TransformRule[]>(() => parseRules(value));
  const [inputJson, setInputJson] = React.useState<string>(samplePayload || DEFAULT_SAMPLE);
  const [outputJson, setOutputJson] = React.useState<string>('{}');
  const [rawJson, setRawJson] = React.useState<string>(() => rulesToJson(parseRules(value)));
  const [activeTab, setActiveTab] = React.useState<string>('visual');

  // Sync rules -> parent onChange
  const syncToParent = React.useCallback(
    (updatedRules: TransformRule[]) => {
      const json = rulesToJson(updatedRules);
      onChange(json);
    },
    [onChange]
  );

  // When rules change from visual editor, sync to raw JSON
  React.useEffect(() => {
    if (activeTab === 'visual') {
      setRawJson(rulesToJson(rules));
    }
  }, [rules, activeTab]);

  // When switching to visual from JSON tab, parse raw JSON into rules
  const handleTabChange = (tab: string) => {
    if (tab === 'visual' && activeTab === 'json') {
      const parsed = parseRules(rawJson);
      setRules(parsed);
      syncToParent(parsed);
    }
    if (tab === 'json' && activeTab === 'visual') {
      setRawJson(rulesToJson(rules));
    }
    setActiveTab(tab);
  };

  // ---------------------------------------------------------------------------
  // Rule CRUD
  // ---------------------------------------------------------------------------

  const addRule = () => {
    const newRule: TransformRule = {
      id: generateRuleId(),
      source: '',
      target: '',
      type: 'direct',
    };
    const updated = [...rules, newRule];
    setRules(updated);
    syncToParent(updated);
  };

  const removeRule = (id: string) => {
    const updated = rules.filter((r) => r.id !== id);
    setRules(updated);
    syncToParent(updated);
  };

  const updateRule = (id: string, field: keyof TransformRule, val: string) => {
    const updated = rules.map((r) => (r.id === id ? { ...r, [field]: val } : r));
    setRules(updated);
    syncToParent(updated);
  };

  // ---------------------------------------------------------------------------
  // Test / apply
  // ---------------------------------------------------------------------------

  const handleTest = () => {
    try {
      const input = JSON.parse(inputJson);
      const currentRules = activeTab === 'json' ? parseRules(rawJson) : rules;
      const output = applyRules(input, currentRules);
      setOutputJson(JSON.stringify(output, null, 2));
    } catch (e) {
      setOutputJson(JSON.stringify({ error: 'Invalid input JSON' }, null, 2));
    }
  };

  // Handle raw JSON changes
  const handleRawJsonChange = (val: string) => {
    setRawJson(val);
    try {
      const parsed = parseRules(val);
      onChange(rulesToJson(parsed));
    } catch {
      // Don't sync invalid JSON
    }
  };

  // ---------------------------------------------------------------------------
  // Path validation indicator
  // ---------------------------------------------------------------------------

  const PathIndicator = ({ path }: { path: string }) => {
    if (!path) return null;
    const valid = isValidPath(path);
    return valid ? (
      <Check className="h-3.5 w-3.5 text-green-500 shrink-0" />
    ) : (
      <X className="h-3.5 w-3.5 text-red-500 shrink-0" />
    );
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="border rounded-lg overflow-hidden" style={{ height: 500 }}>
      <ResizablePanelGroup direction="horizontal">
        {/* Panel 1: Input JSON */}
        <ResizablePanel defaultSize={30} minSize={20}>
          <div className="flex flex-col h-full">
            <div className="px-3 py-2 border-b bg-muted/50">
              <Label className="text-xs font-medium uppercase tracking-wider">Input JSON</Label>
            </div>
            <Textarea
              className="flex-1 border-0 rounded-none resize-none font-mono text-xs focus-visible:ring-0"
              value={inputJson}
              onChange={(e) => setInputJson(e.target.value)}
              placeholder="Paste sample input JSON..."
            />
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Panel 2: Transform Rules */}
        <ResizablePanel defaultSize={40} minSize={25}>
          <div className="flex flex-col h-full">
            <div className="px-3 py-2 border-b bg-muted/50 flex items-center justify-between">
              <Label className="text-xs font-medium uppercase tracking-wider">
                Transform Rules
              </Label>
              <Button type="button" size="sm" variant="outline" onClick={handleTest}>
                <Play className="h-3.5 w-3.5 mr-1" />
                Test
              </Button>
            </div>

            <Tabs value={activeTab} onValueChange={handleTabChange} className="flex-1 flex flex-col">
              <TabsList className="w-full rounded-none grid grid-cols-2">
                <TabsTrigger value="visual">Visual Editor</TabsTrigger>
                <TabsTrigger value="json">JSON Editor</TabsTrigger>
              </TabsList>

              <TabsContent value="visual" className="flex-1 m-0 overflow-hidden">
                <ScrollArea className="h-full">
                  <div className="p-3 space-y-3">
                    {rules.length === 0 && (
                      <p className="text-sm text-muted-foreground text-center py-4">
                        No rules defined. Click "Add Rule" to get started.
                      </p>
                    )}

                    {rules.map((rule, idx) => (
                      <div
                        key={rule.id}
                        className="border rounded-md p-3 space-y-2 bg-background"
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-medium text-muted-foreground">
                            Rule {idx + 1}
                          </span>
                          <Button
                            type="button"
                            size="icon"
                            variant="ghost"
                            className="h-6 w-6"
                            onClick={() => removeRule(rule.id)}
                          >
                            <Minus className="h-3.5 w-3.5" />
                          </Button>
                        </div>

                        <div className="space-y-1.5">
                          <Label className="text-xs">Source Path</Label>
                          <div className="flex items-center gap-1.5">
                            <Input
                              className="font-mono text-xs h-8"
                              placeholder="data.user.name"
                              value={rule.source}
                              onChange={(e) => updateRule(rule.id, 'source', e.target.value)}
                            />
                            <PathIndicator path={rule.source} />
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <Label className="text-xs">Target Path</Label>
                          <div className="flex items-center gap-1.5">
                            <Input
                              className="font-mono text-xs h-8"
                              placeholder="user_name"
                              value={rule.target}
                              onChange={(e) => updateRule(rule.id, 'target', e.target.value)}
                            />
                            <PathIndicator path={rule.target} />
                          </div>
                        </div>

                        <div className="space-y-1.5">
                          <Label className="text-xs">Type</Label>
                          <Select
                            value={rule.type}
                            onValueChange={(val) =>
                              updateRule(rule.id, 'type', val as 'direct' | 'template')
                            }
                          >
                            <SelectTrigger className="h-8 text-xs">
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="direct">Direct</SelectItem>
                              <SelectItem value="template">Template</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                      </div>
                    ))}

                    <Button
                      type="button"
                      variant="outline"
                      className="w-full"
                      onClick={addRule}
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Add Rule
                    </Button>
                  </div>
                </ScrollArea>
              </TabsContent>

              <TabsContent value="json" className="flex-1 m-0">
                <Textarea
                  className="h-full border-0 rounded-none resize-none font-mono text-xs focus-visible:ring-0"
                  value={rawJson}
                  onChange={(e) => handleRawJsonChange(e.target.value)}
                  placeholder="Enter transform rules as JSON array..."
                />
              </TabsContent>
            </Tabs>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Panel 3: Output Preview */}
        <ResizablePanel defaultSize={30} minSize={20}>
          <div className="flex flex-col h-full">
            <div className="px-3 py-2 border-b bg-muted/50">
              <Label className="text-xs font-medium uppercase tracking-wider">
                Output Preview
              </Label>
            </div>
            <Textarea
              className="flex-1 border-0 rounded-none resize-none font-mono text-xs focus-visible:ring-0"
              value={outputJson}
              readOnly
              placeholder='Click "Test" to see the output...'
            />
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
