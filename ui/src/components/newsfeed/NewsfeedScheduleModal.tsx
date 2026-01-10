/**
 * Newsfeed Schedule Modal - Configure Scheduled Dashboard Generation
 */

import { useState, useEffect } from 'react';
import {
  Clock,
  Save,
  Play,
  Loader2,
  Newspaper,
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
  schedule_type: 'interval' | 'daily';
  check_interval: number;
  interval_unit: string;
  schedule_time: string;
  generate_briefing: boolean;
  generate_highlights: boolean;
  generate_narratives: boolean;
  persona: string;
}

interface ScheduleStatus {
  last_run_time: string | null;
  next_run_time: string | null;
  last_run_status: string | null;
  last_error: string | null;
  is_running: boolean;
  run_count: number;
}

interface NewsfeedScheduleModalProps {
  open: boolean;
  onClose: () => void;
}

export function NewsfeedScheduleModal({
  open,
  onClose,
}: NewsfeedScheduleModalProps) {
  const [scheduleSettings, setScheduleSettings] = useState<ScheduleSettings>({
    schedule_enabled: false,
    schedule_type: 'interval',
    check_interval: 24,
    interval_unit: 'hours',
    schedule_time: '09:00',
    generate_briefing: true,
    generate_highlights: true,
    generate_narratives: false,
    persona: 'CEO',
  });
  const [scheduleStatus, setScheduleStatus] = useState<ScheduleStatus | null>(null);
  const [scheduleLoading, setScheduleLoading] = useState(false);
  const [runningNow, setRunningNow] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      loadScheduleData();
    }
  }, [open]);

  const loadScheduleData = async () => {
    setLoadError(null);
    try {
      const response = await fetch('/api/news-feed/dashboard/schedule/status', {
        credentials: 'include',
      });
      if (response.ok) {
        const data = await response.json();
        if (data.settings) {
          setScheduleSettings({
            schedule_enabled: data.settings.schedule_enabled || false,
            schedule_type: data.settings.schedule_type || 'interval',
            check_interval: data.settings.check_interval || 24,
            interval_unit: data.settings.interval_unit || 'hours',
            schedule_time: data.settings.schedule_time || '09:00',
            generate_briefing: data.settings.generate_briefing !== false,
            generate_highlights: data.settings.generate_highlights !== false,
            generate_narratives: data.settings.generate_narratives || false,
            persona: data.settings.persona || 'CEO',
          });
        }
        if (data.status) {
          setScheduleStatus(data.status);
        }
      } else if (response.status !== 404) {
        setLoadError('Failed to load schedule settings');
      }
    } catch (e) {
      console.error('Failed to load schedule data', e);
      setLoadError('Failed to connect to server');
    }
  };

  const handleSaveSchedule = async () => {
    setScheduleLoading(true);
    try {
      const response = await fetch('/api/news-feed/dashboard/schedule/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify(scheduleSettings),
      });
      if (response.ok) {
        onClose(); // Close modal on successful save
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to save settings');
      }
    } catch (e) {
      console.error('Failed to save schedule', e);
      alert('Failed to save schedule settings');
    } finally {
      setScheduleLoading(false);
    }
  };

  const handleRunNow = async () => {
    setRunningNow(true);
    try {
      const response = await fetch('/api/news-feed/dashboard/schedule/run-now', {
        method: 'POST',
        credentials: 'include',
      });
      if (response.ok) {
        const result = await response.json();
        await loadScheduleData();
        alert(`Dashboard generation complete!\nBriefing: ${result.briefing_generated ? 'Generated' : 'Skipped'}\nHighlights: ${result.highlights_generated ? 'Generated' : 'Skipped'}`);
      } else {
        const error = await response.json();
        alert(error.detail || 'Failed to run generation');
      }
    } catch (e) {
      console.error('Failed to run generation', e);
      alert('Failed to run dashboard generation');
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
      <DialogContent className="w-auto min-w-[450px] max-w-[550px]">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Clock className="w-5 h-5" />
            Scheduled Dashboard Generation
          </DialogTitle>
          <DialogDescription>
            Configure automatic briefing and highlights generation
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-6 py-4">
          {loadError && (
            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-sm text-red-700">
              {loadError}
            </div>
          )}

          {/* Enable Toggle */}
          <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div>
              <Label className="font-medium">Automatic Generation</Label>
              <p className="text-xs text-gray-500 mt-1">
                Generate dashboard content on a schedule
              </p>
            </div>
            <Switch
              checked={scheduleSettings.schedule_enabled}
              onCheckedChange={(checked) =>
                setScheduleSettings(prev => ({ ...prev, schedule_enabled: checked }))
              }
            />
          </div>

          {/* Schedule Type */}
          <div className="space-y-3">
            <Label className="font-medium">Schedule Type</Label>
            <Select
              value={scheduleSettings.schedule_type}
              onValueChange={(v) =>
                setScheduleSettings(prev => ({ ...prev, schedule_type: v as 'interval' | 'daily' }))
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="interval">Run at Interval</SelectItem>
                <SelectItem value="daily">Run Daily at Specific Time</SelectItem>
              </SelectContent>
            </Select>
          </div>

          {/* Interval Configuration - only show for interval type */}
          {scheduleSettings.schedule_type === 'interval' && (
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
              <p className="text-xs text-gray-500">
                Dashboard will be generated every {scheduleSettings.check_interval} {scheduleSettings.interval_unit}
              </p>
            </div>
          )}

          {/* Daily Time Configuration - only show for daily type */}
          {scheduleSettings.schedule_type === 'daily' && (
            <div className="space-y-3">
              <Label className="font-medium">Run at Time</Label>
              <Input
                type="time"
                value={scheduleSettings.schedule_time}
                onChange={(e) =>
                  setScheduleSettings(prev => ({ ...prev, schedule_time: e.target.value }))
                }
                className="w-40"
              />
              <p className="text-xs text-gray-500">
                Dashboard will be generated daily at {scheduleSettings.schedule_time} (server time)
              </p>
            </div>
          )}

          {/* What to Generate */}
          <div className="space-y-3">
            <Label className="font-medium">Generate</Label>
            <div className="space-y-2">
              <label className="flex items-center gap-3 p-2 hover:bg-gray-50 rounded cursor-pointer">
                <Switch
                  checked={scheduleSettings.generate_briefing}
                  onCheckedChange={(checked) =>
                    setScheduleSettings(prev => ({ ...prev, generate_briefing: checked }))
                  }
                />
                <div>
                  <span className="text-sm font-medium">Executive Briefing</span>
                  <p className="text-xs text-gray-500">Six articles with AI analysis</p>
                </div>
              </label>
              <label className="flex items-center gap-3 p-2 hover:bg-gray-50 rounded cursor-pointer">
                <Switch
                  checked={scheduleSettings.generate_highlights}
                  onCheckedChange={(checked) =>
                    setScheduleSettings(prev => ({ ...prev, generate_highlights: checked }))
                  }
                />
                <div>
                  <span className="text-sm font-medium">Highlights / Incidents</span>
                  <p className="text-xs text-gray-500">Key events and incidents</p>
                </div>
              </label>
              <label className="flex items-center gap-3 p-2 hover:bg-gray-50 rounded cursor-pointer">
                <Switch
                  checked={scheduleSettings.generate_narratives}
                  onCheckedChange={(checked) =>
                    setScheduleSettings(prev => ({ ...prev, generate_narratives: checked }))
                  }
                />
                <div>
                  <span className="text-sm font-medium">Narratives</span>
                  <p className="text-xs text-gray-500">Thematic story threads</p>
                </div>
              </label>
            </div>
          </div>

          {/* Persona */}
          <div className="space-y-3">
            <Label className="font-medium">Briefing Persona</Label>
            <Select
              value={scheduleSettings.persona}
              onValueChange={(v) =>
                setScheduleSettings(prev => ({ ...prev, persona: v }))
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="CEO">CEO - Strategic Overview</SelectItem>
                <SelectItem value="CMO">CMO - Marketing & Brand</SelectItem>
                <SelectItem value="CTO">CTO - Technology & Innovation</SelectItem>
                <SelectItem value="CISO">CISO - Security & Risk</SelectItem>
              </SelectContent>
            </Select>
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
                    <Newspaper className="w-4 h-4" />
                    Status
                  </>
                )}
              </h4>
              <div className="text-sm text-blue-800 dark:text-blue-200 space-y-1">
                <p>Last run: {formatDateTime(scheduleStatus.last_run_time)}</p>
                <p>Next run: {formatDateTime(scheduleStatus.next_run_time)}</p>
                {scheduleStatus.last_run_status && (
                  <p>Last status: <span className={scheduleStatus.last_run_status === 'success' ? 'text-green-600' : 'text-red-600'}>{scheduleStatus.last_run_status}</span></p>
                )}
                {scheduleStatus.run_count > 0 && (
                  <p>Total runs: {scheduleStatus.run_count}</p>
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
