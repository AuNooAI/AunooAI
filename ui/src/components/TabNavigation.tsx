/**
 * Tab Navigation Component matching Figma design
 */

interface Tab {
  id: string;
  label: string;
}

interface TabNavigationProps {
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

const tabs: Tab[] = [
  { id: 'strategic-recommendations', label: 'Strategic Recommendations' },
  { id: 'market-signals', label: 'Market Signals & Strategic Risks' },
  { id: 'consensus', label: 'Consensus Analysis' },
  { id: 'impact-timeline', label: 'Impact Timeline' },
  { id: 'future-horizons', label: 'Future Horizons' },
];

export function TabNavigation({ activeTab, onTabChange }: TabNavigationProps) {
  return (
    <div className="flex gap-0 border-b border-gray-200">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`
            px-6 py-3 text-sm font-medium transition-all relative
            ${activeTab === tab.id
              ? 'text-gray-900'
              : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
            }
          `}
        >
          {tab.label}
          {activeTab === tab.id && (
            <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-pink-500"></div>
          )}
        </button>
      ))}
    </div>
  );
}
