/**
 * Gather App - Automated Data Collection Management
 * React-based replacement for keyword-alerts page
 */

import { useState } from 'react';
import { useGather } from './hooks/useGather';
import { SharedNavigation } from './components/SharedNavigation';
import { GatherHeader } from './components/gather/GatherHeader';
import { KeywordGroupCard } from './components/gather/KeywordGroupCard';
import { KeywordGroupDetailPanel } from './components/gather/KeywordGroupDetailPanel';
import { AutoCollectModal } from './components/gather/AutoCollectModal';
import { ManageKeywordsModal } from './components/gather/ManageKeywordsModal';
import { TestProcessModal } from './components/gather/TestProcessModal';
import { GroupSettingsModal } from './components/gather/GroupSettingsModal';
import { ProcessingStatusBadge } from './components/gather/ProcessingStatusBadge';
import { NotificationBell } from './components/gather/NotificationBell';
import { RSSFeedsTab } from './components/gather/RSSFeedsTab';
import { TrainingStatusTab } from './components/gather/TrainingStatusTab';
import { Alert, AlertDescription } from './components/ui/alert';
import { Loader2, AlertCircle, Plus, Search, Rss, GraduationCap } from 'lucide-react';
import { OnboardingWizard } from './components/onboarding/OnboardingWizard';
import { AuspexChat } from './components/auspex';
import type { KeywordGroupSummary } from './services/gatherApi';
import { getRecentArticlesForGroup, deleteUnscoredArticles } from './services/gatherApi';
import './components/gather/gather.css';

type GatherTab = 'keywords' | 'rss' | 'training';

function GatherApp() {
  const {
    groups,
    keywords,
    settings,
    status,
    relevanceStats,
    groupSummaries,
    availableProviders,
    topics,
    loading,
    error,
    checkingKeywords,
    refresh,
    saveSettings,
    toggleCollection,
    createGroup,
    removeGroup,
    addKeywordToGroup,
    editKeyword,
    removeKeyword,
    checkKeywords,
    clearError,
  } = useGather();

  // Tab state
  const [activeTab, setActiveTab] = useState<GatherTab>('keywords');

  // Panel state
  const [selectedGroup, setSelectedGroup] = useState<KeywordGroupSummary | null>(null);
  const [isPanelOpen, setIsPanelOpen] = useState(false);

  // Modal states
  const [isAutoCollectOpen, setIsAutoCollectOpen] = useState(false);
  const [isManageKeywordsOpen, setIsManageKeywordsOpen] = useState(false);
  const [isTestProcessOpen, setIsTestProcessOpen] = useState(false);
  const [testProcessArticle, setTestProcessArticle] = useState<{ uri: string; groupId: number } | null>(null);
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);
  const [groupSettingsTarget, setGroupSettingsTarget] = useState<{ id: number; name: string } | null>(null);

  // Handle test process for specific article
  const handleTestProcessArticle = (uri: string, groupId: number) => {
    setTestProcessArticle({ uri, groupId });
    setIsTestProcessOpen(true);
  };

  // Handle opening test modal from header - preload a testable article
  const handleOpenTestProcess = async () => {
    // Find first group with articles to get a testable article
    const groupWithArticles = groupSummaries.find(g => g.total_articles > 0);
    if (groupWithArticles) {
      try {
        const articles = await getRecentArticlesForGroup(groupWithArticles.id, 1);
        if (articles.length > 0) {
          setTestProcessArticle({ uri: articles[0].uri, groupId: groupWithArticles.id });
        }
      } catch {
        // If fetch fails, open modal without preload
      }
    }
    setIsTestProcessOpen(true);
  };

  // Handle card click
  const handleCardClick = (group: KeywordGroupSummary) => {
    setSelectedGroup(group);
    setIsPanelOpen(true);
  };

  // Handle panel close
  const handlePanelClose = () => {
    setIsPanelOpen(false);
    setTimeout(() => setSelectedGroup(null), 300); // Clear after animation
  };

  // Handle Update Now
  const handleUpdateNow = async () => {
    const result = await checkKeywords();
    if (result?.success) {
      // Could show a toast notification here
    }
  };

  // Handle auto-collection toggle
  const handleToggleCollection = async () => {
    await toggleCollection();
  };

  // Handle run check for specific group
  const handleRunGroupCheck = async (groupId: number) => {
    const result = await checkKeywords(groupId);
    if (result?.success) {
      refresh();
    }
  };

  // Handle delete group from panel
  const handleDeleteGroup = async (groupId: number) => {
    const success = await removeGroup(groupId);
    if (success) {
      handlePanelClose();
    }
  };

  // Handle delete unscored articles for a group
  const handleDeleteUnscored = async (groupId: number) => {
    if (!confirm('Delete all unscored articles for this group? This cannot be undone.')) {
      return;
    }
    try {
      const result = await deleteUnscoredArticles(groupId);
      if (result.success) {
        refresh();
      }
    } catch (err) {
      console.error('Failed to delete unscored articles:', err);
    }
  };

  // Handle opening group settings modal
  const handleOpenGroupSettings = (groupId: number) => {
    const group = groupSummaries.find(g => g.id === groupId);
    if (group) {
      setGroupSettingsTarget({ id: group.id, name: group.name });
    }
  };

  if (loading) {
    return (
      <div className="gather-app">
        <div className="gather-layout">
          <SharedNavigation currentPage="gather" onTopicEditorClick={() => setIsManageKeywordsOpen(true)} />
          <div className="gather-loading">
            <Loader2 className="gather-loading-spinner" />
            <p>Loading Gather...</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="gather-app">
      <div className="gather-layout">
        <SharedNavigation currentPage="gather" onTopicEditorClick={() => setIsManageKeywordsOpen(true)} />

        <div className="gather-content-area">
          {/* Top Header Bar */}
          <div className="gather-top-bar">
            <div className="gather-top-bar-left">
              <span className="gather-top-bar-title">Gather</span>
              <span className="gather-top-bar-separator">/</span>
              <span className="gather-top-bar-subtitle">Automated Data Collection</span>
              <ProcessingStatusBadge />
            </div>
            <div className="gather-top-bar-right">
              <NotificationBell />
              <button
                className="gather-top-bar-setup-btn"
                onClick={() => setIsOnboardingOpen(true)}
              >
                Set up topic
                <Plus className="w-4 h-4" />
              </button>
            </div>
          </div>

          <main className="gather-main">
            <GatherHeader
          status={status}
          checkingKeywords={checkingKeywords}
          onToggleCollection={handleToggleCollection}
          onUpdateNow={handleUpdateNow}
          onOpenAutoCollect={() => setIsAutoCollectOpen(true)}
          onOpenManageKeywords={() => setIsManageKeywordsOpen(true)}
          onTestProcess={handleOpenTestProcess}
        />

        {/* Tab Navigation */}
        <div className="gather-tab-navigation">
          <button
            className={`gather-tab-btn ${activeTab === 'keywords' ? 'active' : ''}`}
            onClick={() => setActiveTab('keywords')}
          >
            <Search className="w-4 h-4" />
            Keyword Groups
          </button>
          <button
            className={`gather-tab-btn ${activeTab === 'rss' ? 'active' : ''}`}
            onClick={() => setActiveTab('rss')}
          >
            <Rss className="w-4 h-4" />
            RSS Feeds
          </button>
          <button
            className={`gather-tab-btn ${activeTab === 'training' ? 'active' : ''}`}
            onClick={() => setActiveTab('training')}
          >
            <GraduationCap className="w-4 h-4" />
            Training
          </button>
        </div>

        {/* Error Alert */}
        {error && (
          <Alert variant="destructive" className="gather-error-alert">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>
              {error}
              <button onClick={clearError} className="gather-error-dismiss">
                Dismiss
              </button>
            </AlertDescription>
          </Alert>
        )}

        {/* Tab Content */}
        {activeTab === 'keywords' && (
          /* Keyword Group Cards Grid */
          <div className="gather-cards-grid">
            {groupSummaries.length === 0 ? (
              <div className="gather-empty-state">
                <div className="gather-empty-icon">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                </div>
                <h3>No keyword groups yet</h3>
                <p>Create keyword groups to start collecting articles automatically.</p>
                <button
                  onClick={() => setIsManageKeywordsOpen(true)}
                  className="gather-empty-cta"
                >
                  Create First Group
                </button>
              </div>
            ) : (
              groupSummaries.map(group => (
                <KeywordGroupCard
                  key={group.id}
                  group={group}
                  onClick={() => handleCardClick(group)}
                  onDeleteUnscored={handleDeleteUnscored}
                  onSettingsClick={handleOpenGroupSettings}
                />
              ))
            )}
          </div>
        )}

        {activeTab === 'rss' && (
          /* RSS Feeds Tab */
          <RSSFeedsTab topics={topics} />
        )}

        {activeTab === 'training' && (
          /* Training Status Tab */
          <TrainingStatusTab />
        )}
          </main>
        </div>
      </div>

      {/* Detail Panel (Slide-out Sheet) */}
      <KeywordGroupDetailPanel
        group={selectedGroup}
        keywords={keywords.filter(k => k.group_id === selectedGroup?.id)}
        keywordStats={relevanceStats.filter(s => s.group_id === selectedGroup?.id)}
        isOpen={isPanelOpen}
        onClose={handlePanelClose}
        onRunCheck={handleRunGroupCheck}
        onDeleteGroup={handleDeleteGroup}
        onAddKeyword={addKeywordToGroup}
        onEditKeyword={editKeyword}
        onDeleteKeyword={removeKeyword}
        checkingKeywords={checkingKeywords}
        onTestProcessArticle={handleTestProcessArticle}
      />

      {/* Auto-Collect Settings Modal */}
      <AutoCollectModal
        isOpen={isAutoCollectOpen}
        onClose={() => setIsAutoCollectOpen(false)}
        settings={settings}
        availableProviders={availableProviders || []}
        onSave={saveSettings}
      />

      {/* Manage Keywords Modal */}
      <ManageKeywordsModal
        isOpen={isManageKeywordsOpen}
        onClose={() => setIsManageKeywordsOpen(false)}
        groups={groups}
        keywords={keywords}
        topics={topics}
        onCreateGroup={createGroup}
        onDeleteGroup={removeGroup}
        onAddKeyword={addKeywordToGroup}
        onEditKeyword={editKeyword}
        onDeleteKeyword={removeKeyword}
      />

      {/* Test Process Modal */}
      <TestProcessModal
        isOpen={isTestProcessOpen}
        onClose={() => {
          setIsTestProcessOpen(false);
          setTestProcessArticle(null);
        }}
        groups={groups}
        onSuccess={refresh}
        preloadArticle={testProcessArticle}
      />

      {/* Group Settings Modal */}
      {groupSettingsTarget && (
        <GroupSettingsModal
          isOpen={!!groupSettingsTarget}
          onClose={() => setGroupSettingsTarget(null)}
          groupId={groupSettingsTarget.id}
          groupName={groupSettingsTarget.name}
          onSaved={refresh}
        />
      )}

      {/* Onboarding Wizard */}
      <OnboardingWizard
        open={isOnboardingOpen}
        onOpenChange={setIsOnboardingOpen}
      />
      <AuspexChat />
    </div>
  );
}

export default GatherApp;
