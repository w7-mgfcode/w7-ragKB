import { useState, useCallback } from 'react';

export interface FlatTreeNode {
  path: string;
  name: string;
  type: 'directory' | 'document';
  depth: number;
  parentPath: string | null;
}

interface UseTreeKeyboardOptions {
  flatNodes: FlatTreeNode[];
  expandedPaths: Set<string>;
  onToggleExpand: (path: string) => void;
  onSelect: (path: string) => void;
  containerRef: React.RefObject<HTMLDivElement | null>;
}

export function useTreeKeyboard({
  flatNodes,
  expandedPaths,
  onToggleExpand,
  onSelect,
  containerRef,
}: UseTreeKeyboardOptions) {
  const [focusedPath, setFocusedPath] = useState<string | null>(null);

  const focusNode = useCallback(
    (path: string) => {
      setFocusedPath(path);
      const container = containerRef.current;
      if (container) {
        const el = container.querySelector(`[data-path="${CSS.escape(path)}"]`) as HTMLElement | null;
        el?.focus();
      }
    },
    [containerRef],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (flatNodes.length === 0) return;

      const currentIndex = focusedPath
        ? flatNodes.findIndex((n) => n.path === focusedPath)
        : -1;
      const currentNode = currentIndex >= 0 ? flatNodes[currentIndex] : null;

      switch (e.key) {
        case 'ArrowDown': {
          e.preventDefault();
          const nextIndex = currentIndex < flatNodes.length - 1 ? currentIndex + 1 : 0;
          focusNode(flatNodes[nextIndex].path);
          break;
        }
        case 'ArrowUp': {
          e.preventDefault();
          const prevIndex = currentIndex > 0 ? currentIndex - 1 : flatNodes.length - 1;
          focusNode(flatNodes[prevIndex].path);
          break;
        }
        case 'ArrowRight': {
          e.preventDefault();
          if (currentNode?.type === 'directory') {
            if (!expandedPaths.has(currentNode.path)) {
              onToggleExpand(currentNode.path);
            } else {
              // Move to first child
              const nextIndex = currentIndex + 1;
              if (nextIndex < flatNodes.length && flatNodes[nextIndex].depth > currentNode.depth) {
                focusNode(flatNodes[nextIndex].path);
              }
            }
          }
          break;
        }
        case 'ArrowLeft': {
          e.preventDefault();
          if (currentNode?.type === 'directory' && expandedPaths.has(currentNode.path)) {
            onToggleExpand(currentNode.path);
          } else if (currentNode?.parentPath) {
            focusNode(currentNode.parentPath);
          }
          break;
        }
        case 'Enter': {
          e.preventDefault();
          if (currentNode) {
            if (currentNode.type === 'directory') {
              onToggleExpand(currentNode.path);
            } else {
              onSelect(currentNode.path);
            }
          }
          break;
        }
        case 'Home': {
          e.preventDefault();
          if (flatNodes.length > 0) {
            focusNode(flatNodes[0].path);
          }
          break;
        }
        case 'End': {
          e.preventDefault();
          if (flatNodes.length > 0) {
            focusNode(flatNodes[flatNodes.length - 1].path);
          }
          break;
        }
      }
    },
    [flatNodes, focusedPath, expandedPaths, onToggleExpand, onSelect, focusNode],
  );

  return { focusedPath, handleKeyDown, setFocusedPath: focusNode };
}
