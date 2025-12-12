/**
 * Hook for polling active job status
 */
import { useState, useEffect, useCallback, useRef } from 'react';
import {
  getActiveJobsStatus,
  ActiveJob,
  ActiveJobsStatus,
} from '../services/gatherApi';

interface UseJobStatusOptions {
  pollInterval?: number; // ms, default 3000
  enabled?: boolean;
}

interface UseJobStatusReturn {
  activeJobs: ActiveJob[];
  totalActive: number;
  isPolling: boolean;
  lastUpdated: Date | null;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useJobStatus(options: UseJobStatusOptions = {}): UseJobStatusReturn {
  const { pollInterval = 3000, enabled = true } = options;

  const [activeJobs, setActiveJobs] = useState<ActiveJob[]>([]);
  const [totalActive, setTotalActive] = useState(0);
  const [isPolling, setIsPolling] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);

  const intervalRef = useRef<NodeJS.Timeout | null>(null);

  const fetchStatus = useCallback(async () => {
    try {
      const result: ActiveJobsStatus = await getActiveJobsStatus();
      if (result.success) {
        setActiveJobs(result.active_jobs || []);
        setTotalActive(result.total_active || 0);
        setLastUpdated(new Date());
        setError(null);
      }
    } catch (err) {
      console.error('Error fetching job status:', err);
      setError(err instanceof Error ? err.message : 'Failed to fetch job status');
    }
  }, []);

  // Start/stop polling based on enabled flag
  useEffect(() => {
    if (!enabled) {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      setIsPolling(false);
      return;
    }

    // Initial fetch
    fetchStatus();
    setIsPolling(true);

    // Set up polling interval
    intervalRef.current = setInterval(fetchStatus, pollInterval);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      setIsPolling(false);
    };
  }, [enabled, pollInterval, fetchStatus]);

  return {
    activeJobs,
    totalActive,
    isPolling,
    lastUpdated,
    error,
    refresh: fetchStatus,
  };
}
