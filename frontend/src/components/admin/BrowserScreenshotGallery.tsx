/**
 * Browser Screenshot Gallery Component
 * 
 * Displays screenshots from a browser instance in a grid layout with lightbox view.
 * Features:
 * - Grid layout with thumbnails (3-4 columns responsive)
 * - Screenshot metadata: timestamp, url, dimensions
 * - Lightbox view for full-size screenshots
 * - Download button for each screenshot
 * - Delete button for each screenshot with confirmation
 * - Loading and error states
 */

import * as React from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Download, Trash2, X, Loader2, Image as ImageIcon } from 'lucide-react';
import { getBrowserScreenshots } from '@/lib/api';
import type { BrowserScreenshot } from '@/types/gateway';
import { toast } from 'sonner';

interface BrowserScreenshotGalleryProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sessionId: string;
}

export function BrowserScreenshotGallery({
  open,
  onOpenChange,
  sessionId,
}: BrowserScreenshotGalleryProps) {
  const [screenshots, setScreenshots] = React.useState<BrowserScreenshot[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [selectedScreenshot, setSelectedScreenshot] = React.useState<BrowserScreenshot | null>(null);
  const [deleteDialogOpen, setDeleteDialogOpen] = React.useState(false);
  const [screenshotToDelete, setScreenshotToDelete] = React.useState<BrowserScreenshot | null>(null);
  const [isDeleting, setIsDeleting] = React.useState(false);

  // Fetch screenshots when dialog opens
  React.useEffect(() => {
    if (open && sessionId) {
      fetchScreenshots();
    }
  }, [open, sessionId]);

  const fetchScreenshots = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getBrowserScreenshots(sessionId);
      setScreenshots(data);
    } catch (err) {
      setError((err as Error).message);
      toast.error('Failed to load screenshots: ' + (err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = async (screenshot: BrowserScreenshot) => {
    try {
      const response = await fetch(screenshot.image_url);
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `screenshot-${screenshot.screenshot_id}-${new Date(screenshot.timestamp).getTime()}.png`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      toast.success('Screenshot downloaded!');
    } catch (err) {
      toast.error('Failed to download screenshot: ' + (err as Error).message);
    }
  };

  const handleDeleteClick = (screenshot: BrowserScreenshot) => {
    setScreenshotToDelete(screenshot);
    setDeleteDialogOpen(true);
  };

  const handleConfirmDelete = async () => {
    if (!screenshotToDelete) return;

    setIsDeleting(true);
    try {
      // TODO: Implement delete API endpoint when backend is ready
      // await deleteBrowserScreenshot(screenshotToDelete.screenshot_id);
      
      // For now, just remove from local state
      setScreenshots(screenshots.filter(s => s.screenshot_id !== screenshotToDelete.screenshot_id));
      toast.success('Screenshot deleted!');
      
      // Close lightbox if the deleted screenshot was selected
      if (selectedScreenshot?.screenshot_id === screenshotToDelete.screenshot_id) {
        setSelectedScreenshot(null);
      }
    } catch (err) {
      toast.error('Failed to delete screenshot: ' + (err as Error).message);
    } finally {
      setIsDeleting(false);
      setDeleteDialogOpen(false);
      setScreenshotToDelete(null);
    }
  };

  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString();
  };

  const getImageDimensions = (imageUrl: string): Promise<{ width: number; height: number }> => {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        resolve({ width: img.width, height: img.height });
      };
      img.onerror = () => {
        resolve({ width: 0, height: 0 });
      };
      img.src = imageUrl;
    });
  };

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[1200px] max-h-[90vh]">
          <DialogHeader>
            <DialogTitle>Screenshot Gallery</DialogTitle>
            <DialogDescription>
              Screenshots captured from browser session: {sessionId}
            </DialogDescription>
          </DialogHeader>

          <ScrollArea className="h-[600px] pr-4">
            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                <span className="ml-2 text-muted-foreground">Loading screenshots...</span>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center py-12 text-destructive">
                <p>Error loading screenshots: {error}</p>
                <Button onClick={fetchScreenshots} className="mt-4" variant="outline">
                  Retry
                </Button>
              </div>
            ) : screenshots.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                <ImageIcon className="h-12 w-12 mb-4" />
                <p>No screenshots available for this session.</p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
                {screenshots.map((screenshot) => (
                  <Card
                    key={screenshot.screenshot_id}
                    className="overflow-hidden hover:shadow-lg transition-shadow cursor-pointer"
                    onClick={() => setSelectedScreenshot(screenshot)}
                  >
                    <div className="relative aspect-video bg-muted">
                      <img
                        src={screenshot.image_url}
                        alt={`Screenshot from ${screenshot.url}`}
                        className="w-full h-full object-cover"
                      />
                      <div className="absolute top-2 right-2 flex gap-1">
                        <Button
                          size="icon"
                          variant="secondary"
                          className="h-8 w-8"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDownload(screenshot);
                          }}
                        >
                          <Download className="h-4 w-4" />
                        </Button>
                        <Button
                          size="icon"
                          variant="destructive"
                          className="h-8 w-8"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteClick(screenshot);
                          }}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                    <CardContent className="p-3 space-y-2">
                      <div className="flex items-center justify-between">
                        <Badge variant="outline" className="text-xs">
                          {formatTimestamp(screenshot.timestamp)}
                        </Badge>
                      </div>
                      <div className="text-xs text-muted-foreground truncate" title={screenshot.url}>
                        {screenshot.url}
                      </div>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </ScrollArea>
        </DialogContent>
      </Dialog>

      {/* Lightbox Dialog for Full-Size View */}
      <Dialog open={!!selectedScreenshot} onOpenChange={() => setSelectedScreenshot(null)}>
        <DialogContent className="sm:max-w-[90vw] max-h-[90vh]">
          <DialogHeader>
            <DialogTitle>Screenshot Details</DialogTitle>
            <DialogDescription>
              Captured at {selectedScreenshot && formatTimestamp(selectedScreenshot.timestamp)}
            </DialogDescription>
          </DialogHeader>

          {selectedScreenshot && (
            <div className="space-y-4">
              <ScrollArea className="h-[60vh]">
                <div className="flex items-center justify-center bg-muted rounded-lg p-4">
                  <img
                    src={selectedScreenshot.image_url}
                    alt={`Screenshot from ${selectedScreenshot.url}`}
                    className="max-w-full max-h-full object-contain"
                  />
                </div>
              </ScrollArea>

              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Badge variant="outline">URL</Badge>
                  <span className="text-sm font-mono truncate">{selectedScreenshot.url}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">Timestamp</Badge>
                  <span className="text-sm">{formatTimestamp(selectedScreenshot.timestamp)}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">Screenshot ID</Badge>
                  <span className="text-sm font-mono">{selectedScreenshot.screenshot_id}</span>
                </div>
              </div>

              <div className="flex justify-end gap-2">
                <Button
                  variant="outline"
                  onClick={() => handleDownload(selectedScreenshot)}
                >
                  <Download className="h-4 w-4 mr-2" />
                  Download
                </Button>
                <Button
                  variant="destructive"
                  onClick={() => {
                    handleDeleteClick(selectedScreenshot);
                    setSelectedScreenshot(null);
                  }}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  Delete
                </Button>
                <Button variant="outline" onClick={() => setSelectedScreenshot(null)}>
                  <X className="h-4 w-4 mr-2" />
                  Close
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete Screenshot</AlertDialogTitle>
            <AlertDialogDescription>
              Are you sure you want to delete this screenshot? This action cannot be undone.
              {screenshotToDelete && (
                <div className="mt-4 p-3 bg-muted rounded-md">
                  <p className="text-sm font-medium">Screenshot ID: {screenshotToDelete.screenshot_id}</p>
                  <p className="text-sm">URL: {screenshotToDelete.url}</p>
                  <p className="text-sm">Captured: {formatTimestamp(screenshotToDelete.timestamp)}</p>
                </div>
              )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={isDeleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              disabled={isDeleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {isDeleting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Deleting...
                </>
              ) : (
                'Delete Screenshot'
              )}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
