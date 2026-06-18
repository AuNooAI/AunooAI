/**
 * PAM (Power, Attention & Money) Dashboard Application
 *
 * Strategic intelligence dashboard for tracking the three fundamental flows
 * reshaping the knowledge economy, structured around the 5 Key Trends for 2030.
 */

import React, { useState, useEffect } from 'react';
import { PAMDashboard } from './components/pam';
import { SharedNavigation } from './components/SharedNavigation';
import { usePAM } from './hooks/usePAM';
import './components/pam/PAMDashboard.css';
import { AuspexChat } from './components/auspex';

// Types for topics
interface Topic {
  name: string;
  id?: number;
}

const PAMApp: React.FC = () => {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [selectedTopic, setSelectedTopic] = useState<string>('');
  const [loading, setLoading] = useState(true);

  // PAM state - using the hook for state management
  const pam = usePAM();
  const [pamAnalysisType, setPamAnalysisType] = useState<'comprehensive' | 'power' | 'attention' | 'money'>('comprehensive');
  const [pamTimeHorizon, setPamTimeHorizon] = useState<'current' | '6_months' | '1_year' | '5_years' | '2030'>('1_year');
  const [pamTrendFocus, setPamTrendFocus] = useState<string[]>(['T1', 'T2', 'T3', 'T4', 'T5']);
  const [pamDaysBack, setPamDaysBack] = useState(90);
  const [pamArticleLimit, setPamArticleLimit] = useState(100);
  const [pamActiveView, setPamActiveView] = useState<'executive' | 'power' | 'attention' | 'money' | 'scenarios'>('executive');

  // Load topics and cached report on mount
  useEffect(() => {
    loadTopics();
    // Load definitions and cached report
    pam.loadDefinitions();
    pam.loadCachedReport();
  }, []);

  const loadTopics = async () => {
    try {
      const response = await fetch('/api/topics');
      if (response.ok) {
        const data = await response.json();
        if (data.topics) {
          setTopics(data.topics);
          // Auto-select first topic if available
          if (data.topics.length > 0 && !selectedTopic) {
            setSelectedTopic(data.topics[0].name);
          }
        }
      }
    } catch (err) {
      console.error('Failed to load topics:', err);
    } finally {
      setLoading(false);
    }
  };

  // Handle refresh/generate action
  const handleRefresh = () => {
    pam.startGeneration({
      topic: '', // Empty = search across all topics
      analysisType: pamAnalysisType,
      entityType: 'publisher',
      timeHorizon: pamTimeHorizon,
      trendFocus: pamTrendFocus as ('T1' | 'T2' | 'T3' | 'T4' | 'T5')[],
      daysBack: pamDaysBack,
      articleLimit: pamArticleLimit,
      model: 'gpt-5.4-mini',
    });
  };

  return (
    <div className="pam-app">
      <SharedNavigation
        currentPage="pam"
        topics={topics}
        selectedTopic={selectedTopic}
        onTopicChange={setSelectedTopic}
      />

      <main className="pam-main-content">
        {loading ? (
          <div className="pam-loading-container">
            <div className="pam-loading-spinner" />
            <p>Loading PAM Dashboard...</p>
          </div>
        ) : (
          <div className="pam-dashboard-wrapper">
            {/* Simple toolbar for standalone page */}
            <div className="pam-standalone-toolbar">
              <button
                onClick={handleRefresh}
                disabled={pam.isGenerating}
                className="pam-refresh-button"
              >
                {pam.isGenerating ? 'Analyzing...' : 'Generate Analysis'}
              </button>
            </div>
            <PAMDashboard
              topic={selectedTopic}
              isGenerating={pam.isGenerating}
              currentStage={pam.currentStage}
              stageProgress={pam.stageProgress}
              data={pam.data}
              error={pam.error}
              activeView={pamActiveView}
              onViewChange={setPamActiveView}
              onClearError={pam.clearError}
            />
          </div>
        )}
      </main>
      <AuspexChat />
    </div>
  );
};

export default PAMApp;

// Add some app-level styles
const appStyles = `
.pam-app {
  min-height: 100vh;
  background: #f8fafc;
}

.pam-main-content {
  padding-top: 60px; /* Account for fixed navigation */
}

.pam-loading-container {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: calc(100vh - 60px);
  gap: 1rem;
  color: #64748b;
}

.pam-loading-spinner {
  width: 48px;
  height: 48px;
  border: 4px solid #e2e8f0;
  border-top-color: #ec4899;
  border-radius: 50%;
  animation: pam-spin 1s linear infinite;
}

@keyframes pam-spin {
  to { transform: rotate(360deg); }
}

.pam-dashboard-wrapper {
  max-width: 1600px;
  margin: 0 auto;
  padding: 1rem;
}

.pam-standalone-toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 0.5rem 0;
  margin-bottom: 1rem;
}

.pam-refresh-button {
  background: #ec4899;
  color: white;
  border: none;
  padding: 0.75rem 1.5rem;
  border-radius: 0.5rem;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.pam-refresh-button:hover:not(:disabled) {
  background: #db2777;
}

.pam-refresh-button:disabled {
  background: #f9a8d4;
  cursor: not-allowed;
}
`;

// Inject styles
if (typeof document !== 'undefined') {
  const styleSheet = document.createElement('style');
  styleSheet.textContent = appStyles;
  document.head.appendChild(styleSheet);
}
