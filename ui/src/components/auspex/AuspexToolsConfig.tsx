/**
 * AuspexToolsConfig - Modal for configuring enabled/disabled tools
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogFooter
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Switch } from '../ui/switch';
import { Label } from '../ui/label';
import { Database, BarChart3, Wrench, Check, X, RotateCcw } from 'lucide-react';
import { cn } from '../ui/utils';

interface ToolsConfig {
  [key: string]: boolean;
}

interface ToolDefinition {
  id: string;
  label: string;
  description: string;
  category: 'database' | 'analysis';
}

const TOOL_DEFINITIONS: ToolDefinition[] = [
  // Database Tools
  {
    id: 'toolGetTopicArticles',
    label: 'Get Topic Articles',
    description: 'Retrieve articles from database for specific topics with date filtering.',
    category: 'database'
  },
  {
    id: 'toolSemanticSearch',
    label: 'Semantic Search & Analysis',
    description: 'Perform comprehensive semantic search with diversity filtering and structured analysis.',
    category: 'database'
  },
  {
    id: 'toolKeywordSearch',
    label: 'Keyword Search',
    description: 'Search articles by specific keywords with topic filtering.',
    category: 'database'
  },
  {
    id: 'toolFollowUp',
    label: 'Follow-up Query',
    description: 'Conduct follow-up searches based on previous results for deeper investigation.',
    category: 'database'
  },
  // Analysis Tools
  {
    id: 'toolSentimentTrends',
    label: 'Sentiment Trends Analysis',
    description: 'Analyze sentiment patterns and trends over time with statistical breakdowns.',
    category: 'analysis'
  },
  {
    id: 'toolCategoryAnalysis',
    label: 'Category Analysis',
    description: 'Get article categories and their distribution with percentage breakdowns.',
    category: 'analysis'
  },
  {
    id: 'toolNewsSearch',
    label: 'Real-time News Search',
    description: 'Search for current news articles using external APIs for latest information.',
    category: 'analysis'
  }
];

interface AuspexToolsConfigProps {
  isOpen: boolean;
  onClose: () => void;
  config: ToolsConfig;
  onSave: (config: ToolsConfig) => void;
}

export function AuspexToolsConfig({
  isOpen,
  onClose,
  config,
  onSave
}: AuspexToolsConfigProps) {
  // Local state for editing
  const [localConfig, setLocalConfig] = useState<ToolsConfig>({ ...config });

  // Reset local config when dialog opens
  useEffect(() => {
    if (isOpen) {
      setLocalConfig({ ...config });
    }
  }, [isOpen, config]);

  const handleToggle = (toolId: string) => {
    setLocalConfig(prev => ({
      ...prev,
      [toolId]: !prev[toolId]
    }));
  };

  const handleEnableAll = () => {
    const newConfig: ToolsConfig = {};
    TOOL_DEFINITIONS.forEach(tool => {
      newConfig[tool.id] = true;
    });
    setLocalConfig(newConfig);
  };

  const handleDisableAll = () => {
    const newConfig: ToolsConfig = {};
    TOOL_DEFINITIONS.forEach(tool => {
      newConfig[tool.id] = false;
    });
    setLocalConfig(newConfig);
  };

  const handleReset = () => {
    const newConfig: ToolsConfig = {};
    TOOL_DEFINITIONS.forEach(tool => {
      newConfig[tool.id] = true;
    });
    setLocalConfig(newConfig);
  };

  const handleSave = () => {
    onSave(localConfig);
    onClose();
  };

  const databaseTools = TOOL_DEFINITIONS.filter(t => t.category === 'database');
  const analysisTools = TOOL_DEFINITIONS.filter(t => t.category === 'analysis');

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Wrench className="w-5 h-5 text-pink-500" />
            Auspex Tools Configuration
          </DialogTitle>
          <DialogDescription>
            Enable or disable individual tools for Auspex. Each tool provides specific capabilities for data analysis and retrieval.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 py-4">
          {/* Database Tools */}
          <div>
            <h4 className="flex items-center gap-2 text-sm font-semibold text-pink-600 dark:text-pink-400 mb-3">
              <Database className="w-4 h-4" />
              Database Tools
            </h4>
            <div className="space-y-3">
              {databaseTools.map(tool => (
                <ToolToggle
                  key={tool.id}
                  tool={tool}
                  enabled={localConfig[tool.id] !== false}
                  onToggle={() => handleToggle(tool.id)}
                />
              ))}
            </div>
          </div>

          {/* Analysis Tools */}
          <div>
            <h4 className="flex items-center gap-2 text-sm font-semibold text-pink-600 dark:text-pink-400 mb-3">
              <BarChart3 className="w-4 h-4" />
              Analysis Tools
            </h4>
            <div className="space-y-3">
              {analysisTools.map(tool => (
                <ToolToggle
                  key={tool.id}
                  tool={tool}
                  enabled={localConfig[tool.id] !== false}
                  onToggle={() => handleToggle(tool.id)}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Global Controls */}
        <div className="border-t border-gray-200 dark:border-gray-700 pt-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={handleEnableAll}
                className="text-green-600 hover:text-green-700"
              >
                <Check className="w-4 h-4 mr-1" />
                Enable All
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleDisableAll}
                className="text-red-600 hover:text-red-700"
              >
                <X className="w-4 h-4 mr-1" />
                Disable All
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleReset}
              >
                <RotateCcw className="w-4 h-4 mr-1" />
                Reset
              </Button>
            </div>
            <p className="text-xs text-gray-400">
              Tools can be toggled during conversations
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSave} className="bg-pink-500 hover:bg-pink-600">
            Save Configuration
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Need to import useState and useEffect
import { useState, useEffect } from 'react';

function ToolToggle({
  tool,
  enabled,
  onToggle
}: {
  tool: ToolDefinition;
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-800">
      <Switch
        checked={enabled}
        onCheckedChange={onToggle}
      />
      <div className="flex-1 min-w-0">
        <Label className="text-sm font-medium text-gray-900 dark:text-gray-100 cursor-pointer" onClick={onToggle}>
          {tool.label}
        </Label>
        <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">
          {tool.description}
        </p>
      </div>
    </div>
  );
}
