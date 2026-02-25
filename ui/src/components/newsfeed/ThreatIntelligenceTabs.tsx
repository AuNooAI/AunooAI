/**
 * ThreatIntelligenceTabs Component
 * Tab navigation for the threat intelligence feature
 */

import {
  LayoutDashboard,
  Map,
  Clock,
  Users,
  Tags,
  GitBranch,
  Lightbulb,
  FileText,
} from 'lucide-react';

export type ThreatIntelTab =
  | 'overview'
  | 'map'
  | 'timeline'
  | 'actors'
  | 'categories'
  | 'analysis'
  | 'insights'
  | 'articles';

interface ThreatIntelligenceTabsProps {
  activeTab: ThreatIntelTab;
  onTabChange: (tab: ThreatIntelTab) => void;
}

const tabs: { id: ThreatIntelTab; label: string; icon: React.ReactNode }[] = [
  { id: 'overview', label: 'Overview', icon: <LayoutDashboard className="w-4 h-4" /> },
  { id: 'map', label: 'Map', icon: <Map className="w-4 h-4" /> },
  { id: 'timeline', label: 'Timeline', icon: <Clock className="w-4 h-4" /> },
  { id: 'actors', label: 'Actors', icon: <Users className="w-4 h-4" /> },
  { id: 'categories', label: 'Categories', icon: <Tags className="w-4 h-4" /> },
  { id: 'analysis', label: 'Analysis', icon: <GitBranch className="w-4 h-4" /> },
  { id: 'insights', label: 'Insights', icon: <Lightbulb className="w-4 h-4" /> },
  { id: 'articles', label: 'Articles', icon: <FileText className="w-4 h-4" /> },
];

export function ThreatIntelligenceTabs({ activeTab, onTabChange }: ThreatIntelligenceTabsProps) {
  return (
    <div className="flex flex-wrap gap-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors ${
            activeTab === tab.id
              ? 'bg-white dark:bg-gray-700 text-red-600 dark:text-red-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
          }`}
        >
          {tab.icon}
          <span className="hidden sm:inline">{tab.label}</span>
        </button>
      ))}
    </div>
  );
}
