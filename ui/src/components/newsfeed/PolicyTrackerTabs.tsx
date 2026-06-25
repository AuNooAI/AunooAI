/**
 * Policy Tracker Tabs Navigation Component
 */

import { LayoutDashboard, Clock, Layers, BarChart3, FileText, Sparkles, Tag } from 'lucide-react';

export type PolicyTab = 'overview' | 'timeline' | 'themes' | 'analysis' | 'insights' | 'categories' | 'articles';

interface PolicyTrackerTabsProps {
  activeTab: PolicyTab;
  onTabChange: (tab: PolicyTab) => void;
}

const tabs: { id: PolicyTab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: 'overview', label: 'Overview', icon: LayoutDashboard },
  { id: 'timeline', label: 'Timeline', icon: Clock },
  { id: 'themes', label: 'Themes', icon: Layers },
  { id: 'analysis', label: 'Analysis', icon: BarChart3 },
  { id: 'insights', label: 'Insights', icon: Sparkles },
  { id: 'categories', label: 'Categories', icon: Tag },
  { id: 'articles', label: 'Articles', icon: FileText },
];

export function PolicyTrackerTabs({ activeTab, onTabChange }: PolicyTrackerTabsProps) {
  return (
    <div className="flex gap-1 border-b border-gray-200 dark:border-gray-700">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;

        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors ${
              isActive
                ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                : 'border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
            }`}
          >
            <Icon className="w-4 h-4" />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
