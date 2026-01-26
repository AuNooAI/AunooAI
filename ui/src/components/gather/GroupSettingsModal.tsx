/**
 * GroupSettingsModal - Per-group collection settings modal
 * Allows customizing collection schedule, providers, and processing settings per keyword group.
 * Settings with null values inherit from global defaults.
 */

import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '../ui/dialog';
import { Button } from '../ui/button';
import { Input } from '../ui/input';
import { Label } from '../ui/label';
import { Switch } from '../ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Slider } from '../ui/slider';
import { Checkbox } from '../ui/checkbox';
import { Settings, Save, Loader2, RotateCcw, Globe } from 'lucide-react';
import type {
  GroupSettingsResponse,
  GroupSettingsUpdateRequest,
  AvailableProvider,
  AvailableModel,
} from '../../services/gatherApi';
import { getGroupSettings, updateGroupSettings, getAvailableModels, getAvailableProviders } from '../../services/gatherApi';

interface GroupSettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  groupId: number;
  groupName: string;
  onSaved?: () => void;
}

export function GroupSettingsModal({
  isOpen,
  onClose,
  groupId,
  groupName,
  onSaved,
}: GroupSettingsModalProps) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [settingsData, setSettingsData] = useState<GroupSettingsResponse | null>(null);
  const [formData, setFormData] = useState<GroupSettingsUpdateRequest>({});
  const [selectedProviders, setSelectedProviders] = useState<string[]>([]);
  const [availableProviders, setAvailableProviders] = useState<AvailableProvider[]>([]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [useGlobalSettings, setUseGlobalSettings] = useState(true);

  // Load settings when modal opens
  useEffect(() => {
    if (isOpen && groupId) {
      loadData();
    }
  }, [isOpen, groupId]);

  const loadData = async () => {
    setLoading(true);
    setError(null);

    try {
      // Load group settings, providers, and models in parallel
      const [settings, providers, models] = await Promise.all([
        getGroupSettings(groupId),
        getAvailableProviders(),
        getAvailableModels(),
      ]);

      setSettingsData(settings);
      setAvailableProviders(providers);
      setAvailableModels(models);

      // Check if group has any custom settings
      const hasCustom = settings.custom_fields.length > 0;
      setUseGlobalSettings(!hasCustom);

      // Initialize form data from effective settings
      setFormData({
        is_active: settings.is_active,
        check_interval: settings.settings.check_interval,
        interval_unit: settings.settings.interval_unit,
        search_date_range: settings.settings.search_date_range,
        auto_ingest_enabled: settings.settings.auto_ingest_enabled,
        min_relevance_threshold: settings.settings.min_relevance_threshold,
        quality_control_enabled: settings.settings.quality_control_enabled,
        auto_save_approved_only: settings.settings.auto_save_approved_only,
        default_llm_model: settings.settings.default_llm_model ?? undefined,
        llm_temperature: settings.settings.llm_temperature,
        llm_max_tokens: settings.settings.llm_max_tokens,
      });

      // Parse providers
      try {
        const providersJson = settings.settings.providers;
        const providersList = providersJson ? JSON.parse(providersJson) : [];
        setSelectedProviders(providersList);
      } catch {
        setSelectedProviders([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const handleProviderToggle = (providerId: string, checked: boolean) => {
    setSelectedProviders(prev =>
      checked
        ? [...prev, providerId]
        : prev.filter(p => p !== providerId)
    );
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);

    try {
      let requestData: GroupSettingsUpdateRequest;

      if (useGlobalSettings) {
        // Reset to global defaults
        requestData = { use_global_settings: true };
      } else {
        // Save custom settings
        requestData = {
          ...formData,
          providers: JSON.stringify(selectedProviders),
        };
      }

      const result = await updateGroupSettings(groupId, requestData);

      if (result.success) {
        onSaved?.();
        onClose();
      } else {
        setError(result.message || 'Failed to save settings');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const handleResetToGlobal = () => {
    setUseGlobalSettings(true);
  };

  // Calculate check interval display
  const getIntervalDisplay = () => {
    const interval = formData.check_interval || 24;
    const unit = formData.interval_unit || 3600;

    if (unit === 60) return `${interval} minute${interval !== 1 ? 's' : ''}`;
    if (unit === 3600) return `${interval} hour${interval !== 1 ? 's' : ''}`;
    if (unit === 86400) return `${interval} day${interval !== 1 ? 's' : ''}`;
    return `${interval} units`;
  };

  // Check if a field is customized (non-null in original settings)
  const isFieldCustom = (field: string) => {
    return settingsData?.custom_fields.includes(field);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="gather-modal gather-group-settings-modal">
        <DialogHeader>
          <DialogTitle className="gather-modal-title">
            <Settings className="h-5 w-5" />
            Group Settings: {groupName}
          </DialogTitle>
          <DialogDescription>
            Configure collection settings for this keyword group
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="gather-modal-loading">
            <Loader2 className="h-6 w-6 animate-spin" />
            <span>Loading settings...</span>
          </div>
        ) : error ? (
          <div className="gather-modal-error">
            <p>{error}</p>
            <Button variant="outline" onClick={loadData}>Retry</Button>
          </div>
        ) : (
          <>
            <div className="gather-modal-content">
              {/* Use Global Settings Toggle */}
              <div className="gather-modal-section gather-global-toggle-section">
                <div className="gather-toggle-row gather-global-toggle">
                  <div className="gather-toggle-info">
                    <Label htmlFor="use-global">
                      <Globe className="h-4 w-4 inline mr-2" />
                      Use Global Settings
                    </Label>
                    <span className="gather-toggle-desc">
                      Inherit all settings from global auto-collect configuration
                    </span>
                  </div>
                  <Switch
                    id="use-global"
                    checked={useGlobalSettings}
                    onCheckedChange={setUseGlobalSettings}
                  />
                </div>
                {!useGlobalSettings && (
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={handleResetToGlobal}
                    className="gather-reset-btn"
                  >
                    <RotateCcw className="h-4 w-4 mr-1" />
                    Reset to Global
                  </Button>
                )}
              </div>

              {/* Custom Settings - only shown when not using global */}
              {!useGlobalSettings && (
                <>
                  {/* Active Toggle */}
                  <div className="gather-modal-section">
                    <div className="gather-toggle-row">
                      <div className="gather-toggle-info">
                        <Label htmlFor="is-active">Active</Label>
                        <span className="gather-toggle-desc">Enable collection for this group</span>
                      </div>
                      <Switch
                        id="is-active"
                        checked={formData.is_active ?? true}
                        onCheckedChange={checked => setFormData(prev => ({ ...prev, is_active: checked }))}
                      />
                    </div>
                  </div>

                  {/* Collection Schedule */}
                  <div className="gather-modal-section">
                    <h4 className="gather-modal-section-title">
                      Collection Schedule
                      {isFieldCustom('check_interval') && (
                        <span className="gather-custom-badge">Custom</span>
                      )}
                    </h4>

                    <div className="gather-form-row">
                      <div className="gather-form-group">
                        <Label htmlFor="check-interval">Check Interval</Label>
                        <div className="gather-interval-inputs">
                          <Input
                            id="check-interval"
                            type="number"
                            min={1}
                            max={9999}
                            value={formData.check_interval || 24}
                            onChange={e => setFormData(prev => ({ ...prev, check_interval: parseInt(e.target.value) || 24 }))}
                            style={{ width: '100px' }}
                          />
                          <Select
                            value={String(formData.interval_unit || 3600)}
                            onValueChange={val => setFormData(prev => ({ ...prev, interval_unit: parseInt(val) }))}
                          >
                            <SelectTrigger>
                              <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value="60">Minutes</SelectItem>
                              <SelectItem value="3600">Hours</SelectItem>
                              <SelectItem value="86400">Days</SelectItem>
                            </SelectContent>
                          </Select>
                        </div>
                        <p className="gather-form-hint">Check every {getIntervalDisplay()}</p>
                      </div>

                      <div className="gather-form-group">
                        <Label htmlFor="search-range">Search Date Range (days)</Label>
                        <Input
                          id="search-range"
                          type="number"
                          min={1}
                          max={30}
                          value={formData.search_date_range || 7}
                          onChange={e => setFormData(prev => ({ ...prev, search_date_range: parseInt(e.target.value) || 7 }))}
                        />
                      </div>
                    </div>
                  </div>

                  {/* News Providers */}
                  <div className="gather-modal-section">
                    <h4 className="gather-modal-section-title">
                      News Providers
                      {isFieldCustom('providers') && (
                        <span className="gather-custom-badge">Custom</span>
                      )}
                    </h4>
                    <p className="gather-form-hint">Select which providers to use for this group</p>

                    <div className="gather-providers-grid">
                      {(availableProviders || []).map(provider => (
                        <div key={provider.id} className="gather-provider-item">
                          <Checkbox
                            id={`provider-${provider.id}`}
                            checked={selectedProviders.includes(provider.id)}
                            onCheckedChange={checked => handleProviderToggle(provider.id, checked as boolean)}
                            disabled={!provider.configured}
                          />
                          <Label
                            htmlFor={`provider-${provider.id}`}
                            className={!provider.configured ? 'gather-provider-disabled' : ''}
                          >
                            <span className="gather-provider-name">{provider.name}</span>
                            <span className="gather-provider-desc">{provider.description}</span>
                            {!provider.configured && (
                              <span className="gather-provider-unconfigured">Not configured</span>
                            )}
                          </Label>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Processing Settings */}
                  <div className="gather-modal-section">
                    <h4 className="gather-modal-section-title">
                      Processing Settings
                      {isFieldCustom('auto_ingest_enabled') && (
                        <span className="gather-custom-badge">Custom</span>
                      )}
                    </h4>

                    <div className="gather-toggle-row">
                      <div className="gather-toggle-info">
                        <Label htmlFor="auto-ingest">Auto-Processing</Label>
                        <span className="gather-toggle-desc">Automatically analyze articles with AI</span>
                      </div>
                      <Switch
                        id="auto-ingest"
                        checked={formData.auto_ingest_enabled ?? true}
                        onCheckedChange={checked => setFormData(prev => ({ ...prev, auto_ingest_enabled: checked }))}
                      />
                    </div>

                    <div className="gather-toggle-row">
                      <div className="gather-toggle-info">
                        <Label htmlFor="quality-control">Quality Control</Label>
                        <span className="gather-toggle-desc">Enable relevance scoring and filtering</span>
                      </div>
                      <Switch
                        id="quality-control"
                        checked={formData.quality_control_enabled ?? true}
                        onCheckedChange={checked => setFormData(prev => ({ ...prev, quality_control_enabled: checked }))}
                      />
                    </div>

                    <div className="gather-toggle-row">
                      <div className="gather-toggle-info">
                        <Label htmlFor="auto-save">Auto-Save Approved Only</Label>
                        <span className="gather-toggle-desc">Only save articles that pass quality threshold</span>
                      </div>
                      <Switch
                        id="auto-save"
                        checked={formData.auto_save_approved_only ?? true}
                        onCheckedChange={checked => setFormData(prev => ({ ...prev, auto_save_approved_only: checked }))}
                      />
                    </div>

                    {formData.quality_control_enabled && (
                      <div className="gather-form-group">
                        <Label>Minimum Relevance Threshold: {Math.round((formData.min_relevance_threshold || 0) * 100)}%</Label>
                        <Slider
                          value={[(formData.min_relevance_threshold || 0) * 100]}
                          onValueChange={([val]) => setFormData(prev => ({ ...prev, min_relevance_threshold: val / 100 }))}
                          min={0}
                          max={100}
                          step={5}
                        />
                      </div>
                    )}
                  </div>

                  {/* AI Settings */}
                  <div className="gather-modal-section">
                    <h4 className="gather-modal-section-title">
                      AI Settings
                      {isFieldCustom('default_llm_model') && (
                        <span className="gather-custom-badge">Custom</span>
                      )}
                    </h4>

                    <div className="gather-form-group">
                      <Label htmlFor="default-model">Default LLM Model</Label>
                      <Select
                        value={formData.default_llm_model || ''}
                        onValueChange={val => setFormData(prev => ({ ...prev, default_llm_model: val }))}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select a model..." />
                        </SelectTrigger>
                        <SelectContent>
                          {availableModels.map((model) => (
                            <SelectItem key={model.name} value={model.name}>
                              {model.name}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>

                    {formData.auto_ingest_enabled && (
                      <div className="gather-form-row">
                        <div className="gather-form-group">
                          <Label>LLM Temperature: {formData.llm_temperature?.toFixed(1) || '0.2'}</Label>
                          <Slider
                            value={[(formData.llm_temperature || 0.2) * 100]}
                            onValueChange={([val]) => setFormData(prev => ({ ...prev, llm_temperature: val / 100 }))}
                            min={0}
                            max={200}
                            step={10}
                          />
                        </div>

                        <div className="gather-form-group">
                          <Label htmlFor="max-tokens">Max Tokens</Label>
                          <Input
                            id="max-tokens"
                            type="number"
                            min={100}
                            max={4000}
                            value={formData.llm_max_tokens || 1000}
                            onChange={e => setFormData(prev => ({ ...prev, llm_max_tokens: parseInt(e.target.value) || 1000 }))}
                          />
                        </div>
                      </div>
                    )}
                  </div>
                </>
              )}

              {/* Info about next check */}
              {settingsData?.next_check_at && (
                <div className="gather-modal-info">
                  <p>
                    Next scheduled check: {new Date(settingsData.next_check_at).toLocaleString()}
                  </p>
                </div>
              )}
            </div>

            <DialogFooter>
              <Button variant="outline" onClick={onClose} disabled={saving}>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Saving...
                  </>
                ) : (
                  <>
                    <Save className="h-4 w-4" />
                    Save Settings
                  </>
                )}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
