/**
 * Session Detail Drawer Component
 * 
 * Displays detailed information about a session including:
 * - Session metadata
 * - Message history with pagination
 * - Inter-session message indicators
 * - Memory usage
 * - Tool usage log
 */

import { useState } from 'react';
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Progress } from '@/components/ui/progress';
import { Download, MessageSquare, X, Shrink } from 'lucide-react';
import { useSession, useSessionHistory } from '@/hooks/useGateway';
import { toast } from 'sonner';
import { SendMessageDialog } from './SendMessageDialog';
import { SessionCompactionInterface } from './SessionCompactionInterface';

interface SessionDetailDrawerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string | null;
}

export function SessionDetailDrawer({
  open,
  onOpenChange,
  sessionId,
}: SessionDetailDrawerProps) {
  const [sendMessageOpen, setSendMessageOpen] = useState(false);
  const [compactOpen, setCompactOpen] = useState(false);
  const { session, loading: sessionLoading, refetch: refetchSession } = useSession(sessionId || '');
  const { messages, loading: messagesLoading, loadMore, hasMore, refetch: refetchMessages } = useSessionHistory(
    sessionId || ''
  );

  const handleExport = () => {
    if (!session || !messages) return;

    const exportData = {
      session: session,
      messages: messages,
      exported_at: new Date().toISOString(),
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: 'application/json',
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `session-${session.session_id}-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    toast.success('Conversation exported successfully!');
  };

  if (!sessionId) {
    return null;
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent className="max-h-[90vh]">
        <div className="mx-auto w-full max-w-4xl">
          <DrawerHeader>
            <div className="flex items-center justify-between">
              <div>
                <DrawerTitle>Session Details</DrawerTitle>
                <DrawerDescription>
                  {sessionLoading ? 'Loading...' : `Session ID: ${sessionId}`}
                </DrawerDescription>
              </div>
              <DrawerClose asChild>
                <Button variant="ghost" size="icon">
                  <X className="h-4 w-4" />
                </Button>
              </DrawerClose>
            </div>
          </DrawerHeader>

          <div className="p-4 space-y-4">
            {sessionLoading ? (
              <div className="text-center py-8">Loading session details...</div>
            ) : session ? (
              <>
                {/* Session Metadata */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Session Metadata</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-sm text-muted-foreground">Channel</p>
                        <p className="font-medium">{session.channel_id}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">User ID</p>
                        <p className="font-medium">{session.user_id}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Session Type</p>
                        <Badge className="capitalize">{session.session_type}</Badge>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Activation Mode</p>
                        <Badge variant="outline" className="capitalize">
                          {session.activation_mode}
                        </Badge>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Message Count</p>
                        <p className="font-medium">{session.message_count}</p>
                      </div>
                      <div>
                        <p className="text-sm text-muted-foreground">Last Activity</p>
                        <p className="font-medium">
                          {new Date(session.last_activity_at).toLocaleString()}
                        </p>
                      </div>
                    </div>

                    {/* Memory Usage */}
                    {session.memory_usage !== undefined && (
                      <div className="mt-4">
                        <div className="flex items-center justify-between mb-2">
                          <p className="text-sm text-muted-foreground">Memory Usage</p>
                          <p className="text-sm font-medium">
                            {session.memory_usage}% of limit
                          </p>
                        </div>
                        <Progress value={session.memory_usage} />
                      </div>
                    )}

                    {/* Tool Allowlist */}
                    {session.tool_allowlist && session.tool_allowlist.length > 0 && (
                      <div className="mt-4">
                        <p className="text-sm text-muted-foreground mb-2">Tool Allowlist</p>
                        <div className="flex flex-wrap gap-2">
                          {session.tool_allowlist.map((tool) => (
                            <Badge key={tool} variant="secondary">
                              {tool}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </CardContent>
                </Card>

                <Separator />

                {/* Message History */}
                <Card>
                  <CardHeader>
                    <CardTitle className="text-sm">Message History</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <ScrollArea className="h-[400px] pr-4">
                      {messagesLoading && messages.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                          Loading messages...
                        </div>
                      ) : messages.length > 0 ? (
                        <div className="space-y-4">
                          {messages.map((message) => (
                            <div
                              key={message.message_id}
                              className="border rounded-lg p-3 space-y-2"
                            >
                              <div className="flex items-center justify-between">
                                <Badge
                                  variant={
                                    message.role === 'user'
                                      ? 'default'
                                      : message.role === 'assistant'
                                      ? 'secondary'
                                      : 'outline'
                                  }
                                >
                                  {message.role}
                                </Badge>
                                <span className="text-xs text-muted-foreground">
                                  {new Date(message.created_at).toLocaleString()}
                                </span>
                              </div>
                              <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                              {message.source_session && (
                                <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                  <MessageSquare className="h-3 w-3" />
                                  <span>From session: {message.source_session}</span>
                                </div>
                              )}
                            </div>
                          ))}

                          {hasMore && (
                            <Button
                              variant="outline"
                              className="w-full"
                              onClick={loadMore}
                              disabled={messagesLoading}
                            >
                              {messagesLoading ? 'Loading...' : 'Load More'}
                            </Button>
                          )}
                        </div>
                      ) : (
                        <div className="text-center py-8 text-muted-foreground">
                          No messages yet
                        </div>
                      )}
                    </ScrollArea>
                  </CardContent>
                </Card>
              </>
            ) : (
              <div className="text-center py-8 text-destructive">
                Session not found
              </div>
            )}
          </div>

          <DrawerFooter>
            <div className="flex gap-2">
              <Button onClick={handleExport} variant="outline" disabled={!session}>
                <Download className="mr-2 h-4 w-4" />
                Export Conversation
              </Button>
              <Button onClick={() => setCompactOpen(true)} variant="outline" disabled={!session}>
                <Shrink className="mr-2 h-4 w-4" />
                Compact
              </Button>
              <Button onClick={() => setSendMessageOpen(true)} disabled={!session}>
                <MessageSquare className="mr-2 h-4 w-4" />
                Send Message
              </Button>
              <DrawerClose asChild>
                <Button variant="outline">Close</Button>
              </DrawerClose>
            </div>
          </DrawerFooter>
        </div>
      </DrawerContent>

      {/* Send Message Dialog */}
      <SendMessageDialog
        open={sendMessageOpen}
        onOpenChange={setSendMessageOpen}
        defaultSessionId={sessionId || undefined}
        onSuccess={() => {
          refetchSession();
          refetchMessages();
        }}
      />

      {/* Session Compaction Dialog */}
      {session && (
        <SessionCompactionInterface
          open={compactOpen}
          onOpenChange={setCompactOpen}
          sessionId={session.session_id}
          onSuccess={() => {
            refetchSession();
            refetchMessages();
          }}
        />
      )}
    </Drawer>
  );
}
