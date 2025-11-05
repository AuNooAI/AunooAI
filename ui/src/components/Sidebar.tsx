/**
 * Sidebar Navigation Component matching Figma design
 */

import { Home, Compass, Map, MessageSquare, Settings, Info, Moon } from 'lucide-react';

interface SidebarProps {
  darkMode?: boolean;
}

export function Sidebar({ darkMode = false }: SidebarProps) {
  return (
    <div className="w-44 h-screen bg-white border-r border-gray-200 flex flex-col">
      {/* Logo */}
      <div className="p-6">
        <h1 className="text-pink-500 text-xl font-bold">AUNOOAI</h1>
      </div>

      {/* General Section */}
      <div className="px-4 mb-4">
        <div className="text-xs text-gray-600 mb-2 px-2">General</div>
        <nav className="space-y-1">
          <button className="w-full flex items-center gap-3 px-2 py-2 text-sm text-gray-800 hover:bg-gray-100 rounded-md">
            <Home className="w-4 h-4" />
            <span>Operations HQ</span>
          </button>
          <button className="w-full flex items-center gap-3 px-2 py-2 text-sm text-gray-800 hover:bg-gray-100 rounded-md">
            <Compass className="w-4 h-4" />
            <span>Discover</span>
          </button>
          <button className="w-full flex items-center gap-3 px-2 py-2 text-sm text-gray-800 hover:bg-gray-100 rounded-md bg-gray-100">
            <Map className="w-4 h-4" />
            <span>Explore</span>
          </button>
          <button className="w-full flex items-center gap-3 px-2 py-2 text-sm text-gray-800 hover:bg-gray-100 rounded-md">
            <MessageSquare className="w-4 h-4" />
            <span>Communicate</span>
          </button>
        </nav>
      </div>

      {/* Spacer */}
      <div className="flex-1"></div>

      {/* Support Section */}
      <div className="px-4 mb-4">
        <div className="text-xs text-gray-600 mb-2 px-2">Support</div>
        <nav className="space-y-1">
          <button className="w-full flex items-center gap-3 px-2 py-2 text-sm text-gray-800 hover:bg-gray-100 rounded-md">
            <Settings className="w-4 h-4" />
            <span>Settings</span>
          </button>
          <button className="w-full flex items-center gap-3 px-2 py-2 text-sm text-gray-800 hover:bg-gray-100 rounded-md">
            <Info className="w-4 h-4" />
            <span>App Info</span>
          </button>
        </nav>
      </div>

      {/* Dark Mode Toggle */}
      <div className="px-4 mb-4">
        <button className="w-full flex items-center justify-between px-2 py-2 text-sm text-gray-800">
          <div className="flex items-center gap-3">
            <Moon className="w-4 h-4" />
            <span>Dark Mode</span>
          </div>
          <div className="w-10 h-5 bg-gray-300 rounded-full relative">
            <div className="w-4 h-4 bg-white rounded-full absolute top-0.5 left-0.5"></div>
          </div>
        </button>
      </div>

      {/* User Info */}
      <div className="px-4 mb-4 pb-4 border-t pt-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 bg-orange-500 rounded-md flex items-center justify-center text-white font-bold">
            O
          </div>
          <div className="text-xs">
            <div className="font-medium">Oliver</div>
            <div className="text-gray-600">oliver@email.com</div>
          </div>
        </div>
      </div>
    </div>
  );
}
