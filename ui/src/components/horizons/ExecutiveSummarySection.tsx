/**
 * ExecutiveSummarySection Component
 * Container component for Future Horizons executive summaries
 */

import React from 'react';
import { Button } from '@/components/ui/button';
import { Loader2, FileText, RefreshCw } from 'lucide-react';
import { TopicExecutiveSummary } from '@/types/horizonsExecutiveSummary';
import ExecutiveSummaryCard from './ExecutiveSummaryCard';
import './executive-summary.css';

interface ExecutiveSummarySectionProps {
  summaries: TopicExecutiveSummary[] | null;
  isLoading: boolean;
  onGenerate: () => void;
  onRegenerate?: () => void;
  error?: string | null;
  generatedAt?: string | null;
  researchTopic?: string;
}

const ExecutiveSummarySection: React.FC<ExecutiveSummarySectionProps> = ({
  summaries,
  isLoading,
  onGenerate,
  onRegenerate,
  error,
  generatedAt,
  researchTopic,
}) => {
  const hasSummaries = summaries && summaries.length > 0;

  return (
    <div
      className="executive-summary-section space-y-6"
      id="horizons-executive-summary"
      data-testid="executive-summary-section"
    >
      {/* Section Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <FileText className="w-5 h-5 text-muted-foreground" />
          <h3 className="text-lg font-semibold tracking-tight">
            Executive Summary
          </h3>
          {generatedAt && (
            <span className="text-xs text-muted-foreground">
              Generated {new Date(generatedAt).toLocaleString()}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {hasSummaries && onRegenerate && (
            <Button
              variant="outline"
              size="sm"
              onClick={onRegenerate}
              disabled={isLoading}
              className="gap-2"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              Regenerate
            </Button>
          )}
          {!hasSummaries && !isLoading && (
            <Button
              variant="default"
              size="sm"
              onClick={onGenerate}
              className="gap-2"
            >
              <FileText className="w-4 h-4" />
              Generate Executive Summary
            </Button>
          )}
        </div>
      </div>

      {/* Error State */}
      {error && (
        <div className="bg-destructive/10 text-destructive border border-destructive/20 rounded-lg p-4 text-sm">
          <p className="font-medium mb-1">Failed to generate executive summary</p>
          <p className="text-destructive/80">{error}</p>
          <Button
            variant="outline"
            size="sm"
            onClick={onGenerate}
            className="mt-3"
          >
            Try Again
          </Button>
        </div>
      )}

      {/* Loading State */}
      {isLoading && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <Loader2 className="w-8 h-8 animate-spin text-primary mb-4" />
          <p className="text-sm text-muted-foreground">
            Generating horizon-anchored executive summary...
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            Analyzing scenarios and identifying decision forks
          </p>
        </div>
      )}

      {/* Empty State (no summaries, not loading) */}
      {!hasSummaries && !isLoading && !error && (
        <div className="flex flex-col items-center justify-center py-12 border border-dashed border-border rounded-lg bg-muted/20">
          <FileText className="w-12 h-12 text-muted-foreground/50 mb-4" />
          <p className="text-sm text-muted-foreground mb-2">
            No executive summary generated yet
          </p>
          <p className="text-xs text-muted-foreground mb-4 max-w-md text-center">
            Generate an executive summary to see horizon-anchored insights with counter-signals and decision forks for strategic planning.
          </p>
          <Button
            variant="default"
            onClick={onGenerate}
            className="gap-2"
          >
            <FileText className="w-4 h-4" />
            Generate Executive Summary
          </Button>
        </div>
      )}

      {/* Summaries Grid */}
      {hasSummaries && !isLoading && (
        <div className="executive-summary-grid grid gap-6 md:grid-cols-2">
          {summaries.map((summary, index) => (
            <ExecutiveSummaryCard
              key={`${summary.topic_title}-${index}`}
              summary={summary}
              index={index}
              researchTopic={researchTopic}
            />
          ))}
        </div>
      )}

      {/* Horizon Legend */}
      {hasSummaries && !isLoading && (
        <div className="flex flex-wrap items-center justify-center gap-4 pt-4 border-t border-border text-xs text-muted-foreground">
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-blue-600" />
            <span>H1 Declining System</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-purple-600" />
            <span>H2 Transition/Innovation</span>
          </div>
          <div className="flex items-center gap-1.5">
            <div className="w-3 h-3 rounded bg-green-600" />
            <span>H3 Future Vision</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default ExecutiveSummarySection;
