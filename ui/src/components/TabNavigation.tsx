/**
 * Tab Navigation Component matching Figma design
 */

import { useRef, useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

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
  {
    id: 'pam',
    label: 'Power, Attention & Money',
    tooltip: 'Track power flows, attention economy, and financial dynamics reshaping the knowledge economy'
  },
];

export function TabNavigation({ activeTab, onTabChange }: TabNavigationProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(false);

  const checkScrollArrows = () => {
    if (scrollRef.current) {
      const { scrollLeft, scrollWidth, clientWidth } = scrollRef.current;
      setShowLeftArrow(scrollLeft > 0);
      setShowRightArrow(scrollLeft < scrollWidth - clientWidth - 1);
    }
  };

  useEffect(() => {
    checkScrollArrows();
    window.addEventListener('resize', checkScrollArrows);
    return () => window.removeEventListener('resize', checkScrollArrows);
  }, []);

  const scroll = (direction: 'left' | 'right') => {
    if (scrollRef.current) {
      const scrollAmount = 200;
      scrollRef.current.scrollBy({
        left: direction === 'left' ? -scrollAmount : scrollAmount,
        behavior: 'smooth'
      });
    }
  };

  return (
    <div className="relative flex items-center">
      {/* Left Arrow */}
      {showLeftArrow && (
        <button
          onClick={() => scroll('left')}
          className="absolute left-0 z-10 h-full px-2 bg-gradient-to-r from-white via-white/90 to-transparent hover:from-gray-100 flex items-center"
        >
          <div className="bg-gray-100 hover:bg-gray-200 rounded-full p-1 shadow-sm border border-gray-200">
            <ChevronLeft className="w-4 h-4 text-gray-600" />
          </div>
        </button>
      )}

      {/* Scrollable Tabs */}
      <div
        ref={scrollRef}
        onScroll={checkScrollArrows}
        className="overflow-x-auto scrollbar-hide flex-1"
      >
        <div className="flex gap-0 border-b border-gray-200 min-w-max">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              title={tab.tooltip}
              className={`
                px-6 py-3 text-sm font-medium transition-all relative whitespace-nowrap
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
      </div>

      {/* Right Arrow */}
      {showRightArrow && (
        <button
          onClick={() => scroll('right')}
          className="absolute right-0 z-10 h-full px-2 bg-gradient-to-l from-white via-white/90 to-transparent hover:from-gray-100 flex items-center"
        >
          <div className="bg-gray-100 hover:bg-gray-200 rounded-full p-1 shadow-sm border border-gray-200">
            <ChevronRight className="w-4 h-4 text-gray-600" />
          </div>
        </button>
      )}
    </div>
  );
}
