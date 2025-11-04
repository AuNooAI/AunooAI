/**
 * World Clock Configuration Modal
 */

import { useState, useEffect } from 'react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from './ui/dialog';
import { Button } from './ui/button';
import { X, Plus } from 'lucide-react';

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

const AVAILABLE_TIMEZONES = [
  { timezone: 'America/Los_Angeles', city: 'San Francisco' },
  { timezone: 'America/Denver', city: 'Denver' },
  { timezone: 'America/Chicago', city: 'Chicago' },
  { timezone: 'America/New_York', city: 'New York' },
  { timezone: 'America/Sao_Paulo', city: 'São Paulo' },
  { timezone: 'Europe/London', city: 'London' },
  { timezone: 'Europe/Paris', city: 'Paris' },
  { timezone: 'Europe/Berlin', city: 'Berlin' },
  { timezone: 'Europe/Rome', city: 'Rome' },
  { timezone: 'Europe/Moscow', city: 'Moscow' },
  { timezone: 'Africa/Cairo', city: 'Cairo' },
  { timezone: 'Africa/Johannesburg', city: 'Johannesburg' },
  { timezone: 'Asia/Dubai', city: 'Dubai' },
  { timezone: 'Asia/Kolkata', city: 'Mumbai' },
  { timezone: 'Asia/Singapore', city: 'Singapore' },
  { timezone: 'Asia/Shanghai', city: 'Beijing' },
  { timezone: 'Asia/Tokyo', city: 'Tokyo' },
  { timezone: 'Asia/Seoul', city: 'Seoul' },
  { timezone: 'Australia/Sydney', city: 'Sydney' },
  { timezone: 'Pacific/Auckland', city: 'Auckland' },
];

export function WorldClockConfig({ open, onOpenChange, currentClocks, onSave }: WorldClockConfigProps) {
  const [selectedClocks, setSelectedClocks] = useState<ClockConfig[]>(currentClocks);

  useEffect(() => {
    setSelectedClocks(currentClocks);
  }, [currentClocks]);

  const handleToggleClock = (clock: ClockConfig) => {
    const exists = selectedClocks.some((c) => c.timezone === clock.timezone);
    if (exists) {
      setSelectedClocks(selectedClocks.filter((c) => c.timezone !== clock.timezone));
    } else {
      setSelectedClocks([...selectedClocks, clock]);
    }
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
      <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Configure World Clocks</DialogTitle>
          <DialogDescription>
            Select the time zones you want to display. Currently showing {selectedClocks.length} clocks.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3 mt-4">
          {AVAILABLE_TIMEZONES.map((clock) => {
            const selected = isSelected(clock.timezone);
            return (
              <button
                key={clock.timezone}
                onClick={() => handleToggleClock(clock)}
                className={`flex items-center justify-between px-4 py-3 rounded-lg border-2 transition-all ${
                  selected
                    ? 'border-pink-500 bg-pink-50 text-pink-700'
                    : 'border-gray-200 bg-white text-gray-700 hover:border-pink-200'
                }`}
              >
                <span className="font-medium">{clock.city}</span>
                {selected ? (
                  <X className="w-4 h-4" />
                ) : (
                  <Plus className="w-4 h-4 text-gray-400" />
                )}
              </button>
            );
          })}
        </div>

        <div className="flex justify-end gap-3 mt-6">
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
