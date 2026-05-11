/**
 * Document tree component with hierarchical navigation.
 *
 * Displays documents and directories in a tree structure with expand/collapse,
 * selection checkboxes, search filtering, keyboard navigation, and virtual
 * scrolling for large trees (50+ visible nodes).
 */

import React, { useState, useMemo, useRef, useCallback } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { ChevronRight, ChevronDown, Folder, File } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Checkbox } from '@/components/ui/checkbox';
import { useTreeKeyboard, type FlatTreeNode } from '@/hooks/useTreeKeyboard';
import { announce } from '@/lib/announcer';
import { SyncStatusBadge } from './SyncStatusBadge';
import type { TreeNode, DocumentSyncInfo } from '@/types/documents';

interface DocumentTreeProps {
  nodes: TreeNode[];
  selectedPath: string | null;
  onSelect: (path: string) => void;
  searchQuery: string;
  selectedPaths: Set<string>;
  onToggleSelect: (path: string) => void;
  syncStatuses?: Record<string, DocumentSyncInfo>;
}

interface FlatRenderNode extends FlatTreeNode {
  node: TreeNode;
  isExpanded: boolean;
  siblingsCount: number;
  posInSet: number;
}

const VIRTUAL_THRESHOLD = 50;

export const DocumentTree: React.FC<DocumentTreeProps> = React.memo(({
  nodes,
  selectedPath,
  onSelect,
  searchQuery,
  selectedPaths,
  onToggleSelect,
  syncStatuses,
}) => {
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set());
  const containerRef = useRef<HTMLDivElement>(null);

  const toggleExpand = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  }, []);

  // Filter tree based on search query
  const filteredNodes = useMemo(() => {
    if (!searchQuery) return nodes;

    const filterTree = (treeNodes: TreeNode[]): TreeNode[] => {
      return treeNodes
        .map((node) => {
          if (node.type === 'directory') {
            const filteredChildren = filterTree(node.children);
            if (filteredChildren.length > 0) {
              return { ...node, children: filteredChildren };
            }
            return null;
          } else {
            if (node.name.toLowerCase().includes(searchQuery.toLowerCase())) {
              return node;
            }
            return null;
          }
        })
        .filter((node): node is TreeNode => node !== null);
    };

    return filterTree(nodes);
  }, [nodes, searchQuery]);

  // Flatten visible tree for keyboard navigation and virtual scrolling
  const flatRenderNodes = useMemo(() => {
    const result: FlatRenderNode[] = [];
    const flatten = (treeNodes: TreeNode[], depth: number, parentPath: string | null) => {
      for (let i = 0; i < treeNodes.length; i++) {
        const node = treeNodes[i];
        const isExpanded = expandedPaths.has(node.path);
        result.push({
          path: node.path,
          name: node.name,
          type: node.type,
          depth,
          parentPath,
          node,
          isExpanded,
          siblingsCount: treeNodes.length,
          posInSet: i + 1,
        });
        if (node.type === 'directory' && isExpanded && node.children) {
          flatten(node.children, depth + 1, node.path);
        }
      }
    };
    flatten(filteredNodes, 0, null);
    return result;
  }, [filteredNodes, expandedPaths]);

  // FlatTreeNode subset for keyboard hook
  const flatNodes: FlatTreeNode[] = flatRenderNodes;

  const handleToggleExpand = useCallback((path: string) => {
    toggleExpand(path);
    const node = flatRenderNodes.find((n) => n.path === path);
    if (node) {
      const wasExpanded = expandedPaths.has(path);
      if (wasExpanded) {
        announce(`${node.name} collapsed`);
      } else {
        announce(`${node.name} expanded`);
      }
    }
  }, [toggleExpand, flatRenderNodes, expandedPaths]);

  const { focusedPath, handleKeyDown } = useTreeKeyboard({
    flatNodes,
    expandedPaths,
    onToggleExpand: handleToggleExpand,
    onSelect,
    containerRef,
  });

  const useVirtual = flatRenderNodes.length >= VIRTUAL_THRESHOLD;

  const virtualizer = useVirtualizer({
    count: useVirtual ? flatRenderNodes.length : 0,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 32,
    overscan: 10,
  });

  const highlightText = (text: string) => {
    if (!searchQuery) return text;
    const index = text.toLowerCase().indexOf(searchQuery.toLowerCase());
    if (index === -1) return text;
    return (
      <>
        {text.substring(0, index)}
        <span className="bg-yellow-200 dark:bg-yellow-800">
          {text.substring(index, index + searchQuery.length)}
        </span>
        {text.substring(index + searchQuery.length)}
      </>
    );
  };

  const renderFlatNode = (flatNode: FlatRenderNode) => {
    const { node, depth, isExpanded, siblingsCount, posInSet } = flatNode;
    const isSelected = selectedPath === node.path;
    const isFocused = focusedPath === node.path;

    if (node.type === 'directory') {
      return (
        <div
          role="treeitem"
          aria-expanded={isExpanded}
          aria-level={depth + 1}
          aria-setsize={siblingsCount}
          aria-posinset={posInSet}
          data-path={node.path}
          tabIndex={isFocused ? 0 : -1}
          className={cn(
            'flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer hover:bg-accent',
            isSelected && 'bg-accent',
            isFocused && 'ring-2 ring-ring ring-offset-1'
          )}
          style={{ paddingLeft: `${depth * 16 + 8}px` }}
          onClick={() => handleToggleExpand(node.path)}
        >
          {isExpanded ? (
            <ChevronDown className="h-4 w-4 shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0" />
          )}
          <Folder className="h-4 w-4 text-blue-500 shrink-0" />
          <span className="flex-1 text-sm truncate">{highlightText(node.name)}</span>
        </div>
      );
    }

    const isChecked = selectedPaths.has(node.path);
    const syncInfo = syncStatuses?.[node.path];
    return (
      <div
        role="treeitem"
        aria-selected={isSelected}
        aria-level={depth + 1}
        aria-setsize={siblingsCount}
        aria-posinset={posInSet}
        data-path={node.path}
        tabIndex={isFocused ? 0 : -1}
        className={cn(
          'flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer hover:bg-accent',
          isSelected && 'bg-accent',
          isFocused && 'ring-2 ring-ring ring-offset-1'
        )}
        style={{ paddingLeft: `${depth * 16 + 32}px` }}
        onClick={() => onSelect(node.path)}
        title={node.path}
      >
        <Checkbox
          checked={isChecked}
          aria-label={`Select ${node.name}`}
          onCheckedChange={() => onToggleSelect(node.path)}
          onClick={(e) => e.stopPropagation()}
        />
        <File className="h-4 w-4 text-gray-500 shrink-0" />
        <span className="flex-1 text-sm truncate">{highlightText(node.name)}</span>
        {syncInfo && (
          <SyncStatusBadge
            status={syncInfo.sync_status}
            errorMessage={syncInfo.error_message}
            size="sm"
          />
        )}
        {node.metadata && (
          <span className="text-xs text-muted-foreground shrink-0">
            {node.metadata.word_count}w
          </span>
        )}
      </div>
    );
  };

  // Recursive render for small trees (preserves DOM nesting with role="group")
  const renderNode = (node: TreeNode, depth: number, siblingsCount: number, posInSet: number) => {
    const isExpanded = expandedPaths.has(node.path);
    const isSelected = selectedPath === node.path;
    const isChecked = selectedPaths.has(node.path);
    const isFocused = focusedPath === node.path;

    if (node.type === 'directory') {
      return (
        <div key={node.path}>
          <div
            role="treeitem"
            aria-expanded={isExpanded}
            aria-level={depth + 1}
            aria-setsize={siblingsCount}
            aria-posinset={posInSet}
            data-path={node.path}
            tabIndex={isFocused ? 0 : -1}
            className={cn(
              'flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer hover:bg-accent',
              isSelected && 'bg-accent',
              isFocused && 'ring-2 ring-ring ring-offset-1'
            )}
            style={{ paddingLeft: `${depth * 16 + 8}px` }}
            onClick={() => handleToggleExpand(node.path)}
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4 shrink-0" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0" />
            )}
            <Folder className="h-4 w-4 text-blue-500 shrink-0" />
            <span className="flex-1 text-sm truncate">{highlightText(node.name)}</span>
          </div>

          {isExpanded && node.children && (
            <div role="group">
              {node.children.map((child, i) => renderNode(child, depth + 1, node.children.length, i + 1))}
            </div>
          )}
        </div>
      );
    }

    const syncInfo = syncStatuses?.[node.path];
    return (
      <div
        key={node.path}
        role="treeitem"
        aria-selected={isSelected}
        aria-level={depth + 1}
        aria-setsize={siblingsCount}
        aria-posinset={posInSet}
        data-path={node.path}
        tabIndex={isFocused ? 0 : -1}
        className={cn(
          'flex items-center gap-2 px-2 py-1.5 rounded-md cursor-pointer hover:bg-accent',
          isSelected && 'bg-accent',
          isFocused && 'ring-2 ring-ring ring-offset-1'
        )}
        style={{ paddingLeft: `${depth * 16 + 32}px` }}
        onClick={() => onSelect(node.path)}
        title={node.path}
      >
        <Checkbox
          checked={isChecked}
          aria-label={`Select ${node.name}`}
          onCheckedChange={() => onToggleSelect(node.path)}
          onClick={(e) => e.stopPropagation()}
        />
        <File className="h-4 w-4 text-gray-500 shrink-0" />
        <span className="flex-1 text-sm truncate">{highlightText(node.name)}</span>
        {syncInfo && (
          <SyncStatusBadge
            status={syncInfo.sync_status}
            errorMessage={syncInfo.error_message}
            size="sm"
          />
        )}
        {node.metadata && (
          <span className="text-xs text-muted-foreground shrink-0">
            {node.metadata.word_count}w
          </span>
        )}
      </div>
    );
  };

  if (filteredNodes.length === 0) {
    return (
      <div className="p-4 text-center text-sm text-muted-foreground">
        {searchQuery ? 'No documents match your search' : 'No documents found'}
      </div>
    );
  }

  // Virtual scrolling for large trees
  if (useVirtual) {
    return (
      <div
        ref={containerRef}
        role="tree"
        aria-label="Document tree"
        className="p-2"
        style={{ height: '100%', overflow: 'auto' }}
        onKeyDown={handleKeyDown}
      >
        <div
          style={{
            height: `${virtualizer.getTotalSize()}px`,
            width: '100%',
            position: 'relative',
          }}
        >
          {virtualizer.getVirtualItems().map((virtualRow) => {
            const flatNode = flatRenderNodes[virtualRow.index];
            return (
              <div
                key={flatNode.path}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  height: `${virtualRow.size}px`,
                  transform: `translateY(${virtualRow.start}px)`,
                }}
              >
                {renderFlatNode(flatNode)}
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  // Standard render for small trees
  return (
    <div
      ref={containerRef}
      role="tree"
      aria-label="Document tree"
      className="space-y-0.5 p-2"
      onKeyDown={handleKeyDown}
    >
      {filteredNodes.map((node, i) => renderNode(node, 0, filteredNodes.length, i + 1))}
    </div>
  );
});

DocumentTree.displayName = 'DocumentTree';
