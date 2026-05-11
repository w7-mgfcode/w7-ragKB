import { useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeRaw from 'rehype-raw';
import breaks from 'remark-breaks';
import DOMPurify from 'dompurify';
import { PrismLight as SyntaxHighlighter } from 'react-syntax-highlighter';
import { atomDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { cn } from '@/lib/utils';

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

interface CodeProps {
  node?: Element;
  inline?: boolean;
  className?: string;
  children: React.ReactNode;
}

export const MarkdownRenderer = ({ content, className }: MarkdownRendererProps) => {
  const sanitized = useMemo(() => {
    return DOMPurify.sanitize(content, {
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'hr',
        'ul', 'ol', 'li', 'blockquote', 'pre', 'code',
        'a', 'strong', 'em', 'del', 'img', 'table', 'thead',
        'tbody', 'tr', 'th', 'td', 'sup', 'sub', 'details', 'summary',
      ],
      ALLOWED_ATTR: ['href', 'src', 'alt', 'title', 'class', 'id', 'target', 'rel'],
    });
  }, [content]);

  return (
    <div className={cn('prose prose-sm dark:prose-invert max-w-none [&>*:first-child]:mt-0 [&>*:last-child]:mb-0', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, breaks]}
        rehypePlugins={[rehypeRaw]}
        components={{
          p: ({ children }) => <p className="mb-4 last:mb-0">{children}</p>,
          h1: ({ children }) => <h1 className="text-2xl font-bold mt-6 mb-4 first:mt-0">{children}</h1>,
          h2: ({ children }) => <h2 className="text-xl font-bold mt-5 mb-3 first:mt-0">{children}</h2>,
          h3: ({ children }) => <h3 className="text-lg font-bold mt-4 mb-2 first:mt-0">{children}</h3>,
          h4: ({ children }) => <h4 className="text-base font-bold mt-3 mb-2 first:mt-0">{children}</h4>,
          a: ({ href, children }) => (
            <a href={href} className="text-blue-400 hover:text-blue-500 hover:underline" target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          code({ inline, className: codeClassName, children, ...props }: CodeProps) {
            const match = /language-(\w+)/.exec(codeClassName || '');
            return !inline && match ? (
              <SyntaxHighlighter
                style={atomDark}
                language={match[1]}
                PreTag="div"
                className="rounded-md !bg-gray-900 !p-4 !my-2"
                {...props}
              >
                {String(children).replace(/\n$/, '')}
              </SyntaxHighlighter>
            ) : (
              <code className={cn('bg-gray-800 px-1 py-0.5 rounded text-gray-200', codeClassName)} {...props}>
                {children}
              </code>
            );
          },
        }}
      >
        {sanitized}
      </ReactMarkdown>
    </div>
  );
};
