/**
 * Processing Status Badge - Shows active background jobs
 */
import React from 'react';
import { Loader2 } from 'lucide-react';
import { Badge } from '../ui/badge';
import { useJobStatus } from '../../hooks/useJobStatus';

interface ProcessingStatusBadgeProps {
  className?: string;
}

function getJobTypeLabel(jobType: string): string {
  switch (jobType) {
    case 'keyword_monitor_auto_ingest':
      return 'Auto-collecting';
    case 'bulk_processing':
      return 'Processing';
    default:
      return 'Running';
  }
}

export function ProcessingStatusBadge({ className = '' }: ProcessingStatusBadgeProps) {
  const { activeJobs, totalActive } = useJobStatus({
    pollInterval: 3000,
    enabled: true,
  });

  if (totalActive === 0) {
    return null;
  }

  // Get the most recent job for display
  const latestJob = activeJobs[0];

  // Build status message
  let statusMessage: string;
  if (latestJob) {
    const label = getJobTypeLabel(latestJob.job_type);
    if (latestJob.progress > 0) {
      statusMessage = `${label}: ${latestJob.progress}%`;
    } else if (latestJob.article_count && latestJob.article_count > 0) {
      statusMessage = `${label}: ${latestJob.article_count} articles`;
    } else {
      statusMessage = label;
    }
  } else {
    statusMessage = `Processing ${totalActive} job${totalActive > 1 ? 's' : ''}`;
  }

  return (
    <Badge
      variant="default"
      className={`gather-processing-badge ${className}`}
    >
      <Loader2 className="h-3 w-3 animate-spin mr-2" />
      <span>{statusMessage}</span>
      {totalActive > 1 && (
        <span className="ml-1 text-xs opacity-75">({totalActive})</span>
      )}
    </Badge>
  );
}
