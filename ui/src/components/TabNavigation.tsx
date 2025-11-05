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
    <div className="bg-gray-100 rounded-lg p-1 flex gap-1">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`
            px-4 py-2 text-sm font-medium rounded-md transition-colors
            ${activeTab === tab.id
              ? 'bg-white text-gray-950 shadow-sm'
              : 'text-gray-700 hover:text-gray-950'
            }
          `}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
