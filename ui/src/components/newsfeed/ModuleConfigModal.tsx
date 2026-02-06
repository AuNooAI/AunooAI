import React from 'react';
import { Globe, Scale, Microscope, Info } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '../ui/dialog';
import { Switch } from '../ui/switch';
import type { ModuleInfo } from '../../hooks/useModules';

const ICON_MAP: Record<string, React.ElementType> = {
  Globe,
  Scale,
  Microscope,
};

interface ModuleConfigModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modules: ModuleInfo[];
  onToggle: (moduleId: string, enabled: boolean) => void;
}

export function ModuleConfigModal({ open, onOpenChange, modules, onToggle }: ModuleConfigModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md overflow-hidden">
        <DialogHeader>
          <DialogTitle>Analysis Modules</DialogTitle>
          <DialogDescription>
            Enable or disable optional analysis modules.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 mt-2 overflow-hidden">
          {modules.map((m) => {
            const Icon = ICON_MAP[m.tab_icon || ''] || Globe;
            return (
              <div
                key={m.id}
                className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 dark:border-gray-700"
              >
                <div className="shrink-0 w-8 h-8 rounded-md bg-gray-100 dark:bg-gray-700 flex items-center justify-center">
                  <Icon className="w-4 h-4 text-gray-600 dark:text-gray-300" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium text-gray-900 dark:text-gray-100 truncate">
                    {m.name}
                  </p>
                  {m.description && (
                    <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                      {m.description}
                    </p>
                  )}
                </div>
                <Switch
                  className="shrink-0"
                  checked={m.enabled}
                  onCheckedChange={(checked) => onToggle(m.id, checked)}
                />
              </div>
            );
          })}
        </div>

        <div className="flex items-start gap-2 mt-4 p-3 rounded-md bg-blue-50 dark:bg-blue-900/20 text-xs text-blue-700 dark:text-blue-300">
          <Info className="w-4 h-4 shrink-0 mt-0.5" />
          <span>
            Tab visibility updates immediately. Background tasks require a service restart to fully stop.
          </span>
        </div>
      </DialogContent>
    </Dialog>
  );
}
