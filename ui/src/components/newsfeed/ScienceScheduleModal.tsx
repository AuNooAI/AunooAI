/**
 * ScienceWatch Schedule Modal - Configure Scheduled LLM Classification
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Clock,
  Save,
  Play,
  Loader2,
  Beaker,
  Trash2,
  Plus,
  Bell,
  BellOff,
  AlertCircle,
  X,
} from 'lucide-react';
import {
  getSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  runScheduleNow,
  type ScienceSchedule,
} from '../../services/scienceFundingApi';

interface ScienceScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
  onScheduleRun?: () => void;
  topic?: string;
}

const INTERVAL_UNITS = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
];

const DAYS_BACK_OPTIONS = [
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
  { value: 365, label: '1 year' },
  { value: 0, label: 'All time' },
];

export function ScienceScheduleModal({
  isOpen,
  onClose,
  onScheduleRun,
  topic,
}: ScienceScheduleModalProps) {
  const [schedules, setSchedules] = useState<ScienceSchedule[]>([]);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const [formData, setFormData] = useState({
    name: '',
    topic: topic || '',
    run_type: 'incremental' as 'incremental' | 'full',
    days_back: 30,
    schedule_enabled: true,
    schedule_type: 'interval' as 'interval' | 'daily',
    schedule_interval: 6,
    schedule_unit: 'hours' as 'minutes' | 'hours' | 'days',
    schedule_time: '09:00',
    notify_on_complete: true,
    notify_threshold: 10,
  });

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const schedulesData = await getSchedules();
      setSchedules(schedulesData);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load schedules');
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = async () => {
    if (!formData.name.trim()) {
      setError('Schedule name is required');
      return;
    }

    setSaving(true);
    setError(null);
    try {
      await createSchedule({
        name: formData.name,
        topic: formData.topic || undefined,
        run_type: formData.run_type,
        days_back: formData.days_back,
        schedule_enabled: formData.schedule_enabled,
        schedule_type: formData.schedule_type,
        schedule_interval: formData.schedule_type === 'interval' ? formData.schedule_interval : undefined,
        schedule_unit: formData.schedule_type === 'interval' ? formData.schedule_unit : undefined,
        schedule_time: formData.schedule_type === 'daily' ? formData.schedule_time : undefined,
        notify_on_complete: formData.notify_on_complete,
        notify_threshold: formData.notify_threshold,
      });
      setShowCreateForm(false);
      resetForm();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create schedule');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdate = async (id: number) => {
    setSaving(true);
    setError(null);
    try {
      await updateSchedule(id, {
        name: formData.name,
        topic: formData.topic || undefined,
        run_type: formData.run_type,
        days_back: formData.days_back,
        schedule_enabled: formData.schedule_enabled,
        schedule_type: formData.schedule_type,
        schedule_interval: formData.schedule_type === 'interval' ? formData.schedule_interval : undefined,
        schedule_unit: formData.schedule_type === 'interval' ? formData.schedule_unit : undefined,
        schedule_time: formData.schedule_type === 'daily' ? formData.schedule_time : undefined,
        notify_on_complete: formData.notify_on_complete,
        notify_threshold: formData.notify_threshold,
      });
      setEditingId(null);
      resetForm();
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update schedule');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this schedule?')) return;

    try {
      await deleteSchedule(id);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete schedule');
    }
  };

  const handleRunNow = async (id: number) => {
    setRunning(id);
    setError(null);
    try {
      await runScheduleNow(id);
      await loadData();
      if (onScheduleRun) onScheduleRun();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to run schedule');
    } finally {
      setRunning(null);
    }
  };

  const handleToggleEnabled = async (schedule: ScienceSchedule) => {
    try {
      await updateSchedule(schedule.id, {
        schedule_enabled: !schedule.schedule_enabled,
      });
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to toggle schedule');
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      topic: topic || '',
      run_type: 'incremental',
      days_back: 30,
      schedule_enabled: true,
      schedule_type: 'interval',
      schedule_interval: 6,
      schedule_unit: 'hours',
      schedule_time: '09:00',
      notify_on_complete: true,
      notify_threshold: 10,
    });
  };

  const startEditing = (schedule: ScienceSchedule) => {
    setEditingId(schedule.id);
    setFormData({
      name: schedule.name,
      topic: schedule.topic || '',
      run_type: (schedule.run_type as 'incremental' | 'full') || 'incremental',
      days_back: schedule.days_back,
      schedule_enabled: schedule.schedule_enabled,
      schedule_type: (schedule.schedule_type as 'interval' | 'daily') || 'interval',
      schedule_interval: schedule.schedule_interval || 6,
      schedule_unit: (schedule.schedule_unit as 'minutes' | 'hours' | 'days') || 'hours',
      schedule_time: schedule.schedule_time || '09:00',
      notify_on_complete: schedule.notify_on_complete,
      notify_threshold: schedule.notify_threshold,
    });
  };

  const formatNextRun = (nextRun: string | null) => {
    if (!nextRun) return 'Not scheduled';
    return new Date(nextRun).toLocaleString();
  };

  const handleClose = useCallback(() => {
    setShowCreateForm(false);
    setEditingId(null);
    resetForm();
    onClose();
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[1100] flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50" onClick={handleClose} />

      <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl max-h-[90vh] overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Clock className="w-5 h-5 text-emerald-500" />
            <h3 className="text-lg font-medium text-gray-900 dark:text-gray-100">
              Scheduled LLM Classification
            </h3>
          </div>
          <button
            onClick={handleClose}
            className="text-gray-500 hover:text-gray-600 dark:hover:text-gray-400"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-4 overflow-y-auto max-h-[70vh]">
          {error && (
            <div className="mb-4 flex items-center gap-2 p-3 bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded-lg text-sm">
              <AlertCircle className="w-4 h-4 flex-shrink-0" />
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-emerald-500" />
            </div>
          ) : (
            <>
              {/* Schedules List */}
              <div className="space-y-3 mb-4">
                {schedules.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                    <Beaker className="w-12 h-12 mx-auto mb-3 opacity-50" />
                    <p>No schedules configured yet.</p>
                    <p className="text-sm">Create a schedule to automatically classify articles with LLM.</p>
                  </div>
                ) : (
                  schedules.map((schedule) => (
                    <div
                      key={schedule.id}
                      className={`p-4 rounded-lg border ${
                        schedule.schedule_enabled
                          ? 'bg-emerald-50 dark:bg-emerald-900/10 border-emerald-200 dark:border-emerald-800'
                          : 'bg-gray-50 dark:bg-gray-900/50 border-gray-200 dark:border-gray-700'
                      }`}
                    >
                      {editingId === schedule.id ? (
                        <div className="space-y-3">
                          <ScheduleForm formData={formData} setFormData={setFormData} />
                          <div className="flex justify-end gap-2">
                            <button
                              onClick={() => { setEditingId(null); resetForm(); }}
                              className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleUpdate(schedule.id)}
                              disabled={saving}
                              className="flex items-center gap-2 px-3 py-1.5 text-sm bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 disabled:opacity-50"
                            >
                              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                              Save
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div>
                          <div className="flex items-start justify-between">
                            <div>
                              <h4 className="font-medium text-gray-900 dark:text-gray-100 flex items-center gap-2">
                                {schedule.name}
                                {schedule.notify_on_complete ? (
                                  <Bell className="w-4 h-4 text-emerald-500" />
                                ) : (
                                  <BellOff className="w-4 h-4 text-gray-400" />
                                )}
                              </h4>
                              <p className="text-sm text-gray-500 dark:text-gray-400">
                                {schedule.run_type} &bull; {schedule.days_back === 0 ? 'All time' : `${schedule.days_back} days`}
                              </p>
                            </div>
                            <button
                              onClick={() => handleToggleEnabled(schedule)}
                              className={`px-2 py-1 text-xs rounded-full ${
                                schedule.schedule_enabled
                                  ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                                  : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                              }`}
                            >
                              {schedule.schedule_enabled ? 'Enabled' : 'Disabled'}
                            </button>
                          </div>

                          <div className="mt-2 grid grid-cols-2 gap-2 text-xs text-gray-500 dark:text-gray-400">
                            <div>
                              <span className="font-medium">Schedule:</span>{' '}
                              {schedule.schedule_type === 'daily'
                                ? `Daily at ${schedule.schedule_time}`
                                : `Every ${schedule.schedule_interval} ${schedule.schedule_unit}`}
                            </div>
                            <div>
                              <span className="font-medium">Next run:</span>{' '}
                              {formatNextRun(schedule.next_run_at)}
                            </div>
                            <div>
                              <span className="font-medium">Total runs:</span> {schedule.run_count}
                            </div>
                            <div>
                              <span className="font-medium">Last status:</span>{' '}
                              {schedule.last_run_status ? (
                                <span className={schedule.last_run_status === 'success' ? 'text-green-600' : 'text-red-500'}>
                                  {schedule.last_run_status}
                                </span>
                              ) : (
                                'Never run'
                              )}
                            </div>
                          </div>

                          {schedule.last_run_at && (
                            <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                              Last run: {new Date(schedule.last_run_at).toLocaleString()} -
                              Processed {schedule.last_run_articles_processed},
                              Categorized {schedule.last_run_articles_categorized}
                            </div>
                          )}

                          <div className="flex justify-end gap-2 mt-3">
                            <button
                              onClick={() => handleDelete(schedule.id)}
                              className="p-1.5 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                              title="Delete schedule"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                            <button
                              onClick={() => startEditing(schedule)}
                              className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleRunNow(schedule.id)}
                              disabled={running === schedule.id}
                              className="flex items-center gap-1 px-3 py-1.5 text-sm bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 disabled:opacity-50"
                            >
                              {running === schedule.id ? (
                                <Loader2 className="w-4 h-4 animate-spin" />
                              ) : (
                                <Play className="w-4 h-4" />
                              )}
                              Run Now
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </div>

              {/* Create New Schedule Form */}
              {showCreateForm ? (
                <div className="p-4 rounded-lg border border-emerald-200 dark:border-emerald-800 bg-emerald-50/50 dark:bg-emerald-900/10">
                  <h4 className="font-medium text-gray-900 dark:text-gray-100 mb-3">New Schedule</h4>
                  <div className="space-y-3">
                    <ScheduleForm formData={formData} setFormData={setFormData} />
                    <div className="flex justify-end gap-2">
                      <button
                        onClick={() => { setShowCreateForm(false); resetForm(); }}
                        className="px-3 py-1.5 text-sm text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={handleCreate}
                        disabled={saving}
                        className="flex items-center gap-2 px-3 py-1.5 text-sm bg-emerald-500 text-white rounded-lg hover:bg-emerald-600 disabled:opacity-50"
                      >
                        {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                        Create Schedule
                      </button>
                    </div>
                  </div>
                </div>
              ) : (
                <button
                  onClick={() => setShowCreateForm(true)}
                  className="w-full flex items-center justify-center gap-2 p-3 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg text-gray-500 dark:text-gray-400 hover:border-emerald-400 hover:text-emerald-500 transition-colors"
                >
                  <Plus className="w-5 h-5" />
                  Create New Schedule
                </button>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end p-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={handleClose}
            className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-lg hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function ScheduleForm({
  formData,
  setFormData,
}: {
  formData: any;
  setFormData: (data: any) => void;
}) {
  return (
    <div className="space-y-3">
      {/* Name */}
      <div>
        <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Name</label>
        <input
          type="text"
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          placeholder="e.g., Daily Science Classification"
          className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* Run Type */}
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Run Type</label>
          <select
            value={formData.run_type}
            onChange={(e) => setFormData({ ...formData, run_type: e.target.value })}
            className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="incremental">Incremental (new only)</option>
            <option value="full">Full (reclassify all)</option>
          </select>
        </div>

        {/* Days Back */}
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Look Back</label>
          <select
            value={formData.days_back}
            onChange={(e) => setFormData({ ...formData, days_back: Number(e.target.value) })}
            className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            {DAYS_BACK_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {/* Schedule Type */}
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Schedule Type</label>
          <select
            value={formData.schedule_type}
            onChange={(e) => setFormData({ ...formData, schedule_type: e.target.value })}
            className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
          >
            <option value="interval">Interval</option>
            <option value="daily">Daily at specific time</option>
          </select>
        </div>

        {/* Notify Threshold */}
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Notify Threshold</label>
          <input
            type="number"
            value={formData.notify_threshold}
            onChange={(e) => setFormData({ ...formData, notify_threshold: Number(e.target.value) })}
            min={1}
            className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>
      </div>

      {/* Schedule Details */}
      {formData.schedule_type === 'interval' ? (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Every</label>
            <input
              type="number"
              value={formData.schedule_interval}
              onChange={(e) => setFormData({ ...formData, schedule_interval: Number(e.target.value) })}
              min={1}
              className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Unit</label>
            <select
              value={formData.schedule_unit}
              onChange={(e) => setFormData({ ...formData, schedule_unit: e.target.value })}
              className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
            >
              {INTERVAL_UNITS.map((unit) => (
                <option key={unit.value} value={unit.value}>{unit.label}</option>
              ))}
            </select>
          </div>
        </div>
      ) : (
        <div>
          <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Time</label>
          <input
            type="time"
            value={formData.schedule_time}
            onChange={(e) => setFormData({ ...formData, schedule_time: e.target.value })}
            className="w-full px-3 py-1.5 text-sm bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-emerald-500"
          />
        </div>
      )}

      {/* Options */}
      <div className="flex items-center gap-4">
        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={formData.notify_on_complete}
            onChange={(e) => setFormData({ ...formData, notify_on_complete: e.target.checked })}
            className="w-4 h-4 text-emerald-500 border-gray-300 rounded focus:ring-emerald-500"
          />
          <span className="text-sm text-gray-600 dark:text-gray-300">Send notification</span>
        </label>
      </div>
    </div>
  );
}
