/**
 * World Clock Configuration Modal
 * Supports any IANA timezone via input field
 */

import { useState, useEffect, useMemo } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { X, Plus, Search } from 'lucide-react';

export interface ClockConfig {
  timezone: string;
  city: string;
}

interface WorldClockConfigProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentClocks: ClockConfig[];
  onSave: (clocks: ClockConfig[]) => void;
}

// Get all IANA timezones from the browser
const getAllTimezones = (): string[] => {
  try {
    // @ts-ignore - Intl.supportedValuesOf is available in modern browsers
    return Intl.supportedValuesOf('timeZone');
  } catch {
    // Fallback for older browsers
    return [
      'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Lagos', 'Africa/Nairobi',
      'America/Anchorage', 'America/Buenos_Aires', 'America/Chicago', 'America/Denver',
      'America/Los_Angeles', 'America/Mexico_City', 'America/New_York', 'America/Sao_Paulo',
      'America/Toronto', 'America/Vancouver', 'Asia/Bangkok', 'Asia/Dubai', 'Asia/Hong_Kong',
      'Asia/Jakarta', 'Asia/Kolkata', 'Asia/Manila', 'Asia/Seoul', 'Asia/Shanghai',
      'Asia/Singapore', 'Asia/Tokyo', 'Australia/Melbourne', 'Australia/Perth',
      'Australia/Sydney', 'Europe/Amsterdam', 'Europe/Berlin', 'Europe/Dublin',
      'Europe/Istanbul', 'Europe/London', 'Europe/Madrid', 'Europe/Moscow',
      'Europe/Paris', 'Europe/Rome', 'Europe/Zurich', 'Pacific/Auckland', 'Pacific/Honolulu'
    ];
  }
};

// Extract city name from timezone string
const getCityFromTimezone = (timezone: string): string => {
  const parts = timezone.split('/');
  const city = parts[parts.length - 1];
  return city.replace(/_/g, ' ');
};

// Validate if a timezone string is valid
const isValidTimezone = (tz: string): boolean => {
  try {
    new Intl.DateTimeFormat('en-US', { timeZone: tz });
    return true;
  } catch {
    return false;
  }
};

export function WorldClockConfig({ open, onOpenChange, currentClocks, onSave }: WorldClockConfigProps) {
  const [selectedClocks, setSelectedClocks] = useState<ClockConfig[]>(currentClocks);
  const [searchQuery, setSearchQuery] = useState('');
  const [customTimezone, setCustomTimezone] = useState('');
  const [error, setError] = useState('');

  const allTimezones = useMemo(() => getAllTimezones(), []);

  useEffect(() => {
    setSelectedClocks(currentClocks);
  }, [currentClocks]);

  // Filter timezones based on search query
  const filteredTimezones = useMemo(() => {
    if (!searchQuery) return allTimezones.slice(0, 50); // Show first 50 by default
    const query = searchQuery.toLowerCase();
    return allTimezones.filter(tz =>
      tz.toLowerCase().includes(query) ||
      getCityFromTimezone(tz).toLowerCase().includes(query)
    ).slice(0, 50);
  }, [allTimezones, searchQuery]);

  const handleAddTimezone = (timezone: string) => {
    if (selectedClocks.some(c => c.timezone === timezone)) {
      return; // Already added
    }
    setSelectedClocks([...selectedClocks, {
      timezone,
      city: getCityFromTimezone(timezone)
    }]);
    setError('');
  };

  const handleAddCustom = () => {
    const tz = customTimezone.trim();
    if (!tz) return;

    if (!isValidTimezone(tz)) {
      setError(`Invalid timezone: "${tz}". Use IANA format like "Europe/London"`);
      return;
    }

    handleAddTimezone(tz);
    setCustomTimezone('');
  };

  const handleRemoveTimezone = (timezone: string) => {
    setSelectedClocks(selectedClocks.filter(c => c.timezone !== timezone));
  };

  const handleSave = () => {
    onSave(selectedClocks);
    onOpenChange(false);
  };

  const isSelected = (timezone: string) => {
    return selectedClocks.some((c) => c.timezone === timezone);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle>Configure World Clocks</DialogTitle>
          <DialogDescription>
            Add any IANA timezone. Currently showing {selectedClocks.length} clocks.
          </DialogDescription>
        </DialogHeader>

        {/* Custom timezone input */}
        <div className="flex gap-2 mt-4">
          <div className="flex-1 relative">
            <input
              type="text"
              value={customTimezone}
              onChange={(e) => { setCustomTimezone(e.target.value); setError(''); }}
              onKeyDown={(e) => e.key === 'Enter' && handleAddCustom()}
              placeholder="Enter timezone (e.g., Europe/London, Asia/Tokyo)"
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500"
              list="timezone-suggestions"
            />
            <datalist id="timezone-suggestions">
              {allTimezones.slice(0, 100).map(tz => (
                <option key={tz} value={tz} />
              ))}
            </datalist>
          </div>
          <Button onClick={handleAddCustom} className="bg-pink-500 hover:bg-pink-600 text-white">
            <Plus className="w-4 h-4 mr-1" /> Add
          </Button>
        </div>
        {error && <p className="text-red-500 text-sm mt-1">{error}</p>}

        {/* Selected clocks */}
        {selectedClocks.length > 0 && (
          <div className="mt-4">
            <h4 className="text-sm font-semibold text-gray-700 mb-2">Selected Clocks:</h4>
            <div className="flex flex-wrap gap-2">
              {selectedClocks.map(clock => (
                <span
                  key={clock.timezone}
                  className="inline-flex items-center gap-1 px-3 py-1 bg-pink-100 text-pink-700 rounded-full text-sm"
                >
                  {clock.city}
                  <button
                    onClick={() => handleRemoveTimezone(clock.timezone)}
                    className="hover:bg-pink-200 rounded-full p-0.5"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Search and browse */}
        <div className="mt-4">
          <div className="relative mb-3">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-gray-500" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search timezones..."
              className="w-full pl-10 pr-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-pink-500"
            />
          </div>
          <div className="overflow-y-auto max-h-[300px] border rounded-lg">
            <div className="grid grid-cols-2 gap-1 p-2">
              {filteredTimezones.map((tz) => {
                const selected = isSelected(tz);
                return (
                  <button
                    key={tz}
                    onClick={() => selected ? handleRemoveTimezone(tz) : handleAddTimezone(tz)}
                    className={`flex items-center justify-between px-3 py-2 rounded-md text-sm transition-all ${
                      selected
                        ? 'bg-pink-500 text-white'
                        : 'bg-gray-50 text-gray-700 hover:bg-pink-50'
                    }`}
                  >
                    <span className="truncate">{getCityFromTimezone(tz)}</span>
                    <span className="text-xs opacity-60 ml-1 truncate">{tz.split('/')[0]}</span>
                  </button>
                );
              })}
            </div>
            {filteredTimezones.length === 0 && (
              <p className="text-gray-500 text-center py-4">No timezones found</p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-4 pt-4 border-t">
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={handleSave}
            className="bg-pink-500 hover:bg-pink-600 text-white"
          >
            Save Changes
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
