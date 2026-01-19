/**
 * Run Agent Modal
 * Modal for selecting timeframe and options when running research agents
 */

import { useState } from 'react';
import { Play, Loader2, Calendar, Tag, FileText } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Checkbox } from '../ui/checkbox';

export interface RunAgentOptions {
  daysBack: number;
  tagArticles: boolean;
  generateUnifiedReport?: boolean;
}

interface RunAgentModalProps {
  open: boolean;
  onClose: () => void;
  onRun: (options: RunAgentOptions) => Promise<void>;
  agentName?: string;
  isRunningAll?: boolean;
  loading?: boolean;
}

const TIMEFRAME_OPTIONS = [
  { value: 1, label: 'Last 24 hours', description: 'Most recent articles only' },
  { value: 3, label: 'Last 3 days', description: 'Recent news coverage' },
  { value: 7, label: 'Last 7 days', description: 'Past week of articles' },
  { value: 14, label: 'Last 2 weeks', description: 'Extended coverage period' },
  { value: 30, label: 'Last 30 days', description: 'Full month of articles' },
];

export function RunAgentModal({
  open,
  onClose,
  onRun,
  agentName,
  isRunningAll = false,
  loading = false,
}: RunAgentModalProps) {
  const [selectedDays, setSelectedDays] = useState(7);
  const [tagArticles, setTagArticles] = useState(true);
  const [generateUnifiedReport, setGenerateUnifiedReport] = useState(false);
  const [isRunning, setIsRunning] = useState(false);

  const handleRun = async () => {
    setIsRunning(true);
    try {
      await onRun({
        daysBack: selectedDays,
        tagArticles,
        generateUnifiedReport: isRunningAll ? generateUnifiedReport : undefined,
      });
    } finally {
      setIsRunning(false);
    }
  };

  const title = isRunningAll
    ? 'Run All Active Agents'
    : `Run Agent: ${agentName}`;

  const description = isRunningAll
    ? 'Select the time period to analyze. All active agents will search for matches in articles from this period.'
    : 'Select the time period to analyze. The agent will search for matches in articles from this period.';

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="sm:max-w-[400px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-pink-500" />
            {title}
          </DialogTitle>
          <DialogDescription>
            {description}
          </DialogDescription>
        </DialogHeader>

        <div className="py-4">
          <Label className="text-sm font-medium text-gray-700 mb-3 block">
            Time Period
          </Label>
          <div className="space-y-2">
            {TIMEFRAME_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => setSelectedDays(option.value)}
                disabled={loading || isRunning}
                className={`w-full text-left p-3 rounded-lg border transition-all ${
                  selectedDays === option.value
                    ? 'border-pink-500 bg-pink-50 ring-1 ring-pink-500'
                    : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className={`font-medium ${
                    selectedDays === option.value ? 'text-pink-700' : 'text-gray-900'
                  }`}>
                    {option.label}
                  </span>
                  {selectedDays === option.value && (
                    <span className="w-2 h-2 bg-pink-500 rounded-full" />
                  )}
                </div>
                <p className={`text-sm mt-0.5 ${
                  selectedDays === option.value ? 'text-pink-600' : 'text-gray-700 dark:text-gray-300'
                }`}>
                  {option.description}
                </p>
              </button>
            ))}
          </div>
        </div>

        {/* Options */}
        <div className="py-3 border-t space-y-2">
          <label className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50">
            <Checkbox
              checked={tagArticles}
              onCheckedChange={(checked) => setTagArticles(checked as boolean)}
              disabled={loading || isRunning}
            />
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <Tag className="w-4 h-4 text-green-500" />
                <span className="font-medium text-gray-900">Tag matching articles</span>
              </div>
              <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                Add signal tags to matched articles for easy filtering
              </p>
            </div>
          </label>

          {/* Unified Report option - only for Run All */}
          {isRunningAll && (
            <label className="flex items-start gap-3 p-3 rounded-lg border border-gray-200 cursor-pointer hover:bg-gray-50">
              <Checkbox
                checked={generateUnifiedReport}
                onCheckedChange={(checked) => setGenerateUnifiedReport(checked as boolean)}
                disabled={loading || isRunning}
              />
              <div className="flex-1">
                <div className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-blue-500" />
                  <span className="font-medium text-gray-900">Generate unified report</span>
                </div>
                <p className="text-sm text-gray-700 dark:text-gray-300 mt-0.5">
                  Create a combined intelligence report across all agents
                </p>
              </div>
            </label>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button variant="outline" onClick={onClose} disabled={isRunning}>
            Cancel
          </Button>
          <Button
            onClick={handleRun}
            disabled={loading || isRunning}
            className="bg-pink-500 hover:bg-pink-600"
          >
            {isRunning || loading ? (
              <>
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                Running...
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-2" />
                Run {isRunningAll ? 'All Agents' : 'Agent'}
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
