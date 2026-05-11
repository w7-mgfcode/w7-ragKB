import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface EmbedField {
  name: string;
  value: string;
  inline?: boolean;
}

interface EmbedThumbnail {
  url: string;
}

interface EmbedFooter {
  text: string;
}

interface DiscordEmbed {
  title?: string;
  description?: string;
  color?: number;
  fields?: EmbedField[];
  thumbnail?: EmbedThumbnail;
  footer?: EmbedFooter;
  timestamp?: string;
}

interface DiscordEmbedPreviewProps {
  embed: DiscordEmbed;
}

const DISCORD_BLURPLE = '#5865F2';

/**
 * Converts a numeric color value to a CSS hex string.
 * Discord sends colors as decimal integers (e.g. 5793266 -> #586FF2).
 */
const numberToHex = (color: number): string => {
  return '#' + color.toString(16).padStart(6, '0');
};

export const DiscordEmbedPreview = ({ embed }: DiscordEmbedPreviewProps) => {
  const borderColor =
    embed.color !== undefined ? numberToHex(embed.color) : DISCORD_BLURPLE;

  const formattedTimestamp = embed.timestamp
    ? new Date(embed.timestamp).toLocaleString()
    : null;

  return (
    <Card
      className="overflow-hidden my-2"
      style={{ borderLeft: `4px solid ${borderColor}` }}
    >
      <CardContent className="p-3">
        <div className="flex gap-3">
          {/* Main content */}
          <div className="flex-1 min-w-0 space-y-2">
            {embed.title && (
              <div className="font-bold text-sm">{embed.title}</div>
            )}

            {embed.description && (
              <div className="text-sm text-foreground whitespace-pre-wrap">
                {embed.description}
              </div>
            )}

            {/* Fields grid */}
            {embed.fields && embed.fields.length > 0 && (
              <div className="grid grid-cols-3 gap-2 mt-2">
                {embed.fields.map((field, index) => (
                  <div
                    key={index}
                    className={cn(
                      'min-w-0',
                      field.inline ? 'col-span-1' : 'col-span-3'
                    )}
                  >
                    <div className="text-xs font-semibold text-muted-foreground">
                      {field.name}
                    </div>
                    <div className="text-sm whitespace-pre-wrap break-words">
                      {field.value}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Footer + timestamp */}
            {(embed.footer || formattedTimestamp) && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground mt-2">
                {embed.footer && <span>{embed.footer.text}</span>}
                {embed.footer && formattedTimestamp && <span>-</span>}
                {formattedTimestamp && <span>{formattedTimestamp}</span>}
              </div>
            )}
          </div>

          {/* Thumbnail */}
          {embed.thumbnail && (
            <div className="shrink-0">
              <img
                src={embed.thumbnail.url}
                alt="Embed thumbnail"
                className="h-16 w-16 rounded object-cover"
              />
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
};
