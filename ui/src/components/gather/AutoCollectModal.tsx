/**
 * AutoCollectModal - Settings modal for auto-collection configuration
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
import { Settings, Save, Loader2 } from 'lucide-react';
import type { KeywordMonitorSettings, AvailableProvider, AvailableModel } from '../../services/gatherApi';
import { getAvailableModels } from '../../services/gatherApi';

interface AutoCollectModalProps {
  isOpen: boolean;
  onClose: () => void;
  settings: KeywordMonitorSettings | null;
  availableProviders: AvailableProvider[];
  onSave: (settings: Partial<KeywordMonitorSettings>) => Promise<boolean>;
}

export function AutoCollectModal({
  isOpen,
  onClose,
  settings,
  availableProviders,
  onSave,
}: AutoCollectModalProps) {
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState<Partial<KeywordMonitorSettings>>({});
  const [selectedProviders, setSelectedProviders] = useState<string[]>([]);
  const [availableModels, setAvailableModels] = useState<AvailableModel[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  // Load available models when modal opens
  useEffect(() => {
    if (isOpen && availableModels.length === 0) {
      setLoadingModels(true);
      getAvailableModels()
        .then(models => setAvailableModels(models))
        .catch(() => setAvailableModels([]))
        .finally(() => setLoadingModels(false));
    }
  }, [isOpen, availableModels.length]);

  // Initialize form data when settings change
  useEffect(() => {
    if (settings) {
      setFormData({
        check_interval: settings.check_interval,
        interval_unit: settings.interval_unit,
        search_date_range: settings.search_date_range,
        daily_request_limit: settings.daily_request_limit,
        auto_ingest_enabled: settings.auto_ingest_enabled,
        min_relevance_threshold: settings.min_relevance_threshold,
        quality_control_enabled: settings.quality_control_enabled,
        auto_save_approved_only: settings.auto_save_approved_only,
        auto_regenerate_reports: settings.auto_regenerate_reports,
        llm_temperature: settings.llm_temperature,
        llm_max_tokens: settings.llm_max_tokens,
        default_llm_model: settings.default_llm_model,
      });

      // Parse providers
      try {
        const providers = settings.providers ? JSON.parse(settings.providers) : [settings.provider || 'newsapi'];
        setSelectedProviders(providers);
      } catch {
        setSelectedProviders([settings.provider || 'newsapi']);
      }
    }
  }, [settings]);

  const handleProviderToggle = (providerId: string, checked: boolean) => {
    setSelectedProviders(prev =>
      checked
        ? [...prev, providerId]
        : prev.filter(p => p !== providerId)
    );
  };

  const handleSave = async () => {
    setSaving(true);

    // Merge formData with original settings to ensure all required fields are present
    const dataToSave = {
      ...settings,  // Start with all original settings
      ...formData,  // Override with form changes
      providers: JSON.stringify(selectedProviders),
    };

    const success = await onSave(dataToSave);
    setSaving(false);

    if (success) {
      onClose();
    }
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

  return (
    <Dialog open={isOpen} onOpenChange={onClose}>
      <DialogContent className="gather-modal gather-autocollect-modal">
        <DialogHeader>
          <DialogTitle className="gather-modal-title">
            <Settings className="h-5 w-5" />
            Auto-Collect Settings
          </DialogTitle>
          <DialogDescription>
            Configure automatic article collection settings
          </DialogDescription>
        </DialogHeader>

        <div className="gather-modal-content">
          {/* Collection Schedule */}
          <div className="gather-modal-section">
            <h4 className="gather-modal-section-title">Collection Schedule</h4>

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

            <div className="gather-form-group">
              <Label htmlFor="daily-limit">Daily Request Limit</Label>
              <Input
                id="daily-limit"
                type="number"
                min={10}
                max={1000}
                value={formData.daily_request_limit || 100}
                onChange={e => setFormData(prev => ({ ...prev, daily_request_limit: parseInt(e.target.value) || 100 }))}
              />
            </div>
          </div>

          {/* News Providers */}
          <div className="gather-modal-section">
            <h4 className="gather-modal-section-title">News Providers</h4>
            <p className="gather-form-hint">Select which providers to use for article collection</p>

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
            <h4 className="gather-modal-section-title">Processing Settings</h4>

            <div className="gather-toggle-row">
              <div className="gather-toggle-info">
                <Label htmlFor="auto-ingest">Auto-Processing</Label>
                <span className="gather-toggle-desc">Automatically analyze articles with AI</span>
              </div>
              <Switch
                id="auto-ingest"
                checked={formData.auto_ingest_enabled}
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
                checked={formData.quality_control_enabled}
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
                checked={formData.auto_save_approved_only}
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
            <h4 className="gather-modal-section-title">AI Settings</h4>

            <div className="gather-form-group">
              <Label htmlFor="default-model">Default LLM Model</Label>
              <Select
                value={formData.default_llm_model || ''}
                onValueChange={val => setFormData(prev => ({ ...prev, default_llm_model: val }))}
                disabled={loadingModels}
              >
                <SelectTrigger>
                  <SelectValue placeholder={loadingModels ? "Loading models..." : "Select a model..."} />
                </SelectTrigger>
                <SelectContent>
                  {availableModels.map((model) => (
                    <SelectItem key={model.name} value={model.name}>
                      {model.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="gather-form-hint">
                Model used for article enrichment (sentiment, driver type, etc.)
              </p>
            </div>

            {formData.auto_ingest_enabled && (
              <>
              <div className="gather-form-row">
                <div className="gather-form-group">
                  <Label>LLM Temperature: {formData.llm_temperature?.toFixed(1)}</Label>
                  <Slider
                    value={[(formData.llm_temperature || 0.1) * 100]}
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

              <div className="gather-toggle-row">
                <div className="gather-toggle-info">
                  <Label htmlFor="auto-reports">Auto-Regenerate Reports</Label>
                  <span className="gather-toggle-desc">Update reports when new articles are processed</span>
                </div>
                <Switch
                  id="auto-reports"
                  checked={formData.auto_regenerate_reports}
                  onCheckedChange={checked => setFormData(prev => ({ ...prev, auto_regenerate_reports: checked }))}
                />
              </div>
            </>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={handleSave} disabled={saving || selectedProviders.length === 0}>
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
      </DialogContent>
    </Dialog>
  );
}
