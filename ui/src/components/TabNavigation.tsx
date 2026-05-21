/**
 * Tab Navigation Component matching Figma design
 */

import { useRef, useState, useEffect } from 'react';
import { ChevronLeft, ChevronRight, Settings2, Check, GripVertical } from 'lucide-react';

interface Tab {
  id: string;
  label: string;
  tooltip: string;
}

interface TabNavigationProps {
  activeTab: string;
  onTabChange: (tabId: string) => void;
  hiddenTabs?: Set<string>;
  onToggleTabVisibility?: (tabId: string) => void;
  tabOrder?: string[];
  onReorderTabs?: (newOrder: string[]) => void;
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
    id: 'forecast-tracker',
    label: 'Forecast Tracker',
    tooltip: 'How is the stored Three Horizons forecast tracking against fresh evidence?'
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

export function TabNavigation({ activeTab, onTabChange, hiddenTabs = new Set(), onToggleTabVisibility, tabOrder = [], onReorderTabs }: TabNavigationProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [showLeftArrow, setShowLeftArrow] = useState(false);
  const [showRightArrow, setShowRightArrow] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  // Sort tabs by custom order, then filter out hidden
  const sortedTabs = [...tabs].sort((a, b) => {
    if (tabOrder.length === 0) return 0;
    const indexA = tabOrder.indexOf(a.id);
    const indexB = tabOrder.indexOf(b.id);
    if (indexA === -1 && indexB === -1) return 0;
    if (indexA === -1) return 1;
    if (indexB === -1) return -1;
    return indexA - indexB;
  });

  const visibleTabs = sortedTabs.filter(tab => !hiddenTabs.has(tab.id));

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
  }, [visibleTabs.length]);

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
          {visibleTabs.map((tab) => (
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

// Export tabs list for use in settings
export { tabs };

// Separate component for tab settings dropdown (to be used in header)
interface TabSettingsDropdownProps {
  hiddenTabs: Set<string>;
  onToggleTabVisibility: (tabId: string) => void;
  tabOrder: string[];
  onReorderTabs: (newOrder: string[]) => void;
  activeTab: string;
}

export function TabSettingsDropdown({ hiddenTabs, onToggleTabVisibility, tabOrder, onReorderTabs, activeTab }: TabSettingsDropdownProps) {
  const [showSettings, setShowSettings] = useState(false);
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);

  // Sort tabs by custom order
  const sortedTabs = [...tabs].sort((a, b) => {
    if (tabOrder.length === 0) return 0;
    const indexA = tabOrder.indexOf(a.id);
    const indexB = tabOrder.indexOf(b.id);
    if (indexA === -1 && indexB === -1) return 0;
    if (indexA === -1) return 1;
    if (indexB === -1) return -1;
    return indexA - indexB;
  });

  return (
    <div className="relative">
      <button
        onClick={() => setShowSettings(!showSettings)}
        className="p-2 hover:bg-gray-100 rounded-md flex items-center gap-1 text-gray-700"
        title="Manage dashboard tabs"
      >
        <Settings2 className="w-5 h-5" />
      </button>

      {showSettings && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setShowSettings(false)}
          />
          {/* Dropdown */}
          <div className="absolute right-0 top-full mt-1 w-80 bg-white border border-gray-200 rounded-lg shadow-lg z-50 py-1 max-h-96 overflow-y-auto">
            <div className="px-3 py-2 border-b border-gray-100">
              <h4 className="font-semibold text-gray-900 text-sm">Manage Tabs</h4>
              <p className="text-xs text-gray-500">Drag to reorder, click checkbox to show/hide</p>
            </div>
            {sortedTabs.map((tab, index) => {
              const isVisible = !hiddenTabs.has(tab.id);
              const isActive = tab.id === activeTab;
              return (
                <div
                  key={tab.id}
                  draggable
                  onDragStart={(e) => {
                    setDraggedIndex(index);
                    e.dataTransfer.effectAllowed = 'move';
                    (e.currentTarget as HTMLElement).style.opacity = '0.5';
                  }}
                  onDragEnd={(e) => {
                    (e.currentTarget as HTMLElement).style.opacity = '1';
                    setDraggedIndex(null);
                    setDragOverIndex(null);
                  }}
                  onDragOver={(e) => {
                    e.preventDefault();
                    e.dataTransfer.dropEffect = 'move';
                    setDragOverIndex(index);
                  }}
                  onDrop={(e) => {
                    e.preventDefault();
                    if (draggedIndex !== null && draggedIndex !== index) {
                      const newOrder = sortedTabs.map(t => t.id);
                      const [draggedItem] = newOrder.splice(draggedIndex, 1);
                      newOrder.splice(index, 0, draggedItem);
                      onReorderTabs(newOrder);
                    }
                    setDraggedIndex(null);
                    setDragOverIndex(null);
                  }}
                  className={`flex items-center gap-2 px-3 py-2 transition-colors cursor-grab active:cursor-grabbing ${
                    dragOverIndex === index && draggedIndex !== index
                      ? 'bg-pink-50 border-t-2 border-pink-300'
                      : 'hover:bg-gray-50'
                  } ${draggedIndex === index ? 'opacity-50' : ''}`}
                >
                  <GripVertical className="w-4 h-4 text-gray-500 shrink-0" />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      // Don't allow hiding the active tab
                      if (!isActive || isVisible === false) {
                        onToggleTabVisibility(tab.id);
                      }
                    }}
                    disabled={isActive && isVisible}
                    className={`w-4 h-4 rounded border flex items-center justify-center shrink-0 ${
                      isVisible ? 'bg-pink-500 border-pink-500' : 'border-gray-300'
                    } ${isActive && isVisible ? 'opacity-50 cursor-not-allowed' : ''}`}
                    title={isActive && isVisible ? "Can't hide active tab" : ''}
                  >
                    {isVisible && <Check className="w-3 h-3 text-white" />}
                  </button>
                  <span className={`text-sm flex-1 truncate ${isVisible ? 'text-gray-900' : 'text-gray-500'}`}>
                    {tab.label}
                  </span>
                  {isActive && (
                    <span className="text-xs text-pink-500 shrink-0">active</span>
                  )}
                </div>
              );
            })}
            <div className="px-3 py-2 border-t border-gray-100">
              <p className="text-xs text-gray-500">
                {tabs.length - hiddenTabs.size} of {tabs.length} tabs visible
              </p>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
