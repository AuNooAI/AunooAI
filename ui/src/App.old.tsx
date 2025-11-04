/**
 * Trend Convergence Dashboard - Using Radix UI Components
 * Full backend integration with modern UI components
 */

import { useState } from 'react';
import { useTrendConvergence } from './hooks/useTrendConvergence';
import type { TrendConvergenceData } from './services/api';

// Import Radix UI components
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from './components/ui/dialog';
import { Button } from './components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './components/ui/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './components/ui/select';
import { Badge } from './components/ui/badge';
import { Alert, AlertDescription, AlertTitle } from './components/ui/alert';
import { Loader2, Settings, TrendingUp, Clock, Target, AlertCircle } from 'lucide-react';

// Navigation Bar Component
function NavBar({ loading, onConfigureClick }: { loading: boolean; onConfigureClick: () => void }) {
  return (
    <div className="bg-white/80 backdrop-blur-sm border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Breadcrumb */}
          <div className="flex items-center space-x-2 text-sm">
            <span className="text-gray-500">Explore</span>
            <span className="text-gray-400">/</span>
            <span className="text-gray-700 font-medium">Strategic Recommendations</span>
            <span className="text-gray-400">•</span>
            <span className="text-gray-600">Current indicators and potential disruption scenarios</span>
          </div>

          {/* Actions */}
          <Button
            onClick={onConfigureClick}
            disabled={loading}
            className="gap-2"
          >
            {loading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" />
                Analyzing...
              </>
            ) : (
              <>
                <Settings className="h-4 w-4" />
                Configure Analysis
              </>
            )}
          </Button>
        </div>
      </div>
    </div>
  );
}

// Configuration Modal Component using Radix Dialog
function ConfigModal({
  isOpen,
  onOpenChange,
  config,
  topics,
  models,
  profiles,
  onUpdateConfig,
  onGenerate,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  config: any;
  topics: any[];
  models: any[];
  profiles: any[];
  onUpdateConfig: (updates: any) => void;
  onGenerate: () => void;
}) {
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onGenerate();
    onOpenChange(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Configure Trend Convergence Analysis</DialogTitle>
          <DialogDescription>
            Configure your analysis settings to get started
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-2 gap-4">
            {/* Topic Selection */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Topic *</label>
              <Select value={config.topic} onValueChange={(value) => onUpdateConfig({ topic: value })}>
                <SelectTrigger>
                  <SelectValue placeholder="Select a topic..." />
                </SelectTrigger>
                <SelectContent>
                  {topics.map((topic) => (
                    <SelectItem key={topic.name} value={topic.name}>
                      {topic.display_name || topic.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Model Selection */}
            <div className="space-y-2">
              <label className="text-sm font-medium">AI Model *</label>
              <Select value={config.model} onValueChange={(value) => onUpdateConfig({ model: value })}>
                <SelectTrigger>
                  <SelectValue placeholder="Select model..." />
                </SelectTrigger>
                <SelectContent>
                  {models.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      {model.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Timeframe */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Timeframe</label>
              <Select
                value={String(config.timeframe_days)}
                onValueChange={(value) => onUpdateConfig({ timeframe_days: parseInt(value) })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="30">Last 30 Days</SelectItem>
                  <SelectItem value="90">Last 90 Days</SelectItem>
                  <SelectItem value="180">Last 180 Days</SelectItem>
                  <SelectItem value="365">Last 365 Days</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Analysis Depth */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Analysis Depth</label>
              <Select value={config.analysis_depth} onValueChange={(value) => onUpdateConfig({ analysis_depth: value })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="standard">Standard</SelectItem>
                  <SelectItem value="detailed">Detailed</SelectItem>
                  <SelectItem value="comprehensive">Comprehensive</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Consistency Mode */}
            <div className="space-y-2">
              <label className="text-sm font-medium">Consistency Mode</label>
              <Select
                value={config.consistency_mode}
                onValueChange={(value) => onUpdateConfig({ consistency_mode: value })}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="deterministic">Deterministic</SelectItem>
                  <SelectItem value="low_variance">Low Variance</SelectItem>
                  <SelectItem value="balanced">Balanced</SelectItem>
                  <SelectItem value="creative">Creative</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Organizational Profile */}
            {profiles.length > 0 && (
              <div className="space-y-2">
                <label className="text-sm font-medium">Organizational Profile</label>
                <Select
                  value={config.profile_id ? String(config.profile_id) : undefined}
                  onValueChange={(value) => onUpdateConfig({ profile_id: value ? parseInt(value) : undefined })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="None" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">None</SelectItem>
                    {profiles.map((profile) => (
                      <SelectItem key={profile.id} value={String(profile.id)}>
                        {profile.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex justify-end gap-3 pt-4 border-t">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!config.topic || !config.model}>
              Generate Analysis
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// Strategic Recommendations Display
function StrategicRecommendations({ data }: { data: TrendConvergenceData }) {
  if (!data.strategic_recommendations) return null;

  const timeframes = [
    {
      key: 'near_term',
      title: 'NEAR-TERM',
      subtitle: '2025-2027',
      icon: Clock,
      color: 'bg-green-50 border-green-200',
      data: data.strategic_recommendations.near_term,
    },
    {
      key: 'mid_term',
      title: 'MID-TERM',
      subtitle: '2027-2032',
      icon: TrendingUp,
      color: 'bg-blue-50 border-blue-200',
      data: data.strategic_recommendations.mid_term,
    },
    {
      key: 'long_term',
      title: 'LONG-TERM',
      subtitle: '2032+',
      icon: Target,
      color: 'bg-purple-50 border-purple-200',
      data: data.strategic_recommendations.long_term,
    },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Strategic Recommendations</h2>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {timeframes.map((timeframe) => {
          const Icon = timeframe.icon;
          const trends = timeframe.data?.trends || [];

          return (
            <Card key={timeframe.key} className={`${timeframe.color}`}>
              <CardHeader>
                <div className="flex items-center gap-2">
                  <Icon className="h-5 w-5" />
                  <CardTitle className="text-lg">{timeframe.title}</CardTitle>
                </div>
                <CardDescription>{timeframe.subtitle}</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {trends.slice(0, 5).map((trend: any, idx: number) => (
                  <div key={idx} className="flex gap-2">
                    <span className="text-gray-500">•</span>
                    <p className="text-sm text-gray-700">
                      {typeof trend === 'string' ? trend : (trend.name || trend.description || 'Trend')}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          );
        })}
      </div>
    </div>
  );
}

// Executive Decision Framework Display
function ExecutiveFramework({ data }: { data: TrendConvergenceData }) {
  if (!data.executive_decision_framework?.principles) return null;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Executive Decision Framework</h2>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {data.executive_decision_framework.principles.map((principle: any, idx: number) => (
          <Card key={idx}>
            <CardHeader>
              <CardTitle className="text-base">{principle.title || principle.name || `Principle ${idx + 1}`}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm text-gray-600">
                {principle.description || principle.content || principle.rationale || 'No description available'}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

// Next Steps Display
function NextSteps({ data }: { data: TrendConvergenceData }) {
  if (!data.next_steps || data.next_steps.length === 0) return null;

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-gray-900">Next Steps</h2>

      <Card>
        <CardContent className="pt-6">
          <ol className="space-y-4">
            {data.next_steps.map((step: any, idx: number) => (
              <li key={idx} className="flex gap-4">
                <Badge variant="outline" className="h-6 w-6 rounded-full flex items-center justify-center">
                  {idx + 1}
                </Badge>
                <div className="flex-1">
                  <p className="text-sm text-gray-700">
                    {typeof step === 'string' ? step : (step.action || step.description || 'Step')}
                  </p>
                  {typeof step === 'object' && step.timeline && (
                    <p className="text-xs text-gray-500 mt-1">Timeline: {step.timeline}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </CardContent>
      </Card>
    </div>
  );
}

// Main App Component
export default function App() {
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const { data, topics, profiles, models, config, loading, error, generateAnalysis, updateConfig, clearError } = useTrendConvergence();

  const handleGenerate = async () => {
    await generateAnalysis();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar loading={loading} onConfigureClick={() => setIsConfigOpen(true)} />

      <ConfigModal
        isOpen={isConfigOpen}
        onOpenChange={setIsConfigOpen}
        config={config}
        topics={topics}
        models={models}
        profiles={profiles}
        onUpdateConfig={updateConfig}
        onGenerate={handleGenerate}
      />

      {/* Error Alert */}
      {error && (
        <div className="fixed bottom-4 right-4 z-50 max-w-md">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription className="flex items-start justify-between gap-4">
              <span>{error}</span>
              <Button variant="ghost" size="sm" onClick={clearError}>
                ×
              </Button>
            </AlertDescription>
          </Alert>
        </div>
      )}

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {loading && (
          <div className="flex flex-col items-center justify-center py-20">
            <Loader2 className="h-12 w-12 animate-spin text-pink-500 mb-4" />
            <p className="text-lg text-gray-600">Generating strategic analysis...</p>
            <p className="text-sm text-gray-500 mt-2">This may take a minute</p>
          </div>
        )}

        {!loading && !data && (
          <div className="flex flex-col items-center justify-center py-20">
            <TrendingUp className="h-16 w-16 text-gray-300 mb-4" />
            <h2 className="text-2xl font-semibold text-gray-700 mb-2">Ready to Analyze Trends</h2>
            <p className="text-gray-500 mb-6">Configure your analysis settings to get started</p>
            <Button onClick={() => setIsConfigOpen(true)} size="lg">
              <Settings className="h-5 w-5 mr-2" />
              Configure Analysis
            </Button>
          </div>
        )}

        {!loading && data && (
          <div className="space-y-8">
            {/* Metadata */}
            <div className="flex items-center justify-between">
              <div className="flex gap-3">
                <Badge variant="secondary">{data.model_used || 'Unknown Model'}</Badge>
                <Badge variant="outline">{data.articles_analyzed || 0} articles analyzed</Badge>
                {data.analysis_depth && <Badge variant="outline">{data.analysis_depth}</Badge>}
              </div>
              <Button variant="outline" size="sm" onClick={() => setIsConfigOpen(true)}>
                <Settings className="h-4 w-4 mr-2" />
                Reconfigure
              </Button>
            </div>

            <StrategicRecommendations data={data} />
            <ExecutiveFramework data={data} />
            <NextSteps data={data} />
          </div>
        )}
      </main>
    </div>
  );
}
