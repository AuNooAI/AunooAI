/**
 * AuspexChatMessages - Message display area for the chat
 */

import { useEffect, useRef } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Bot, User, Copy, Check, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { cn } from '../ui/utils';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  isStreaming?: boolean;
}

interface AuspexChatMessagesProps {
  messages: Message[];
  isLoading?: boolean;
}

function MessageContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        // Style links
        a: ({ href, children }) => (
          <a
            href={href}
            target="_blank"
            rel="noopener noreferrer"
            className="text-pink-500 hover:text-pink-600 underline"
          >
            {children}
          </a>
        ),
        // Style code blocks
        code: ({ className, children, ...props }) => {
          const isInline = !className;
          if (isInline) {
            return (
              <code className="bg-gray-100 dark:bg-gray-800 px-1.5 py-0.5 rounded text-sm font-mono" {...props}>
                {children}
              </code>
            );
          }
          return (
            <code className={cn("block bg-gray-100 dark:bg-gray-800 p-3 rounded-lg text-sm font-mono overflow-x-auto", className)} {...props}>
              {children}
            </code>
          );
        },
        // Style pre blocks
        pre: ({ children }) => (
          <pre className="bg-gray-100 dark:bg-gray-800 rounded-lg overflow-x-auto my-2">
            {children}
          </pre>
        ),
        // Style lists - use standard browser list styling (matching marked.parse output)
        ul: ({ children }) => (
          <ul className="list-disc ml-6 my-2 space-y-0.5 text-gray-700 dark:text-gray-300">
            {children}
          </ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal ml-6 my-2 space-y-0.5 text-gray-700 dark:text-gray-300">
            {children}
          </ol>
        ),
        li: ({ children }) => (
          <li className="pl-1">
            {children}
          </li>
        ),
        // Style headings
        h1: ({ children }) => <h1 className="text-xl font-bold mt-4 mb-2 text-gray-900 dark:text-gray-100">{children}</h1>,
        h2: ({ children }) => <h2 className="text-lg font-bold mt-3 mb-2 text-gray-900 dark:text-gray-100">{children}</h2>,
        h3: ({ children }) => <h3 className="text-base font-bold mt-2 mb-1 text-gray-900 dark:text-gray-100">{children}</h3>,
        // Style strong/bold
        strong: ({ children }) => <strong className="font-semibold text-gray-900 dark:text-gray-100">{children}</strong>,
        // Style paragraphs
        p: ({ children }) => <p className="my-2">{children}</p>,
        // Style blockquotes
        blockquote: ({ children }) => (
          <blockquote className="border-l-4 border-pink-300 dark:border-pink-700 pl-4 my-2 italic text-gray-600 dark:text-gray-400">
            {children}
          </blockquote>
        ),
        // Style tables
        table: ({ children }) => (
          <div className="overflow-x-auto my-2">
            <table className="min-w-full border-collapse border border-gray-200 dark:border-gray-700">
              {children}
            </table>
          </div>
        ),
        th: ({ children }) => (
          <th className="border border-gray-200 dark:border-gray-700 px-3 py-2 bg-gray-50 dark:bg-gray-800 font-semibold text-left">
            {children}
          </th>
        ),
        td: ({ children }) => (
          <td className="border border-gray-200 dark:border-gray-700 px-3 py-2">
            {children}
          </td>
        ),
      }}
    >
      {content}
    </ReactMarkdown>
  );
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className={cn(
        'absolute top-2 right-2 p-1.5 rounded',
        'opacity-0 group-hover:opacity-100 transition-opacity',
        'text-gray-400 hover:text-gray-600 dark:hover:text-gray-300',
        'bg-white/80 dark:bg-gray-800/80'
      )}
      title="Copy message"
    >
      {copied ? <Check className="w-4 h-4 text-green-500" /> : <Copy className="w-4 h-4" />}
    </button>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === 'user';

  return (
    <div
      className={cn(
        'flex gap-3 p-4 group relative',
        isUser ? 'bg-gray-50 dark:bg-gray-800/50' : 'bg-white dark:bg-gray-900'
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          'flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center',
          isUser
            ? 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
            : 'bg-pink-100 dark:bg-pink-900/30 text-pink-600 dark:text-pink-400'
        )}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Content */}
      <div className="flex-1 min-w-0 overflow-hidden">
        <div className="flex items-center gap-2 mb-1">
          <span className="font-medium text-sm text-gray-900 dark:text-gray-100">
            {isUser ? 'You' : 'Auspex'}
          </span>
          <span className="text-xs text-gray-400">
            {message.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
          {message.isStreaming && (
            <span className="flex items-center gap-1 text-xs text-pink-500">
              <Loader2 className="w-3 h-3 animate-spin" />
              Typing...
            </span>
          )}
        </div>
        <div className="text-gray-700 dark:text-gray-300 text-sm leading-relaxed">
          {message.content ? (
            <MessageContent content={message.content} />
          ) : message.isStreaming ? (
            <span className="text-gray-400">...</span>
          ) : null}
        </div>
      </div>

      {/* Copy button for assistant messages */}
      {!isUser && message.content && <CopyButton text={message.content} />}
    </div>
  );
}

function WelcomeMessage() {
  return (
    <div className="flex gap-3 p-4">
      <div className="flex-shrink-0 w-8 h-8 rounded-full bg-pink-100 dark:bg-pink-900/30 flex items-center justify-center text-pink-600 dark:text-pink-400">
        <Bot className="w-4 h-4" />
      </div>
      <div className="flex-1">
        <div className="font-medium text-sm text-gray-900 dark:text-gray-100 mb-1">
          Auspex
        </div>
        <div className="text-gray-700 dark:text-gray-300 text-sm">
          <strong>Welcome to Auspex!</strong>
          <br />
          I'm your AI research assistant. Select a topic and model above, then ask me anything about your data.
        </div>
      </div>
    </div>
  );
}

export function AuspexChatMessages({ messages, isLoading }: AuspexChatMessagesProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Check if the last message is still streaming
  const isStreaming = messages.length > 0 && messages[messages.length - 1].isStreaming;

  // Auto-scroll to bottom when messages change or content updates during streaming
  useEffect(() => {
    // Use smooth scrolling to the bottom anchor
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, isStreaming]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto"
    >
      {messages.length === 0 && !isLoading ? (
        <WelcomeMessage />
      ) : (
        <div className="divide-y divide-gray-100 dark:divide-gray-800">
          {messages.map((message) => (
            <MessageBubble key={message.id} message={message} />
          ))}
        </div>
      )}

      {/* Loading indicator - shows at bottom when waiting for response */}
      {isLoading && !isStreaming && (
        <div className="flex items-center gap-3 p-4 bg-white dark:bg-gray-900">
          <div className="flex-shrink-0 w-8 h-8 rounded-full bg-pink-100 dark:bg-pink-900/30 flex items-center justify-center">
            <Loader2 className="w-4 h-4 animate-spin text-pink-600 dark:text-pink-400" />
          </div>
          <div className="text-sm text-gray-500 dark:text-gray-400">
            Auspex is thinking...
          </div>
        </div>
      )}

      {/* Scroll anchor at bottom */}
      <div ref={bottomRef} />
    </div>
  );
}
