/**
 * Statistics panel displaying aggregate document metrics.
 * 
 * Shows total directories, documents, sections, and word count with
 * formatted numbers and responsive layout.
 */

import React from 'react';
import { Folder, FileText, FolderTree, FileType } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { DocumentStats } from '@/types/documents';

interface StatsPanelProps {
  stats: DocumentStats | undefined;
  loading: boolean;
}

export const StatsPanel: React.FC<StatsPanelProps> = React.memo(({ stats, loading }) => {
  if (loading) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {[...Array(4)].map((_, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">Loading...</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="h-8 bg-muted animate-pulse rounded" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  if (!stats) {
    return null;
  }

  const statCards = [
    {
      title: 'Spaces/Categories',
      value: stats.total_directories,
      icon: Folder,
      description: 'Top-level directories',
    },
    {
      title: 'Pages/Documents',
      value: stats.total_documents,
      icon: FileText,
      description: 'Total markdown files',
    },
    {
      title: 'Sections',
      value: stats.total_subdirectories,
      icon: FolderTree,
      description: 'Subdirectories',
    },
    {
      title: 'Words',
      value: stats.total_words,
      icon: FileType,
      description: 'Total word count',
    },
  ];

  return (
    <div aria-label="Document statistics" className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
      {statCards.map((stat) => (
        <Card key={stat.title} aria-label={`${stat.title}: ${formatNumber(stat.value)}`}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
            <stat.icon className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{formatNumber(stat.value)}</div>
            <p className="text-xs text-muted-foreground">{stat.description}</p>
          </CardContent>
        </Card>
      ))}
    </div>
  );
});

StatsPanel.displayName = 'StatsPanel';

// Format numbers with thousand separators
const formatNumber = (num: number): string => {
  return num.toLocaleString('en-US');
};
