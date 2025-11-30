/**
 * Tab Navigation Component matching Figma design
 */

interface Tab {
  id: string;
  label: string;
  tooltip: string;
}

interface TabNavigationProps {
  activeTab: string;
  onTabChange: (tabId: string) => void;
}

const tabs: Tab[] = [
  {
    id: 'strategic-recommendations',
    label: 'Strategic Recommendations',
    tooltip: 'Actionable strategic insights across near, mid, and long-term horizons'
  },
  {
    id: 'market-signals',
    label: 'Market Signals & Strategic Risks',
    tooltip: 'Identify emerging trends, disruption scenarios, and strategic opportunities'
  },
  {
    id: 'consensus',
    label: 'Consensus Analysis',
    tooltip: 'Analyze convergent themes and identify areas of agreement across sources'
  },
  {
    id: 'impact-timeline',
    label: 'Impact Timeline',
    tooltip: 'Visualize key impacts and developments over time'
  },
  {
    id: 'future-horizons',
    label: 'Future Horizons',
    tooltip: 'Explore long-term scenarios and future possibilities'
  },
  {
    id: 'extreme-outliers',
    label: 'Extreme Outliers',
    tooltip: 'Black Swan events, Contrarian analysis, and Wild Card futures'
  },
  {
    id: 'focus-group',
    label: 'Focus Group',
    tooltip: 'Discover stakeholder personas with rich psychographic profiles from article content'
  },
  {
    id: 'executive-briefing',
    label: 'Executive Briefing',
    tooltip: 'Persona-tailored executive briefing with strategic analysis and action items'
  },
  {
    id: 'intelligence-brief',
    label: 'Situation Assessment',
    tooltip: '24-hour strategic intelligence scan with BBC/Wiley quality standards'
  },
  {
    id: 'newsletter',
    label: 'Newsletter',
    tooltip: 'Generate professional newsletters with curated headlines, analysis, and market insights'
  },
];

export function TabNavigation({ activeTab, onTabChange }: TabNavigationProps) {
  return (
    <div className="flex gap-0 border-b border-gray-200">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          title={tab.tooltip}
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
