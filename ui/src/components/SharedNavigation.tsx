/**
 * Shared Navigation - Used across all pages
 * Comprehensive menu matching Figma design
 */

import { useState, useEffect } from 'react';
import {
  Home, Search, Settings, Info, Moon,
  ChevronDown, User, LogOut, TrendingUp, BarChart3, Scale,
  Wand2, Clock, Download, Sliders, Sparkles, FolderPlus,
  Brain, BarChart, Edit, Database as DatabaseIcon, Heart,
  Book, MessageSquare, Chrome, Compass
} from 'lucide-react';

interface SharedNavigationProps {
  currentPage: 'health' | 'anticipate' | 'investigate' | 'gather';
}

interface UserInfo {
  username: string;
  email: string;
}

export function SharedNavigation({ currentPage }: SharedNavigationProps) {
  const [expandedSections, setExpandedSections] = useState<{[key: string]: boolean}>({});
  const [userInfo, setUserInfo] = useState<UserInfo>({ username: 'User', email: 'user@example.com' });

  useEffect(() => {
    // Fetch user info from API
    fetch('/api/users/me')
      .then(res => res.json())
      .then(data => {
        setUserInfo({
          username: data.username || 'User',
          email: data.email || 'user@example.com'
        });
      })
      .catch(err => {
        console.error('Failed to fetch user info:', err);
      });
  }, []);

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }));
  };

  return (
    <div className="w-64 bg-white shadow-lg flex flex-col border-r border-gray-200 overflow-y-auto">
      {/* Logo/Brand */}
      <div className="p-6 border-b border-gray-200">
        <h2 className="text-lg font-semibold text-pink-500 tracking-wide">AUNOOAI</h2>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-3 py-4">
        {/* General Section */}
        <div className="mb-4">
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 mb-2">
            General
          </div>
          <ul className="space-y-0.5">
            {/* Operations HQ */}
            <li>
              <a
                href="/"
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all ${
                  currentPage === 'health'
                    ? 'bg-pink-50 text-pink-600'
                    : 'text-gray-800 hover:bg-gray-50 hover:text-pink-600'
                }`}
              >
                <Home className="w-4.5 h-4.5" />
                <span>Operations HQ</span>
              </a>
            </li>

            {/* Anticipate */}
            <li>
              <a
                href="/trend-convergence"
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all ${
                  currentPage === 'anticipate'
                    ? 'bg-pink-50 text-pink-600'
                    : 'text-gray-800 hover:bg-gray-50 hover:text-pink-600'
                }`}
              >
                <TrendingUp className="w-4.5 h-4.5" />
                <span>Anticipate</span>
              </a>
            </li>

            {/* Explore */}
            <li>
              <a
                href="/news-feed-v2"
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all ${
                  currentPage === 'investigate'
                    ? 'bg-pink-50 text-pink-600'
                    : 'text-gray-800 hover:bg-gray-50 hover:text-pink-600'
                }`}
              >
                <Search className="w-4.5 h-4.5" />
                <span>Explore</span>
              </a>
            </li>

            {/* Gather */}
            <li>
              <a
                href="/keyword-alerts"
                className={`flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all ${
                  currentPage === 'gather'
                    ? 'bg-pink-50 text-pink-600'
                    : 'text-gray-800 hover:bg-gray-50 hover:text-pink-600'
                }`}
              >
                <Download className="w-4.5 h-4.5" />
                <span>Gather</span>
              </a>
            </li>
          </ul>
        </div>

        {/* Support Section */}
        <div>
          <div className="text-xs font-semibold text-gray-500 uppercase tracking-wider px-3 mb-2 mt-2">
            Support
          </div>
          <ul className="space-y-0.5">
            {/* Settings (Expandable) */}
            <li>
              <button
                onClick={() => toggleSection('settings')}
                className="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-md text-sm transition-all text-gray-800 hover:bg-gray-50 hover:text-pink-600"
              >
                <div className="flex items-center gap-3">
                  <Settings className="w-4.5 h-4.5" />
                  <span>Settings</span>
                </div>
                <ChevronDown className={`w-3 h-3 transition-transform ${expandedSections.settings ? 'rotate-180' : ''}`} />
              </button>
              {expandedSections.settings && (
                <ul className="mt-1 space-y-0.5">
                  <li>
                    <a href="/config" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <Sliders className="w-3.5 h-3.5" />
                      <span className="text-xs">App Configuration</span>
                    </a>
                  </li>
                  <li>
                    <a href="/trend-convergence?onboarding=true" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <Sparkles className="w-3.5 h-3.5" />
                      <span className="text-xs">AI-guided Topic Setup</span>
                    </a>
                  </li>
                  <li>
                    <a href="/create_topic" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <FolderPlus className="w-3.5 h-3.5" />
                      <span className="text-xs">Topic Editor</span>
                    </a>
                  </li>
                  <li>
                    <a href="/promptmanager" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <Brain className="w-3.5 h-3.5" />
                      <span className="text-xs">Prompt Engineering</span>
                    </a>
                  </li>
                  <li>
                    <a href="/model-bias-arena" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <Scale className="w-3.5 h-3.5" />
                      <span className="text-xs">Model Bias Arena</span>
                    </a>
                  </li>
                  <li>
                    <a href="/vector-analysis-improved" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <BarChart className="w-3.5 h-3.5" />
                      <span className="text-xs">Exploratory Analysis</span>
                    </a>
                  </li>
                  <li>
                    <a href="/database-editor" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <Edit className="w-3.5 h-3.5" />
                      <span className="text-xs">Database Editor</span>
                    </a>
                  </li>
                  <li>
                    <a href="/analytics" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <DatabaseIcon className="w-3.5 h-3.5" />
                      <span className="text-xs">Analytics</span>
                    </a>
                  </li>
                </ul>
              )}
            </li>

            {/* App Info (Expandable) */}
            <li>
              <button
                onClick={() => toggleSection('appInfo')}
                className="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-md text-sm transition-all text-gray-800 hover:bg-gray-50 hover:text-pink-600"
              >
                <div className="flex items-center gap-3">
                  <Info className="w-4.5 h-4.5" />
                  <span>App Info</span>
                </div>
                <ChevronDown className={`w-3 h-3 transition-transform ${expandedSections.appInfo ? 'rotate-180' : ''}`} />
              </button>
              {expandedSections.appInfo && (
                <ul className="mt-1 space-y-0.5">
                  <li>
                    <a href="/health/dashboard" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <Heart className="w-3.5 h-3.5" />
                      <span className="text-xs">System Health</span>
                    </a>
                  </li>
                  <li>
                    <a href="https://aunoo-ai.gitbook.io/aunoo-ai-kb" target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <Book className="w-3.5 h-3.5" />
                      <span className="text-xs">Knowledge Base</span>
                    </a>
                  </li>
                  <li>
                    <a href="https://discord.gg/hEUNYDm5KH" target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <MessageSquare className="w-3.5 h-3.5" />
                      <span className="text-xs">Discord Community</span>
                    </a>
                  </li>
                  <li>
                    <a href="https://chromewebstore.google.com/detail/aunoo-ai-chrome-browser-e/fjgiomiceklnoaefnhliablhgoodceji" target="_blank" rel="noopener noreferrer" className="flex items-center gap-3 pl-10 pr-3 py-2 rounded-md text-sm text-gray-700 hover:bg-gray-50 hover:text-pink-600 transition-all">
                      <Chrome className="w-3.5 h-3.5" />
                      <span className="text-xs">Chrome Extension</span>
                    </a>
                  </li>
                </ul>
              )}
            </li>

            {/* Dark Mode */}
            <li>
              <button
                className="w-full flex items-center justify-between gap-3 px-3 py-2.5 rounded-md text-sm transition-all text-gray-800 hover:bg-gray-50 hover:text-pink-600"
                onClick={() => {/* Dark mode toggle handler */}}
              >
                <div className="flex items-center gap-3">
                  <Moon className="w-4.5 h-4.5" />
                  <span>Dark Mode</span>
                </div>
                <div className="relative w-10 h-5 bg-gray-200 rounded-full cursor-pointer transition-colors">
                  <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform"></div>
                </div>
              </button>
            </li>
          </ul>
        </div>
      </nav>

      {/* User Profile Footer */}
      <div className="p-4 border-t border-gray-200 bg-gray-50 flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-pink-500 flex items-center justify-center text-white text-sm">
          <User className="w-4 h-4" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-gray-800 truncate">{userInfo.username}</div>
          <div className="text-xs text-gray-600 truncate">{userInfo.email}</div>
        </div>
        <a href="/logout" className="w-8 h-8 rounded-md flex items-center justify-center text-gray-700 hover:bg-red-50 hover:text-red-600 transition-all">
          <LogOut className="w-4 h-4" />
        </a>
      </div>
    </div>
  );
}
