/**
 * ThreatScheduleModal Component
 * Modal for managing threat extraction schedules
 */

import { useState, useEffect, useCallback } from 'react';
import { X, Plus, Play, Pause, Trash2, Clock, Calendar, RefreshCw, CheckCircle, Edit2 } from 'lucide-react';
import {
  getSchedules,
  createSchedule,
  updateSchedule,
  deleteSchedule,
  runSchedule,
  type ThreatSchedule,
} from '../../services/threatIntelligenceApi';

interface ThreatScheduleModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export function ThreatScheduleModal({ isOpen, onClose }: ThreatScheduleModalProps) {
  const [schedules, setSchedules] = useState<ThreatSchedule[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [runningId, setRunningId] = useState<number | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    schedule_type: 'interval' as 'interval' | 'daily',
    schedule_interval: 1,
    schedule_unit: 'hours' as 'minutes' | 'hours' | 'days' | 'weeks',
    schedule_time: '00:00',
    batch_size: 50,
    schedule_enabled: true,
  });

  const resetForm = () => {
    setFormData({
      name: '',
      schedule_type: 'interval',
      schedule_interval: 1,
      schedule_unit: 'hours',
      schedule_time: '00:00',
      batch_size: 50,
      schedule_enabled: true,
    });
    setEditingId(null);
    setShowForm(false);
  };

  const fetchSchedules = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getSchedules();
      setSchedules(result);
    } catch (error) {
      console.error('Error fetching schedules:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchSchedules();
    }
  }, [isOpen, fetchSchedules]);

  const handleCreate = async () => {
    try {
      await createSchedule(formData);
      resetForm();
      fetchSchedules();
    } catch (error) {
      console.error('Error creating schedule:', error);
    }
  };

  const handleEdit = (schedule: ThreatSchedule) => {
    setFormData({
      name: schedule.name,
      schedule_type: schedule.schedule_type,
      schedule_interval: schedule.schedule_interval,
      schedule_unit: schedule.schedule_unit,
      schedule_time: schedule.schedule_time || '00:00',
      batch_size: schedule.batch_size,
      schedule_enabled: schedule.schedule_enabled,
    });
    setEditingId(schedule.id);
    setShowForm(true);
  };

  const handleUpdate = async () => {
    if (!editingId) return;
    try {
      await updateSchedule(editingId, formData);
      resetForm();
      fetchSchedules();
    } catch (error) {
      console.error('Error updating schedule:', error);
    }
  };

  const handleToggleActive = async (schedule: ThreatSchedule) => {
    try {
      await updateSchedule(schedule.id, { schedule_enabled: !schedule.schedule_enabled });
      fetchSchedules();
    } catch (error) {
      console.error('Error updating schedule:', error);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('Are you sure you want to delete this schedule?')) return;

    try {
      await deleteSchedule(id);
      fetchSchedules();
    } catch (error) {
      console.error('Error deleting schedule:', error);
    }
  };

  const handleRunNow = async (id: number) => {
    setRunningId(id);
    try {
      await runSchedule(id);
      setTimeout(() => setRunningId(null), 2000);
      fetchSchedules();
    } catch (error) {
      console.error('Error running schedule:', error);
      setRunningId(null);
    }
  };

  const formatSchedule = (schedule: ThreatSchedule) => {
    if (schedule.schedule_type === 'interval') {
      const unit = schedule.schedule_unit || 'hours';
      const interval = schedule.schedule_interval || 1;
      if (interval === 1) {
        return `Every ${unit.slice(0, -1)}`; // "Every hour", "Every minute"
      }
      return `Every ${interval} ${unit}`;
    } else if (schedule.schedule_type === 'daily') {
      return `Daily at ${schedule.schedule_time || '00:00'}`;
    }
    return 'Custom';
  };

  const formatLastRun = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    const date = new Date(dateStr);
    return date.toLocaleString();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white dark:bg-gray-800 rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-red-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              Processing Schedules
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {loading ? (
            <div className="flex items-center justify-center h-32">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
            </div>
          ) : (
            <>
              {/* Schedule List */}
              {schedules.length === 0 && !showForm ? (
                <div className="text-center py-8">
                  <Clock className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
                  <p className="text-gray-500 dark:text-gray-400">No schedules configured</p>
                  <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
                    Create a schedule to automatically process articles
                  </p>
                </div>
              ) : (
                <div className="space-y-3">
                  {schedules.map((schedule) => (
                    <div
                      key={schedule.id}
                      className={`p-4 rounded-lg border transition-colors ${
                        schedule.schedule_enabled
                          ? 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700'
                          : 'bg-gray-50 dark:bg-gray-800/50 border-gray-200 dark:border-gray-700 opacity-60'
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="font-medium text-gray-900 dark:text-gray-100">
                              {schedule.name}
                            </h3>
                            {schedule.schedule_enabled ? (
                              <span className="px-2 py-0.5 text-xs bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full">
                                Active
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400 rounded-full">
                                Paused
                              </span>
                            )}
                            {schedule.last_run_status === 'error' && (
                              <span className="px-2 py-0.5 text-xs bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-full">
                                Error
                              </span>
                            )}
                          </div>
                          <div className="flex items-center gap-4 mt-2 text-sm text-gray-500 dark:text-gray-400">
                            <span className="flex items-center gap-1">
                              <Clock className="w-3 h-3" />
                              {formatSchedule(schedule)}
                            </span>
                            <span>{schedule.batch_size} articles</span>
                          </div>
                          <div className="mt-2 text-xs text-gray-400 dark:text-gray-500">
                            Last run: {formatLastRun(schedule.last_run_at)}
                            {schedule.next_run_at && schedule.schedule_enabled && (
                              <> · Next: {formatLastRun(schedule.next_run_at)}</>
                            )}
                          </div>
                        </div>

                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleEdit(schedule)}
                            className="p-2 text-gray-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                            title="Edit"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => handleRunNow(schedule.id)}
                            disabled={runningId === schedule.id}
                            className="p-2 text-gray-400 hover:text-green-500 hover:bg-green-50 dark:hover:bg-green-900/20 rounded-lg transition-colors disabled:opacity-50"
                            title="Run Now"
                          >
                            {runningId === schedule.id ? (
                              <CheckCircle className="w-4 h-4 text-green-500" />
                            ) : (
                              <Play className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => handleToggleActive(schedule)}
                            className={`p-2 rounded-lg transition-colors ${
                              schedule.schedule_enabled
                                ? 'text-gray-400 hover:text-yellow-500 hover:bg-yellow-50 dark:hover:bg-yellow-900/20'
                                : 'text-gray-400 hover:text-green-500 hover:bg-green-50 dark:hover:bg-green-900/20'
                            }`}
                            title={schedule.schedule_enabled ? 'Pause' : 'Resume'}
                          >
                            {schedule.schedule_enabled ? (
                              <Pause className="w-4 h-4" />
                            ) : (
                              <RefreshCw className="w-4 h-4" />
                            )}
                          </button>
                          <button
                            onClick={() => handleDelete(schedule.id)}
                            className="p-2 text-gray-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Create/Edit Form */}
              {showForm && (
                <div className="p-4 bg-gray-50 dark:bg-gray-700/50 rounded-lg border border-gray-200 dark:border-gray-700">
                  <h3 className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-4">
                    {editingId ? 'Edit Schedule' : 'New Schedule'}
                  </h3>
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Name
                      </label>
                      <input
                        type="text"
                        value={formData.name}
                        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                        placeholder="e.g., Hourly threat scan"
                        className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
                      />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                          Schedule Type
                        </label>
                        <select
                          value={formData.schedule_type}
                          onChange={(e) =>
                            setFormData({
                              ...formData,
                              schedule_type: e.target.value as 'interval' | 'daily',
                            })
                          }
                          className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
                        >
                          <option value="interval">Interval</option>
                          <option value="daily">Daily</option>
                        </select>
                      </div>

                      {formData.schedule_type === 'interval' ? (
                        <div className="grid grid-cols-2 gap-2">
                          <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                              Every
                            </label>
                            <input
                              type="number"
                              min={1}
                              max={100}
                              value={formData.schedule_interval}
                              onChange={(e) =>
                                setFormData({ ...formData, schedule_interval: Number(e.target.value) })
                              }
                              className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
                            />
                          </div>
                          <div>
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                              Unit
                            </label>
                            <select
                              value={formData.schedule_unit}
                              onChange={(e) =>
                                setFormData({
                                  ...formData,
                                  schedule_unit: e.target.value as 'minutes' | 'hours' | 'days' | 'weeks',
                                })
                              }
                              className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
                            >
                              <option value="minutes">Minutes</option>
                              <option value="hours">Hours</option>
                              <option value="days">Days</option>
                              <option value="weeks">Weeks</option>
                            </select>
                          </div>
                        </div>
                      ) : (
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            Time (UTC)
                          </label>
                          <input
                            type="time"
                            value={formData.schedule_time}
                            onChange={(e) => setFormData({ ...formData, schedule_time: e.target.value })}
                            className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
                          />
                        </div>
                      )}
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                        Batch Size (articles per run)
                      </label>
                      <input
                        type="number"
                        min={10}
                        max={500}
                        value={formData.batch_size}
                        onChange={(e) =>
                          setFormData({ ...formData, batch_size: Number(e.target.value) })
                        }
                        className="w-full px-3 py-2 bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
                      />
                    </div>

                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        id="schedule_enabled"
                        checked={formData.schedule_enabled}
                        onChange={(e) => setFormData({ ...formData, schedule_enabled: e.target.checked })}
                        className="w-4 h-4 text-red-500 rounded border-gray-300 focus:ring-red-500"
                      />
                      <label htmlFor="schedule_enabled" className="text-sm text-gray-700 dark:text-gray-300">
                        Enable schedule
                      </label>
                    </div>

                    <div className="flex items-center justify-end gap-2 pt-2">
                      <button
                        onClick={resetForm}
                        className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
                      >
                        Cancel
                      </button>
                      <button
                        onClick={editingId ? handleUpdate : handleCreate}
                        disabled={!formData.name}
                        className="px-4 py-2 text-sm bg-red-500 text-white rounded-lg hover:bg-red-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                      >
                        {editingId ? 'Update Schedule' : 'Create Schedule'}
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-4 border-t border-gray-200 dark:border-gray-700">
          <button
            onClick={() => {
              resetForm();
              setShowForm(!showForm);
            }}
            className="flex items-center gap-2 px-4 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
          >
            <Plus className="w-4 h-4" />
            Add Schedule
          </button>
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
