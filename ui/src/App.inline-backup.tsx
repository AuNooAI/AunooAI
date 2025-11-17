/**
 * Main App Component - Connected to FastAPI Backend
 * This replaces the static Figma export with a dynamic, data-driven UI
 */

import { useState } from 'react';
import { useTrendConvergence } from './hooks/useTrendConvergence';
import type { TrendConvergenceData } from './services/api';

// Navigation Bar Component
function NavBar({ onConfigureClick }: { onConfigureClick: () => void }) {
  return (
    <div className="bg-white/80 border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Breadcrumb */}
          <div className="flex items-center space-x-2 text-sm">
            <span className="text-gray-600">Explore</span>
            <span className="text-gray-500">/</span>
            <span className="text-gray-800">Strategic Recommendations</span>
            <span className="text-gray-500">•</span>
            <span className="text-gray-700">Current indicators and potential disruption scenarios</span>
          </div>

          {/* Actions */}
          <div className="flex items-center space-x-4">
            <button className="p-2 hover:bg-gray-100 rounded-md transition">
              <svg className="w-5 h-5 text-gray-700" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
              </svg>
            </button>
            <button
              onClick={onConfigureClick}
              className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 transition flex items-center space-x-2"
            >
              <span>Configure Analysis</span>
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// Configuration Modal Component
function ConfigModal({
  isOpen,
  onClose,
  config,
  topics,
  models,
  profiles,
  onUpdateConfig,
  onGenerate,
}: {
  isOpen: boolean;
  onClose: () => void;
  config: any;
  topics: any[];
  models: any[];
  profiles: any[];
  onUpdateConfig: (updates: any) => void;
  onGenerate: () => void;
}) {
  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onGenerate();
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={onClose}>
      <div
        className="bg-white rounded-lg shadow-xl max-w-4xl w-full mx-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={handleSubmit}>
          {/* Header */}
          <div className="border-b border-gray-200 px-6 py-4">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-semibold text-gray-950">Configure Trend Convergence Analysis</h2>
              <button
                type="button"
                onClick={onClose}
                className="text-gray-500 hover:text-gray-700 transition"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Body */}
          <div className="px-6 py-4 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              {/* Topic */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Topic</label>
                <select
                  value={config.topic}
                  onChange={(e) => onUpdateConfig({ topic: e.target.value })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent"
                  required
                >
                  <option value="">Select a topic...</option>
                  {topics.map((topic) => (
                    <option key={topic.name} value={topic.name}>
                      {topic.display_name || topic.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Model */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">AI Model</label>
                <select
                  value={config.model}
                  onChange={(e) => onUpdateConfig({ model: e.target.value })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent"
                  required
                >
                  <option value="">Select model...</option>
                  {models.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.name}
                    </option>
                  ))}
                </select>
              </div>

              {/* Timeframe */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Timeframe</label>
                <select
                  value={config.timeframe_days}
                  onChange={(e) => onUpdateConfig({ timeframe_days: parseInt(e.target.value) })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent"
                >
                  <option value="30">Last 30 Days</option>
                  <option value="90">Last 90 Days</option>
                  <option value="180">Last 180 Days</option>
                  <option value="365">Last 365 Days</option>
                </select>
              </div>

              {/* Analysis Depth */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Analysis Depth</label>
                <select
                  value={config.analysis_depth}
                  onChange={(e) => onUpdateConfig({ analysis_depth: e.target.value })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent"
                >
                  <option value="standard">Standard</option>
                  <option value="detailed">Detailed</option>
                  <option value="comprehensive">Comprehensive</option>
                </select>
              </div>

              {/* Consistency Mode */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Consistency Mode</label>
                <select
                  value={config.consistency_mode}
                  onChange={(e) => onUpdateConfig({ consistency_mode: e.target.value })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent"
                >
                  <option value="deterministic">🎯 Deterministic - Maximum consistency</option>
                  <option value="low_variance">🎲 Low Variance - High consistency</option>
                  <option value="balanced">⚖️ Balanced - Good mix</option>
                  <option value="creative">🌟 Creative - Maximum variation</option>
                </select>
              </div>

              {/* Organizational Profile */}
              <div>
                <label className="block text-sm font-medium text-gray-800 mb-1">Organizational Profile</label>
                <select
                  value={config.profile_id || ''}
                  onChange={(e) => onUpdateConfig({ profile_id: e.target.value ? parseInt(e.target.value) : undefined })}
                  className="w-full border border-gray-300 rounded-md px-3 py-2 focus:ring-2 focus:ring-pink-500 focus:border-transparent"
                >
                  <option value="">No profile selected</option>
                  {profiles.map((profile) => (
                    <option key={profile.id} value={profile.id}>
                      {profile.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          {/* Footer */}
          <div className="border-t border-gray-200 px-6 py-4 flex justify-end space-x-3">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 border border-gray-300 rounded-md hover:bg-gray-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-gradient-to-r from-pink-500 to-pink-600 text-white rounded-md hover:from-pink-600 hover:to-pink-700 transition"
            >
              Generate Analysis
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Strategic Recommendations Display
function StrategicRecommendations({ data }: { data: TrendConvergenceData }) {
  if (!data.strategic_recommendations) return null;

  const { near_term, mid_term, long_term } = data.strategic_recommendations;

  const TimelineCard = ({ title, timeframe, trends, color }: any) => (
    <div className={`flex-1 rounded-xl p-6 text-white ${color}`}>
      <div className="flex items-center space-x-2 mb-4 border-b border-white/20 pb-2">
        <h3 className="font-semibold text-lg">{title}</h3>
      </div>
      <ul className="space-y-2">
        {trends.map((trend: any, idx: number) => {
          const trendText = typeof trend === 'string' ? trend : trend.name || trend.description;
          return (
            <li key={idx} className="flex items-start space-x-2 text-sm">
              <span className="mt-1">•</span>
              <span>{trendText}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );

  return (
    <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
      <h2 className="text-2xl font-bold mb-2">Strategic Recommendations</h2>
      <p className="text-gray-700 mb-6">Evidence-based action plan for executive leadership</p>

      <div className="flex gap-4">
        <TimelineCard
          title="NEAR-TERM (2025-2027)"
          timeframe={near_term.timeframe}
          trends={near_term.trends}
          color="bg-gradient-to-br from-pink-500 to-pink-600"
        />
        <TimelineCard
          title="MID-TERM (2027-2032)"
          timeframe={mid_term.timeframe}
          trends={mid_term.trends}
          color="bg-gradient-to-br from-pink-500 to-purple-600"
        />
        <TimelineCard
          title="LONG-TERM (2032+)"
          timeframe={long_term.timeframe}
          trends={long_term.trends}
          color="bg-gradient-to-br from-purple-600 to-indigo-700"
        />
      </div>
    </div>
  );
}

// Executive Framework Display
function ExecutiveFramework({ data }: { data: TrendConvergenceData }) {
  if (!data.executive_decision_framework?.principles) return null;

  return (
    <div className="bg-white rounded-lg shadow-sm p-6 mb-6">
      <h2 className="text-2xl font-bold mb-6">Executive Decision Framework</h2>

      <div className="grid grid-cols-3 gap-4">
        {data.executive_decision_framework.principles.map((principle, idx) => {
          const title = principle.title || principle.name || `Principle ${idx + 1}`;
          const description = principle.description || principle.content || '';

          return (
            <div
              key={idx}
              className="border-l-4 border-pink-500 bg-gray-50 p-4 rounded-r-lg hover:shadow-md transition"
            >
              <h3 className="font-semibold text-gray-950 mb-2">{title}</h3>
              <p className="text-sm text-gray-700">{description}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Next Steps Display
function NextSteps({ data }: { data: TrendConvergenceData }) {
  if (!data.next_steps || data.next_steps.length === 0) return null;

  return (
    <div className="bg-white rounded-lg shadow-sm p-6">
      <h2 className="text-2xl font-bold mb-6">Next Steps</h2>

      <div className="space-y-3">
        {data.next_steps.map((step, idx) => (
          <div key={idx} className="flex items-start space-x-3 p-3 bg-gray-50 rounded-lg hover:bg-pink-50 transition">
            <div className="flex-shrink-0 w-6 h-6 bg-gradient-to-r from-pink-500 to-pink-600 text-white rounded-full flex items-center justify-center text-sm font-bold">
              {idx + 1}
            </div>
            <p className="text-gray-800">{step}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

// Loading State
function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px]">
      <div className="w-16 h-16 border-4 border-pink-200 border-t-pink-600 rounded-full animate-spin mb-4"></div>
      <p className="text-gray-700">Generating trend convergence analysis...</p>
    </div>
  );
}

// Empty State
function EmptyState({ onConfigureClick }: { onConfigureClick: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
      <svg className="w-24 h-24 text-gray-300 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
      <h3 className="text-xl font-semibold text-gray-800 mb-2">No Analysis Generated Yet</h3>
      <p className="text-gray-600 mb-4">Configure your analysis parameters and generate insights</p>
      <button
        onClick={onConfigureClick}
        className="px-6 py-3 bg-gradient-to-r from-pink-500 to-pink-600 text-white rounded-lg hover:from-pink-600 hover:to-pink-700 transition"
      >
        Configure Analysis
      </button>
    </div>
  );
}

// Main App Component
export default function App() {
  const [isConfigOpen, setIsConfigOpen] = useState(false);
  const {
    data,
    topics,
    profiles,
    models,
    config,
    loading,
    error,
    generateAnalysis,
    updateConfig,
    clearError,
  } = useTrendConvergence();

  const handleGenerate = async () => {
    await generateAnalysis();
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <NavBar onConfigureClick={() => setIsConfigOpen(true)} />

      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Error Display */}
        {error && (
          <div className="mb-6 bg-red-50 border border-red-200 rounded-lg p-4 flex items-start justify-between">
            <div className="flex items-start space-x-3">
              <svg className="w-5 h-5 text-red-600 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
              <div>
                <h4 className="font-semibold text-red-900">Error</h4>
                <p className="text-red-700 text-sm">{error}</p>
              </div>
            </div>
            <button onClick={clearError} className="text-red-600 hover:text-red-800">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        )}

        {/* Content */}
        {loading ? (
          <LoadingState />
        ) : data ? (
          <>
            <StrategicRecommendations data={data} />
            <ExecutiveFramework data={data} />
            <NextSteps data={data} />
          </>
        ) : (
          <EmptyState onConfigureClick={() => setIsConfigOpen(true)} />
        )}
      </main>

      {/* Configuration Modal */}
      <ConfigModal
        isOpen={isConfigOpen}
        onClose={() => setIsConfigOpen(false)}
        config={config}
        topics={topics}
        models={models}
        profiles={profiles}
        onUpdateConfig={updateConfig}
        onGenerate={handleGenerate}
      />
    </div>
  );
}
