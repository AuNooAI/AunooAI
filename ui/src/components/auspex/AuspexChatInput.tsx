/**
 * AuspexChatInput - Input area for composing messages
 */

import { useState, useRef, useEffect, KeyboardEvent, forwardRef, useImperativeHandle } from 'react';
import { Send, Bookmark, Loader2, Info } from 'lucide-react';
import { cn } from '../ui/utils';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '../ui/tooltip';

interface AuspexChatInputProps {
  onSend: (message: string) => void;
  onSave?: (message: string) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  placeholder?: string;
}

export interface AuspexChatInputHandle {
  insertText: (text: string) => void;
  focus: () => void;
}

export const AuspexChatInput = forwardRef<AuspexChatInputHandle, AuspexChatInputProps>(({
  onSend,
  onSave,
  disabled = false,
  isStreaming = false,
  placeholder = 'Ask Auspex anything...'
}, ref) => {
  const [value, setValue] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Expose methods to parent via ref
  useImperativeHandle(ref, () => ({
    insertText: (text: string) => {
      setValue(text);
      // Focus the textarea after inserting
      setTimeout(() => textareaRef.current?.focus(), 0);
    },
    focus: () => {
      textareaRef.current?.focus();
    }
  }));

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, [value]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (trimmed && !disabled && !isStreaming) {
      onSend(trimmed);
      setValue('');
      // Reset textarea height
      if (textareaRef.current) {
        textareaRef.current.style.height = 'auto';
      }
    }
  };

  const handleSave = () => {
    const trimmed = value.trim();
    if (trimmed && onSave) {
      onSave(trimmed);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Send on Enter (without Shift)
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const isDisabled = disabled || isStreaming;
  const canSend = value.trim().length > 0 && !isDisabled;

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 p-4">
      <div className="flex items-end gap-2">
        {/* Textarea */}
        <div className="flex-1 relative">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isDisabled ? 'Select a topic and model to start...' : placeholder}
            disabled={isDisabled}
            rows={1}
            className={cn(
              'w-full resize-none rounded-lg border px-4 py-3 pr-20',
              'text-sm text-gray-900 dark:text-gray-100',
              'placeholder-gray-400 dark:placeholder-gray-500',
              'bg-gray-50 dark:bg-gray-800',
              'border-gray-200 dark:border-gray-700',
              'focus:outline-none focus:ring-2 focus:ring-pink-500 focus:border-transparent',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'transition-colors'
            )}
            style={{ minHeight: '48px', maxHeight: '200px' }}
          />

          {/* Character count hint */}
          {value.length > 100 && (
            <span className="absolute bottom-2 right-16 text-xs text-gray-400">
              {value.length}
            </span>
          )}
        </div>

        {/* Save button */}
        {onSave && (
          <button
            onClick={handleSave}
            disabled={!value.trim() || isDisabled}
            className={cn(
              'flex-shrink-0 p-3 rounded-lg',
              'text-gray-400 hover:text-pink-500',
              'hover:bg-gray-100 dark:hover:bg-gray-800',
              'disabled:opacity-50 disabled:cursor-not-allowed',
              'transition-colors'
            )}
            title="Save as quick query"
          >
            <Bookmark className="w-5 h-5" />
          </button>
        )}

        {/* Send button */}
        <button
          onClick={handleSend}
          disabled={!canSend}
          className={cn(
            'flex-shrink-0 p-3 rounded-lg',
            'bg-pink-500 text-white',
            'hover:bg-pink-600',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            'transition-colors'
          )}
          title={isStreaming ? 'Generating response...' : 'Send message'}
        >
          {isStreaming ? (
            <Loader2 className="w-5 h-5 animate-spin" />
          ) : (
            <Send className="w-5 h-5" />
          )}
        </button>
      </div>

      {/* Help text */}
      <p className="mt-2 text-xs text-gray-400 flex items-center gap-1.5">
        Press Enter to send, Shift+Enter for new line
        <TooltipProvider delayDuration={200}>
          <Tooltip>
            <TooltipTrigger asChild>
              <Info className="w-3.5 h-3.5 text-gray-500 hover:text-gray-300 cursor-help" />
            </TooltipTrigger>
            <TooltipContent side="top" className="max-w-xs">
              <p className="font-medium mb-1">Query depth auto-detected:</p>
              <p className="text-gray-400">• Quick: "Any news on AI?"</p>
              <p className="text-gray-400">• Standard: "Summarize coverage on climate"</p>
              <p className="text-gray-400">• Deep: "Analyze trends and implications"</p>
            </TooltipContent>
          </Tooltip>
        </TooltipProvider>
      </p>
    </div>
  );
});
