/**
 * Emerging Topics Schedule Modal - Configure Scheduled Detection
 */

import { useState, useEffect } from 'react';
import {
  Clock,
  Save,
  Play,
  Loader2,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Label } from '../ui/label';
import { Input } from '../ui/input';
import { Switch } from '../ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

interface ScheduleSettings {
  schedule_enabled: boolean;
  check_interval: number;
  interval_unit: string;
  min_articles: number;
}

interface ScheduleStatus {
  last_check_time: string | null;
  next_check_time: string | null;
  topics_detected: number;
  articles_analyzed: number;
  is_running: boolean;
  last_error: string | null;
}

interface EmergingTopicsScheduleModalProps {
  open: boolean;
  onClose: () => void;
}

export function EmergingTopicsScheduleModal({
  open,
  onClose,
}: EmergingTopicsScheduleModalProps) {
  const [scheduleSettings, setScheduleSettings] = useState<ScheduleSettings>({
    schedule_enabled: false,
    check_interval: 24,
    interval_unit: 'hours',
    min_articles: 50,
  });
  const [scheduleStatus, setScheduleStatus] = useState<ScheduleStatus | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [runningNow, setRunningNow] = useState(false);

  useEffect(() => {
    if (open) {
      loadScheduleData();
    }
  }, [open]);

  const loadScheduleData = async () => {
    try {
      const response = await fetch('/api/emerging-topics/schedule/status');
      if (response.ok) {
        const data = await response.json();
        if (data.settings) {
          setScheduleSettings({
            schedule_enabled: data.settings.schedule_enabled || false,
            check_interval: data.settings.check_interval || 24,
            interval_unit: data.settings.interval_unit || 'hours',
            min_articles: data.settings.min_articles || 50,
          });
        }
        if (data.status) {
          setScheduleStatus(data.status);
        }
      }
    } catch (e) {
      console.error('Failed to load schedule data', e);
    }
  };

  const handleSaveSchedule = async () => {
    setScheduleLoading(true);
    try {
      const response = await fetch('/api/emerging-topics/schedule/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(scheduleSettings),
      });
      if (response.ok) {
        await loadScheduleData();
      }
    } catch (e) {
      console.error('Failed to save schedule', e);
    } finally {
      setScheduleLoading(false);
    }
  };

  const handleRunNow = async () => {
    setRunningNow(true);
    try {
      const response = await fetch('/api/emerging-topics/schedule/run-now', {
        method: 'POST',
      });
      if (response.ok) {
        const result = await response.json();
        await loadScheduleData();
        alert(`Detection complete: ${result.topics_detected} topics found`);
      }
    } catch (e) {
      console.error('Failed to run detection', e);
    } finally {
      setRunningNow(false);
    }
  };

  const formatDateTime = (isoString: string | null) => {
    if (!isoString) return 'Never';
    try {
      return new Date(isoString).toLocaleString();
    } catch {
      return isoString;
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-auto min-w-[450px] max-w-[500px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Clock className="w-5 h-5" />
            Scheduled Detection
          </DialogTitle>
          <DialogDescription>
            Configure automatic emerging topics detection
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {/* Enable Toggle */}
          <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div>
              <Label className="font-medium">Automatic Detection</Label>
              <p className="text-xs text-gray-700 dark:text-gray-300 mt-1">
                Run detection on a schedule
              </p>
            </div>
            <Switch
              checked={scheduleSettings.schedule_enabled}
              onCheckedChange={(checked) =>
                setScheduleSettings(prev => ({ ...prev, schedule_enabled: checked }))
              }
            />
          </div>

          {/* Interval */}
          <div className="space-y-3">
            <Label className="font-medium">Run Every</Label>
            <div className="flex gap-2">
              <Input
                type="number"
                min={1}
                max={168}
                value={scheduleSettings.check_interval}
                onChange={(e) =>
                  setScheduleSettings(prev => ({
                    ...prev,
                    check_interval: parseInt(e.target.value) || 1,
                  }))
                }
                className="w-20"
              />
              <Select
                value={scheduleSettings.interval_unit}
                onValueChange={(v) =>
                  setScheduleSettings(prev => ({ ...prev, interval_unit: v }))
                }
              >
                <SelectTrigger className="w-28">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="hours">hours</SelectItem>
                  <SelectItem value="days">days</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          {/* Status */}
          {scheduleStatus && (
            <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-4 space-y-2">
              <h4 className="font-medium text-blue-900 dark:text-blue-100 flex items-center gap-2">
                {scheduleStatus.is_running ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Running...
                  </>
                ) : (
                  <>
                    <Clock className="w-4 h-4" />
                    Status
                  </>
                )}
              </h4>
              <div className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
                <p>Last run: {formatDateTime(scheduleStatus.last_check_time)}</p>
                <p>Next run: {formatDateTime(scheduleStatus.next_check_time)}</p>
                {scheduleStatus.topics_detected > 0 && (
                  <p>Last result: {scheduleStatus.topics_detected} topics detected</p>
                )}
              </div>
              {scheduleStatus.last_error && (
                <div className="text-xs text-red-600 dark:text-red-400 mt-2">
                  Error: {scheduleStatus.last_error}
                </div>
              )}
            </div>
          )}
        </div>

        <DialogFooter className="flex items-center justify-between gap-2">
          <Button
            variant="outline"
            onClick={handleRunNow}
            disabled={runningNow}
            size="sm"
          >
            {runningNow ? (
              <Loader2 className="w-4 h-4 mr-1 animate-spin" />
            ) : (
              <Play className="w-4 h-4 mr-1" />
            )}
            Run Now
          </Button>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button
              onClick={handleSaveSchedule}
              disabled={scheduleLoading}
            >
              {scheduleLoading ? (
                <Loader2 className="w-4 h-4 mr-1 animate-spin" />
              ) : (
                <Save className="w-4 h-4 mr-1" />
              )}
              Save
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
