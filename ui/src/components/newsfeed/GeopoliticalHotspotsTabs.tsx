/**
 * GeopoliticalHotspotsTabs Component
 * Tab navigation for the geopolitical hotspots feature
 */

import { Globe, Map, Clock, MapPin, Sparkles, Newspaper, BarChart2, Layers } from 'lucide-react';

export type GeopoliticalTab = 'overview' | 'map' | 'timeline' | 'regions' | 'themes' | 'analysis' | 'insights' | 'articles';

interface GeopoliticalHotspotsTabsProps {
  activeTab: GeopoliticalTab;
  onTabChange: (tab: GeopoliticalTab) => void;
}

const tabs: { id: GeopoliticalTab; label: string; icon: React.ElementType }[] = [
  { id: 'overview', label: 'Overview', icon: Globe },
  { id: 'map', label: 'Map', icon: Map },
  { id: 'timeline', label: 'Timeline', icon: Clock },
  { id: 'regions', label: 'Regions', icon: MapPin },
  { id: 'themes', label: 'Themes', icon: Layers },
  { id: 'analysis', label: 'Analysis', icon: BarChart2 },
  { id: 'insights', label: 'Insights', icon: Sparkles },
  { id: 'articles', label: 'Articles', icon: Newspaper },
];

export function GeopoliticalHotspotsTabs({ activeTab, onTabChange }: GeopoliticalHotspotsTabsProps) {
  return (
    <div className="flex items-center gap-1 p-1 bg-gray-100 dark:bg-gray-800 rounded-lg">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = activeTab === tab.id;

        return (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className={`
              flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors
              ${
                isActive
                  ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
              }
            `}
          >
            <Icon className="w-4 h-4" />
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        );
      })}
    </div>
  );
}
