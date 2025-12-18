/**
 * AuspexQuickQueries - Quick query buttons and plugin tools
 */

import { Sparkles } from 'lucide-react';
import { cn } from '../ui/utils';

interface PluginTool {
  name: string;
  description: string;
  category?: string;
}

interface AuspexQuickQueriesProps {
  pluginTools: PluginTool[];
  onToolClick: (tool: PluginTool) => void;
  disabled?: boolean;
}

function formatToolName(name: string): string {
  return name
    .split('_')
    .map(word => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

export function AuspexQuickQueries({
  pluginTools,
  onToolClick,
  disabled = false
}: AuspexQuickQueriesProps) {
  if (pluginTools.length === 0) {
    return null;
  }

  return (
    <div className="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50 px-4 py-3">
      <div className="flex items-center gap-2 mb-2">
        <Sparkles className="w-4 h-4 text-pink-500" />
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          Analysis Tools
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {pluginTools.map((tool) => (
          <button
            key={tool.name}
            onClick={() => onToolClick(tool)}
            disabled={disabled}
            className={cn(
              'px-3 py-1.5 rounded-full text-xs font-medium',
              'bg-white dark:bg-gray-700',
              'border border-gray-200 dark:border-gray-600',
              'text-gray-600 dark:text-gray-300',
              'hover:border-pink-300 hover:text-pink-600 dark:hover:border-pink-700 dark:hover:text-pink-400',
              'hover:bg-pink-50 dark:hover:bg-pink-900/20',
              'transition-colors',
              'disabled:opacity-50 disabled:cursor-not-allowed'
            )}
            title={tool.description}
          >
            {formatToolName(tool.name)}
          </button>
        ))}
      </div>
    </div>
  );
}
