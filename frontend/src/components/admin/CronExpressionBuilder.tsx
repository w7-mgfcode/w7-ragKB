/**
 * Cron Expression Builder Component
 *
 * Visual cron expression builder with:
 * - Natural language input that parses into cron fields
 * - 5 rows for each cron field (minute, hour, day-of-month, month, day-of-week)
 * - Mode selectors per field: Every / Specific / Range / Interval
 * - Generated expression in monospace display
 * - Human-readable description
 * - Preset buttons (Daily, Weekly, Monthly, Hourly)
 * - Next 5 executions preview via debounced API call
 */

import * as React from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Loader2, Wand2 } from 'lucide-react';
import { previewCronSchedule } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface CronExpressionBuilderProps {
  value: string; // current cron expression
  onChange: (value: string) => void;
  timezone?: string;
}

type FieldMode = 'every' | 'specific' | 'range' | 'interval';

interface CronField {
  mode: FieldMode;
  specific: string; // comma-separated values
  rangeFrom: string;
  rangeTo: string;
  interval: string; // e.g. "5" for */5
}

const FIELD_LABELS = ['Minute', 'Hour', 'Day of Month', 'Month', 'Day of Week'] as const;

const FIELD_RANGES: Array<{ min: number; max: number; labels?: Record<number, string> }> = [
  { min: 0, max: 59 }, // minute
  { min: 0, max: 23 }, // hour
  { min: 1, max: 31 }, // day-of-month
  { min: 1, max: 12, labels: { 1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dec' } }, // month
  { min: 0, max: 6, labels: { 0: 'Sun', 1: 'Mon', 2: 'Tue', 3: 'Wed', 4: 'Thu', 5: 'Fri', 6: 'Sat' } }, // day-of-week
];

const WEEKDAY_MAP: Record<string, string> = {
  sunday: '0', sun: '0',
  monday: '1', mon: '1',
  tuesday: '2', tue: '2',
  wednesday: '3', wed: '3',
  thursday: '4', thu: '4',
  friday: '5', fri: '5',
  saturday: '6', sat: '6',
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function defaultField(): CronField {
  return { mode: 'every', specific: '', rangeFrom: '', rangeTo: '', interval: '' };
}

/**
 * Parse a single cron field token into a CronField.
 */
function parseFieldToken(token: string): CronField {
  const field = defaultField();
  if (token === '*') {
    field.mode = 'every';
  } else if (token.startsWith('*/')) {
    field.mode = 'interval';
    field.interval = token.substring(2);
  } else if (token.includes('-')) {
    field.mode = 'range';
    const [from, to] = token.split('-');
    field.rangeFrom = from;
    field.rangeTo = to;
  } else {
    field.mode = 'specific';
    field.specific = token;
  }
  return field;
}

/**
 * Convert a CronField back to its cron token string.
 */
function fieldToToken(field: CronField): string {
  switch (field.mode) {
    case 'every':
      return '*';
    case 'specific':
      return field.specific || '*';
    case 'range':
      if (field.rangeFrom && field.rangeTo) return `${field.rangeFrom}-${field.rangeTo}`;
      return '*';
    case 'interval':
      if (field.interval) return `*/${field.interval}`;
      return '*';
    default:
      return '*';
  }
}

/**
 * Parse a full 5-field cron expression into CronField[].
 */
function parseCronExpression(expr: string): CronField[] {
  const parts = expr.trim().split(/\s+/);
  const fields: CronField[] = [];
  for (let i = 0; i < 5; i++) {
    fields.push(parts[i] ? parseFieldToken(parts[i]) : defaultField());
  }
  return fields;
}

/**
 * Build a cron expression from CronField[].
 */
function buildCronExpression(fields: CronField[]): string {
  return fields.map(fieldToToken).join(' ');
}

/**
 * Generate a human-readable description of a cron expression.
 */
function describeExpression(expr: string): string {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return 'Invalid expression';

  const [min, hour, dom, month, dow] = parts;

  // Common patterns
  if (expr === '* * * * *') return 'Every minute';
  if (min.startsWith('*/') && hour === '*' && dom === '*' && month === '*' && dow === '*') {
    return `Every ${min.substring(2)} minutes`;
  }
  if (hour.startsWith('*/') && min === '0' && dom === '*' && month === '*' && dow === '*') {
    return `Every ${hour.substring(2)} hours`;
  }
  if (min !== '*' && hour !== '*' && dom === '*' && month === '*' && dow === '*') {
    return `Daily at ${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
  }
  if (min !== '*' && hour !== '*' && dom === '*' && month === '*' && dow !== '*') {
    const dayName = FIELD_RANGES[4].labels?.[parseInt(dow)] || `day ${dow}`;
    return `Every ${dayName} at ${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
  }
  if (min !== '*' && hour !== '*' && dom !== '*' && month === '*' && dow === '*') {
    return `Monthly on day ${dom} at ${hour.padStart(2, '0')}:${min.padStart(2, '0')}`;
  }

  // Generic description
  const descParts: string[] = [];
  if (min !== '*') descParts.push(`at minute ${min}`);
  if (hour !== '*') descParts.push(`at hour ${hour}`);
  if (dom !== '*') descParts.push(`on day ${dom}`);
  if (month !== '*') {
    const monthLabel = FIELD_RANGES[3].labels?.[parseInt(month)] || `month ${month}`;
    descParts.push(`in ${monthLabel}`);
  }
  if (dow !== '*') {
    const dowLabel = FIELD_RANGES[4].labels?.[parseInt(dow)] || `weekday ${dow}`;
    descParts.push(`on ${dowLabel}`);
  }

  return descParts.length > 0 ? descParts.join(', ') : 'Every minute';
}

/**
 * Attempt to parse natural language into a cron expression.
 * Returns null if no pattern matches.
 */
function parseNaturalLanguage(text: string): string | null {
  const lower = text.toLowerCase().trim();

  // "every N minutes"
  let match = lower.match(/every\s+(\d+)\s+minutes?/);
  if (match) return `*/${match[1]} * * * *`;

  // "every N hours"
  match = lower.match(/every\s+(\d+)\s+hours?/);
  if (match) return `0 */${match[1]} * * *`;

  // "every day at HH:MM" or "every day at HH"
  match = lower.match(/every\s+day\s+at\s+(\d{1,2}):?(\d{2})?/);
  if (match) {
    const hr = match[1];
    const mn = match[2] || '0';
    return `${mn} ${hr} * * *`;
  }

  // "every [weekday] at HH:MM" or "every [weekday] at HH" or "every [weekday] at HHpm"
  const weekdayPattern = Object.keys(WEEKDAY_MAP).join('|');
  const weekdayRegex = new RegExp(
    `every\\s+(${weekdayPattern})\\s+at\\s+(\\d{1,2}):?(\\d{2})?\\s*(am|pm)?`
  );
  match = lower.match(weekdayRegex);
  if (match) {
    const dayNum = WEEKDAY_MAP[match[1]];
    let hr = parseInt(match[2], 10);
    const mn = match[3] || '0';
    const ampm = match[4];
    if (ampm === 'pm' && hr < 12) hr += 12;
    if (ampm === 'am' && hr === 12) hr = 0;
    return `${mn} ${hr} * * ${dayNum}`;
  }

  // "at HH:MM" (daily)
  match = lower.match(/^at\s+(\d{1,2}):(\d{2})\s*(am|pm)?$/);
  if (match) {
    let hr = parseInt(match[1], 10);
    const mn = match[2];
    const ampm = match[3];
    if (ampm === 'pm' && hr < 12) hr += 12;
    if (ampm === 'am' && hr === 12) hr = 0;
    return `${parseInt(mn, 10)} ${hr} * * *`;
  }

  return null;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function CronExpressionBuilder({
  value,
  onChange,
  timezone = 'UTC',
}: CronExpressionBuilderProps) {
  const [fields, setFields] = React.useState<CronField[]>(() => parseCronExpression(value || '* * * * *'));
  const [naturalInput, setNaturalInput] = React.useState('');
  const [preview, setPreview] = React.useState<string[]>([]);
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewError, setPreviewError] = React.useState<string | null>(null);

  const expression = React.useMemo(() => buildCronExpression(fields), [fields]);
  const description = React.useMemo(() => describeExpression(expression), [expression]);

  // Sync when value prop changes externally
  React.useEffect(() => {
    if (value && value !== expression) {
      setFields(parseCronExpression(value));
    }
  }, [value]); // intentionally only depend on value

  // Notify parent when expression changes
  React.useEffect(() => {
    onChange(expression);
  }, [expression, onChange]);

  // Debounced preview fetch
  React.useEffect(() => {
    if (!expression || expression.trim().split(/\s+/).length !== 5) return;

    setPreviewLoading(true);
    setPreviewError(null);

    const timeout = setTimeout(async () => {
      try {
        const result = await previewCronSchedule(expression, timezone);
        if (result.is_valid) {
          setPreview(result.next_executions);
          setPreviewError(null);
        } else {
          setPreview([]);
          setPreviewError(result.error_message || 'Invalid expression');
        }
      } catch {
        setPreview([]);
        setPreviewError('Failed to preview schedule');
      } finally {
        setPreviewLoading(false);
      }
    }, 600);

    return () => clearTimeout(timeout);
  }, [expression, timezone]);

  // ---------------------------------------------------------------------------
  // Field update
  // ---------------------------------------------------------------------------

  const updateField = (index: number, updates: Partial<CronField>) => {
    setFields((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], ...updates };
      return next;
    });
  };

  // ---------------------------------------------------------------------------
  // Natural language parsing
  // ---------------------------------------------------------------------------

  const handleNaturalLanguage = (text: string) => {
    setNaturalInput(text);
    const parsed = parseNaturalLanguage(text);
    if (parsed) {
      setFields(parseCronExpression(parsed));
    }
  };

  // ---------------------------------------------------------------------------
  // Presets
  // ---------------------------------------------------------------------------

  const presets = [
    { label: 'Hourly', value: '0 * * * *' },
    { label: 'Daily', value: '0 0 * * *' },
    { label: 'Weekly', value: '0 0 * * 1' },
    { label: 'Monthly', value: '0 0 1 * *' },
  ];

  const applyPreset = (val: string) => {
    setFields(parseCronExpression(val));
  };

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div className="space-y-4">
      {/* Natural language input */}
      <div className="space-y-2">
        <Label className="flex items-center gap-2">
          <Wand2 className="h-3.5 w-3.5" />
          Natural Language
        </Label>
        <Input
          placeholder='e.g. "every tuesday at 3pm", "every 15 minutes"'
          value={naturalInput}
          onChange={(e) => handleNaturalLanguage(e.target.value)}
        />
      </div>

      {/* Preset buttons */}
      <div className="flex flex-wrap gap-2">
        {presets.map((p) => (
          <Button
            key={p.label}
            type="button"
            variant="outline"
            size="sm"
            onClick={() => applyPreset(p.value)}
          >
            {p.label}
          </Button>
        ))}
      </div>

      <Separator />

      {/* Field rows */}
      <div className="space-y-3">
        {FIELD_LABELS.map((label, i) => (
          <div key={label} className="grid grid-cols-[120px_130px_1fr] gap-2 items-center">
            <Label className="text-sm">{label}</Label>
            <Select
              value={fields[i].mode}
              onValueChange={(val) => updateField(i, { mode: val as FieldMode })}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="every">Every</SelectItem>
                <SelectItem value="specific">Specific</SelectItem>
                <SelectItem value="range">Range</SelectItem>
                <SelectItem value="interval">Interval</SelectItem>
              </SelectContent>
            </Select>

            <div className="flex items-center gap-1.5">
              {fields[i].mode === 'every' && (
                <span className="text-xs text-muted-foreground">
                  * (all values: {FIELD_RANGES[i].min}-{FIELD_RANGES[i].max})
                </span>
              )}

              {fields[i].mode === 'specific' && (
                <Input
                  className="h-8 font-mono text-xs"
                  placeholder={`e.g. ${FIELD_RANGES[i].min},${FIELD_RANGES[i].min + 1}`}
                  value={fields[i].specific}
                  onChange={(e) => updateField(i, { specific: e.target.value })}
                />
              )}

              {fields[i].mode === 'range' && (
                <>
                  <Input
                    className="h-8 w-20 font-mono text-xs"
                    placeholder={String(FIELD_RANGES[i].min)}
                    value={fields[i].rangeFrom}
                    onChange={(e) => updateField(i, { rangeFrom: e.target.value })}
                  />
                  <span className="text-xs text-muted-foreground">to</span>
                  <Input
                    className="h-8 w-20 font-mono text-xs"
                    placeholder={String(FIELD_RANGES[i].max)}
                    value={fields[i].rangeTo}
                    onChange={(e) => updateField(i, { rangeTo: e.target.value })}
                  />
                </>
              )}

              {fields[i].mode === 'interval' && (
                <div className="flex items-center gap-1.5">
                  <span className="text-xs text-muted-foreground">*/</span>
                  <Input
                    className="h-8 w-20 font-mono text-xs"
                    placeholder="5"
                    value={fields[i].interval}
                    onChange={(e) => updateField(i, { interval: e.target.value })}
                  />
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      <Separator />

      {/* Generated expression */}
      <div className="space-y-2">
        <Label>Generated Expression</Label>
        <div className="bg-muted rounded-md px-4 py-2 font-mono text-sm">{expression}</div>
      </div>

      {/* Human-readable description */}
      <div className="space-y-1">
        <Label>Description</Label>
        <p className="text-sm text-muted-foreground">{description}</p>
      </div>

      {/* Next 5 executions */}
      <Card>
        <CardContent className="pt-4">
          <Label className="text-xs font-medium uppercase tracking-wider">
            Next 5 Executions {timezone && <span className="text-muted-foreground">({timezone})</span>}
          </Label>

          {previewLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground mt-2">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading preview...
            </div>
          )}

          {previewError && !previewLoading && (
            <p className="text-sm text-destructive mt-2">{previewError}</p>
          )}

          {!previewLoading && !previewError && preview.length > 0 && (
            <div className="mt-2 space-y-1">
              {preview.map((time, i) => (
                <div key={i} className="text-sm font-mono">
                  {new Date(time).toLocaleString()}
                </div>
              ))}
            </div>
          )}

          {!previewLoading && !previewError && preview.length === 0 && (
            <p className="text-sm text-muted-foreground mt-2">
              No preview available
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
