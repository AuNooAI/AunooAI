/**
 * AuspexChatButton - Floating button to open the Auspex chat modal
 */

import { Bot } from 'lucide-react';
import { cn } from '../ui/utils';

interface AuspexChatButtonProps {
  onClick: () => void;
  className?: string;
}

export function AuspexChatButton({ onClick, className }: AuspexChatButtonProps) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'fixed bottom-6 right-6 z-50',
        'w-14 h-14 rounded-full',
        'bg-pink-500 hover:bg-pink-600',
        'text-white shadow-lg',
        'flex items-center justify-center',
        'transition-all duration-200',
        'hover:scale-110 hover:shadow-xl',
        'focus:outline-none focus:ring-2 focus:ring-pink-400 focus:ring-offset-2',
        'dark:bg-pink-600 dark:hover:bg-pink-500',
        className
      )}
      title="Open Auspex AI Assistant"
      aria-label="Open Auspex AI Assistant"
    >
      <Bot className="w-6 h-6" />
    </button>
  );
}
