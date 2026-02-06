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
  { id: 'map', label: 'Global View', icon: Map },
  { id: 'timeline', label: 'Timeline', icon: Clock },
  { id: 'regions', label: 'Regions', icon: MapPin },
  { id: 'themes', label: 'Themes', icon: Layers },
  { id: 'analysis', label: 'Analysis', icon: BarChart2 },
  { id: 'insights', label: 'Insights', icon: Sparkles },
  { id: 'articles', label: 'Articles', icon: Newspaper },
];

export function GeopoliticalHotspotsTabs({ activeTab, onTabChange }: GeopoliticalHotspotsTabsProps) {
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
