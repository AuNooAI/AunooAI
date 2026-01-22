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
    <div className="flex gap-1 bg-gray-100 dark:bg-gray-700 rounded-lg p-1">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;

        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
              isActive
                ? 'bg-white dark:bg-gray-600 text-gray-900 dark:text-gray-100 shadow-sm'
                : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100'
            }`}
          >
            <Icon className="w-3.5 h-3.5" />
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
