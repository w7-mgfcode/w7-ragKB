/**
 * Search bar component with debouncing and optional sync status filter.
 *
 * Controlled component that debounces onSearch calls.
 */

import React, { useEffect, useCallback, useRef } from 'react';
import { Search, X } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { SyncStatus } from '@/types/documents';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  onSearch: (query: string) => void;
  placeholder?: string;
  debounceMs?: number;
  syncStatusFilter?: SyncStatus | 'all';
  onSyncStatusFilterChange?: (status: SyncStatus | 'all') => void;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  value,
  onChange,
  onSearch,
  placeholder = 'Search documents...',
  debounceMs = 300,
  syncStatusFilter,
  onSyncStatusFilterChange,
}) => {
  const inputRef = useRef<HTMLInputElement>(null);

  // Debounce onSearch calls
  useEffect(() => {
    const timer = setTimeout(() => {
      onSearch(value);
    }, debounceMs);
    return () => clearTimeout(timer);
  }, [value, debounceMs, onSearch]);

  const handleClear = useCallback(() => {
    onChange('');
    onSearch('');
  }, [onChange, onSearch]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === 'f') {
        e.preventDefault();
        inputRef.current?.focus();
      }
      if (e.key === 'Escape' && value) {
        handleClear();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [value, handleClear]);

  return (
    <div role="search" aria-label="Search documents" className="flex gap-2 items-center">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          ref={inputRef}
          type="search"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="pl-10 pr-10"
        />
        {value && (
          <Button
            variant="ghost"
            size="icon"
            aria-label="Clear search"
            className="absolute right-1 top-1/2 transform -translate-y-1/2 h-7 w-7"
            onClick={handleClear}
          >
            <X className="h-4 w-4" />
          </Button>
        )}
      </div>
      {onSyncStatusFilterChange && (
        <Select
          value={syncStatusFilter || 'all'}
          onValueChange={(v) => onSyncStatusFilterChange(v as SyncStatus | 'all')}
        >
          <SelectTrigger className="w-[140px]" aria-label="Filter by sync status">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            <SelectItem value="in_sync">In Sync</SelectItem>
            <SelectItem value="out_of_sync">Out of Sync</SelectItem>
            <SelectItem value="processing">Processing</SelectItem>
            <SelectItem value="error">Error</SelectItem>
            <SelectItem value="pending_indexing">Pending</SelectItem>
            <SelectItem value="orphaned_chunks">Orphaned</SelectItem>
          </SelectContent>
        </Select>
      )}
    </div>
  );
};
