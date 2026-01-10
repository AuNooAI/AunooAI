/**
 * Emerging Topics Config Modal - Configure Detection & Notification Settings
 */

import { useState, useEffect } from 'react';
import {
  Settings2,
  Info,
  Sliders,
  Save,
  RotateCcw,
  Bell,
  Mail,
  MessageCircle,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '../ui/tabs';
import { Label } from '../ui/label';
import { Slider } from '../ui/slider';
import { Input } from '../ui/input';
import { Switch } from '../ui/switch';
import { Badge } from '../ui/badge';
import { Checkbox } from '../ui/checkbox';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '../ui/select';

export interface EmergingTopicsConfig {
  sampleSize: number;
  daysBack: number;
  distanceThreshold: number;
  minArticlesPerTheme: number;
  maxArticlesPerTheme: number;
  model: string;
}

interface AIModel {
  id: string;
  name: string;
  provider: string;
}

interface NotificationSettings {
  notifications_enabled: boolean;
  notification_channels: { email?: boolean; in_app?: boolean; bluesky?: boolean };
  min_confidence: number;
  cooldown_minutes: number;
  email_recipients: string[];
  bluesky_handle: string | null;
  detection_type_filters: string[];
}

interface EmergingTopicsConfigModalProps {
  open: boolean;
  onClose: () => void;
  config: EmergingTopicsConfig;
  onSave: (config: EmergingTopicsConfig) => void;
  availableModels: AIModel[];
}

const DEFAULT_CONFIG: EmergingTopicsConfig = {
  sampleSize: 250,
  daysBack: 7,
  distanceThreshold: 0.85,
  minArticlesPerTheme: 3,
  maxArticlesPerTheme: 30,
  model: 'gpt-4o',
};

const STORAGE_KEY = 'emergingTopicsConfig';

export function loadEmergingTopicsConfig(): EmergingTopicsConfig {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      return { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
    }
  } catch (e) {
    console.error('Failed to load emerging topics config', e);
  }
  return DEFAULT_CONFIG;
}

export function saveEmergingTopicsConfigToStorage(config: EmergingTopicsConfig): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
}

export function EmergingTopicsConfigModal({
  open,
  onClose,
  config: initialConfig,
  onSave,
  availableModels,
}: EmergingTopicsConfigModalProps) {
  const [config, setConfig] = useState<EmergingTopicsConfig>(initialConfig);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('detection');

  // Notification state
  const [notificationSettings, setNotificationSettings] = useState<NotificationSettings>({
    notifications_enabled: false,
    notification_channels: { email: false, in_app: true, bluesky: false },
    min_confidence: 0.7,
    cooldown_minutes: 360,
    email_recipients: [],
    bluesky_handle: null,
    detection_type_filters: ['accelerating', 'new_cluster'],
  });
  const [notificationLoading, setNotificationLoading] = useState(false);
  const [testingNotification, setTestingNotification] = useState(false);
  const [emailInput, setEmailInput] = useState('');

  useEffect(() => {
    if (open) {
      setConfig(initialConfig);
      loadNotificationData();
    }
  }, [open, initialConfig]);

  const loadNotificationData = async () => {
    try {
      const response = await fetch('/api/emerging-topics/notifications/settings');
      if (response.ok) {
        const data = await response.json();
        setNotificationSettings({
          notifications_enabled: data.notifications_enabled || false,
          notification_channels: data.notification_channels || { email: false, in_app: true, bluesky: false },
          min_confidence: data.min_confidence || 0.7,
          cooldown_minutes: data.cooldown_minutes || 360,
          email_recipients: data.email_recipients || [],
          bluesky_handle: data.bluesky_handle || null,
          detection_type_filters: data.detection_type_filters || ['accelerating', 'new_cluster'],
        });
      }
    } catch (e) {
      console.error('Failed to load notification data', e);
    }
  };

  // Compute valid model options
  const modelOptions = availableModels.length > 0
    ? availableModels
    : [
        { id: 'gpt-4o', name: 'gpt-4o', provider: 'openai' },
        { id: 'gpt-4o-mini', name: 'gpt-4o-mini', provider: 'openai' },
        { id: 'claude-sonnet-4-20250514', name: 'claude-sonnet-4', provider: 'anthropic' },
      ];

  const selectedModel = modelOptions.find(m => m.id === config.model)?.id
    || modelOptions[0]?.id
    || 'gpt-4o';

  const handleSave = async () => {
    setLoading(true);
    try {
      saveEmergingTopicsConfigToStorage(config);
      onSave(config);
      onClose();
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setConfig(DEFAULT_CONFIG);
  };

  const updateField = <K extends keyof EmergingTopicsConfig>(
    field: K,
    value: EmergingTopicsConfig[K]
  ) => {
    setConfig((prev) => ({ ...prev, [field]: value }));
  };

  // Notification handlers
  const handleSaveNotifications = async () => {
    setNotificationLoading(true);
    try {
      const response = await fetch('/api/emerging-topics/notifications/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(notificationSettings),
      });
      if (response.ok) {
        await loadNotificationData();
      }
    } catch (e) {
      console.error('Failed to save notifications', e);
    } finally {
      setNotificationLoading(false);
    }
  };

  const handleTestNotification = async () => {
    setTestingNotification(true);
    try {
      const response = await fetch('/api/emerging-topics/notifications/test', {
        method: 'POST',
      });
      if (response.ok) {
        const result = await response.json();
        const channels = Object.entries(result.results || {})
          .filter(([_, v]: [string, any]) => v.sent)
          .map(([k]) => k);
        if (channels.length > 0) {
          alert(`Test sent via: ${channels.join(', ')}`);
        } else {
          alert('No channels configured or all failed');
        }
      }
    } catch (e) {
      console.error('Failed to test notification', e);
    } finally {
      setTestingNotification(false);
    }
  };

  const addEmailRecipient = () => {
    if (emailInput && emailInput.includes('@')) {
      setNotificationSettings(prev => ({
        ...prev,
        email_recipients: [...prev.email_recipients, emailInput],
      }));
      setEmailInput('');
    }
  };

  const removeEmailRecipient = (email: string) => {
    setNotificationSettings(prev => ({
      ...prev,
      email_recipients: prev.email_recipients.filter(e => e !== email),
    }));
  };

  const toggleDetectionType = (type: string) => {
    setNotificationSettings(prev => ({
      ...prev,
      detection_type_filters: prev.detection_type_filters.includes(type)
        ? prev.detection_type_filters.filter(t => t !== type)
        : [...prev.detection_type_filters, type],
    }));
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="w-auto min-w-[550px] max-w-[650px] max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Settings2 className="w-5 h-5" />
            Emerging Topics Settings
          </DialogTitle>
          <DialogDescription>
            Configure detection and notification settings
          </DialogDescription>
        </DialogHeader>

        <div className="flex-1 overflow-y-auto overflow-x-hidden pr-2">
          <Tabs value={activeTab} onValueChange={setActiveTab} className="mt-4">
            <TabsList className="w-full grid grid-cols-3">
              <TabsTrigger value="detection" className="gap-1 text-xs">
                <Sliders className="w-3.5 h-3.5" />
                Detection
              </TabsTrigger>
              <TabsTrigger value="notifications" className="gap-1 text-xs">
                <Bell className="w-3.5 h-3.5" />
                Alerts
              </TabsTrigger>
              <TabsTrigger value="info" className="gap-1 text-xs">
                <Info className="w-3.5 h-3.5" />
                Info
              </TabsTrigger>
            </TabsList>

            {/* Detection Tab */}
            <TabsContent value="detection" className="space-y-6 mt-4">
              {/* AI Model */}
              <div className="space-y-3">
                <Label className="font-medium">AI Model</Label>
                <Select
                  value={selectedModel}
                  onValueChange={(v) => updateField('model', v)}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Select model" />
                  </SelectTrigger>
                  <SelectContent>
                    {modelOptions.map((model) => (
                      <SelectItem key={model.id} value={model.id}>
                        {model.name} ({model.provider})
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Sample Size */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="font-medium">Sample Size</Label>
                  <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                    {config.sampleSize} articles
                  </span>
                </div>
                <Slider
                  value={[config.sampleSize]}
                  onValueChange={([value]) => updateField('sampleSize', value)}
                  min={50}
                  max={500}
                  step={50}
                />
              </div>

              {/* Days Back */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="font-medium">Days Back</Label>
                  <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                    {config.daysBack} days
                  </span>
                </div>
                <Slider
                  value={[config.daysBack]}
                  onValueChange={([value]) => updateField('daysBack', value)}
                  min={1}
                  max={30}
                  step={1}
                />
              </div>

              {/* Distance Threshold */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="font-medium">Distance Threshold</Label>
                  <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                    {config.distanceThreshold.toFixed(2)}
                  </span>
                </div>
                <Slider
                  value={[config.distanceThreshold * 100]}
                  onValueChange={([value]) => updateField('distanceThreshold', value / 100)}
                  min={30}
                  max={100}
                  step={5}
                />
              </div>

              {/* Min/Max Articles */}
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-sm">Min Articles</Label>
                    <span className="text-xs font-mono">{config.minArticlesPerTheme}</span>
                  </div>
                  <Slider
                    value={[config.minArticlesPerTheme]}
                    onValueChange={([value]) => updateField('minArticlesPerTheme', value)}
                    min={2}
                    max={20}
                    step={1}
                  />
                </div>
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <Label className="text-sm">Max Articles</Label>
                    <span className="text-xs font-mono">{config.maxArticlesPerTheme}</span>
                  </div>
                  <Slider
                    value={[config.maxArticlesPerTheme]}
                    onValueChange={([value]) => updateField('maxArticlesPerTheme', value)}
                    min={10}
                    max={100}
                    step={5}
                  />
                </div>
              </div>
            </TabsContent>

            {/* Notifications Tab */}
            <TabsContent value="notifications" className="space-y-6 mt-4">
              {/* Enable Toggle */}
              <div className="flex items-center justify-between p-4 bg-gray-50 dark:bg-gray-800 rounded-lg">
                <div>
                  <Label className="font-medium">Enable Notifications</Label>
                  <p className="text-xs text-gray-500 mt-1">
                    Get alerted about new emerging topics
                  </p>
                </div>
                <Switch
                  checked={notificationSettings.notifications_enabled}
                  onCheckedChange={(checked) =>
                    setNotificationSettings(prev => ({ ...prev, notifications_enabled: checked }))
                  }
                />
              </div>

              {/* Channels */}
              <div className="space-y-3">
                <Label className="font-medium">Notification Channels</Label>
                <div className="space-y-2">
                  <div className="flex items-center gap-3">
                    <Checkbox
                      id="channel-inapp"
                      checked={notificationSettings.notification_channels.in_app}
                      onCheckedChange={(checked) =>
                        setNotificationSettings(prev => ({
                          ...prev,
                          notification_channels: { ...prev.notification_channels, in_app: !!checked },
                        }))
                      }
                    />
                    <Label htmlFor="channel-inapp" className="flex items-center gap-2 cursor-pointer">
                      <Bell className="w-4 h-4" />
                      In-App Notifications
                    </Label>
                  </div>
                  <div className="flex items-center gap-3">
                    <Checkbox
                      id="channel-email"
                      checked={notificationSettings.notification_channels.email}
                      onCheckedChange={(checked) =>
                        setNotificationSettings(prev => ({
                          ...prev,
                          notification_channels: { ...prev.notification_channels, email: !!checked },
                        }))
                      }
                    />
                    <Label htmlFor="channel-email" className="flex items-center gap-2 cursor-pointer">
                      <Mail className="w-4 h-4" />
                      Email
                    </Label>
                  </div>
                  <div className="flex items-center gap-3">
                    <Checkbox
                      id="channel-bluesky"
                      checked={notificationSettings.notification_channels.bluesky}
                      onCheckedChange={(checked) =>
                        setNotificationSettings(prev => ({
                          ...prev,
                          notification_channels: { ...prev.notification_channels, bluesky: !!checked },
                        }))
                      }
                    />
                    <Label htmlFor="channel-bluesky" className="flex items-center gap-2 cursor-pointer">
                      <MessageCircle className="w-4 h-4" />
                      Bluesky DM
                    </Label>
                  </div>
                </div>
              </div>

              {/* Email Recipients */}
              {notificationSettings.notification_channels.email && (
                <div className="space-y-2">
                  <Label className="font-medium">Email Recipients</Label>
                  <div className="flex gap-2">
                    <Input
                      type="email"
                      placeholder="email@example.com"
                      value={emailInput}
                      onChange={(e) => setEmailInput(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && addEmailRecipient()}
                    />
                    <Button variant="outline" size="sm" onClick={addEmailRecipient}>
                      Add
                    </Button>
                  </div>
                  {notificationSettings.email_recipients.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {notificationSettings.email_recipients.map((email) => (
                        <Badge
                          key={email}
                          variant="secondary"
                          className="cursor-pointer"
                          onClick={() => removeEmailRecipient(email)}
                        >
                          {email} ×
                        </Badge>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* Bluesky Handle */}
              {notificationSettings.notification_channels.bluesky && (
                <div className="space-y-2">
                  <Label className="font-medium">Bluesky Handle</Label>
                  <Input
                    placeholder="@handle.bsky.social"
                    value={notificationSettings.bluesky_handle || ''}
                    onChange={(e) =>
                      setNotificationSettings(prev => ({
                        ...prev,
                        bluesky_handle: e.target.value || null,
                      }))
                    }
                  />
                </div>
              )}

              {/* Confidence Threshold */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="font-medium">Min Confidence</Label>
                  <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                    {(notificationSettings.min_confidence * 100).toFixed(0)}%
                  </span>
                </div>
                <Slider
                  value={[notificationSettings.min_confidence * 100]}
                  onValueChange={([value]) =>
                    setNotificationSettings(prev => ({ ...prev, min_confidence: value / 100 }))
                  }
                  min={50}
                  max={100}
                  step={5}
                />
                <p className="text-xs text-gray-500">Only notify for topics above this confidence</p>
              </div>

              {/* Cooldown */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label className="font-medium">Cooldown Period</Label>
                  <span className="text-sm font-mono bg-gray-100 dark:bg-gray-800 px-2 py-0.5 rounded">
                    {notificationSettings.cooldown_minutes / 60}h
                  </span>
                </div>
                <Slider
                  value={[notificationSettings.cooldown_minutes]}
                  onValueChange={([value]) =>
                    setNotificationSettings(prev => ({ ...prev, cooldown_minutes: value }))
                  }
                  min={60}
                  max={1440}
                  step={60}
                />
                <p className="text-xs text-gray-500">Minimum time between notification batches</p>
              </div>

              {/* Detection Type Filters */}
              <div className="space-y-2">
                <Label className="font-medium">Notify For</Label>
                <div className="flex flex-wrap gap-2">
                  {['accelerating', 'new_cluster', 'llm_proposed', 'proto_cluster'].map((type) => (
                    <Badge
                      key={type}
                      variant={notificationSettings.detection_type_filters.includes(type) ? 'default' : 'outline'}
                      className="cursor-pointer"
                      onClick={() => toggleDetectionType(type)}
                    >
                      {type.replace('_', ' ')}
                    </Badge>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2">
                <Button
                  onClick={handleSaveNotifications}
                  disabled={notificationLoading}
                  size="sm"
                >
                  {notificationLoading ? (
                    <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4 mr-1" />
                  )}
                  Save Notifications
                </Button>
                <Button
                  variant="outline"
                  onClick={handleTestNotification}
                  disabled={testingNotification}
                  size="sm"
                >
                  {testingNotification ? (
                    <Loader2 className="w-4 h-4 mr-1 animate-spin" />
                  ) : (
                    <Bell className="w-4 h-4 mr-1" />
                  )}
                  Test
                </Button>
              </div>
            </TabsContent>

            {/* Info Tab */}
            <TabsContent value="info" className="space-y-4 mt-4">
              <div className="bg-blue-50 dark:bg-blue-950 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                <h4 className="font-semibold text-blue-900 dark:text-blue-100 flex items-center gap-2 mb-2">
                  <Info className="w-4 h-4" />
                  About Emerging Topics Detection
                </h4>
                <p className="text-sm text-blue-800 dark:text-blue-200">
                  This system identifies emerging developments from your news articles.
                  It samples recent high-novelty articles, proposes specific themes,
                  then validates them with semantic search.
                </p>
              </div>

              <div className="bg-purple-50 dark:bg-purple-950 border border-purple-200 dark:border-purple-800 rounded-lg p-4">
                <h4 className="font-semibold text-purple-900 dark:text-purple-100 mb-3">
                  How Scores Are Calculated
                </h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between text-purple-700 dark:text-purple-300">
                    <span><strong>Volume (25%)</strong></span>
                    <span className="text-xs">Article count impact</span>
                  </div>
                  <div className="flex justify-between text-purple-700 dark:text-purple-300">
                    <span><strong>Velocity (30%)</strong></span>
                    <span className="text-xs">Growth momentum</span>
                  </div>
                  <div className="flex justify-between text-purple-700 dark:text-purple-300">
                    <span><strong>Diversity (20%)</strong></span>
                    <span className="text-xs">Source variety</span>
                  </div>
                  <div className="flex justify-between text-purple-700 dark:text-purple-300">
                    <span><strong>Novelty (25%)</strong></span>
                    <span className="text-xs">Semantic uniqueness</span>
                  </div>
                </div>
              </div>
            </TabsContent>
          </Tabs>
        </div>

        <DialogFooter className="flex items-center justify-between gap-2 border-t pt-4 mt-4 flex-shrink-0">
          <Button variant="outline" onClick={onClose}>
            Close
          </Button>
          {activeTab === 'detection' && (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={handleReset} disabled={loading}>
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                Reset
              </Button>
              <Button size="sm" onClick={handleSave} disabled={loading}>
                <Save className="w-3.5 h-3.5 mr-1.5" />
                Save
              </Button>
            </div>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
