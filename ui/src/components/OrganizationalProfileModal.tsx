/**
 * Organizational Profile Modal Component
 */

import { useState } from 'react';
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogPortal, DialogOverlay } from './ui/dialog';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { Textarea } from './ui/textarea';
import { Plus, Edit2, XIcon } from 'lucide-react';
import type { OrganizationalProfile } from '../services/api';
import { cn } from './ui/utils';

interface OrganizationalProfileModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  profiles: OrganizationalProfile[];
  onSave: (profile: Partial<OrganizationalProfile>) => Promise<void>;
}

interface ProfileFormData {
  name: string;
  industry: string;
  organization_type: string;
  risk_tolerance: string;
  innovation_approach: string;
  region: string;
  decision_making_style: string;
  competitive_landscape: string;
  description: string;
  key_concerns: string;
  strategic_priorities: string;
  key_stakeholders: string;
  regulatory_environment: string;
  additional_context: string;
}

const DEFAULT_FORM_DATA: ProfileFormData = {
  name: '',
  industry: '',
  organization_type: '',
  risk_tolerance: '',
  innovation_approach: '',
  region: '',
  decision_making_style: '',
  competitive_landscape: '',
  description: '',
  key_concerns: '',
  strategic_priorities: '',
  key_stakeholders: '',
  regulatory_environment: '',
  additional_context: '',
};

export function OrganizationalProfileModal({
  open,
  onOpenChange,
  profiles,
  onSave,
}: OrganizationalProfileModalProps) {
  const [selectedProfileId, setSelectedProfileId] = useState<string | null>(null);
  const [formData, setFormData] = useState<ProfileFormData>(DEFAULT_FORM_DATA);
  const [isSaving, setIsSaving] = useState(false);

  const handleProfileSelect = (profileId: string) => {
    setSelectedProfileId(profileId);
    const profile = profiles.find((p) => p.id === profileId);
    if (profile) {
      setFormData({
        name: profile.name || '',
        industry: profile.industry || '',
        organization_type: profile.organization_type || '',
        risk_tolerance: profile.risk_tolerance || '',
        innovation_approach: profile.innovation_approach || '',
        region: profile.region || '',
        decision_making_style: profile.decision_making_style || '',
        competitive_landscape: profile.competitive_landscape || '',
        description: profile.description || '',
        key_concerns: profile.key_concerns || '',
        strategic_priorities: profile.strategic_priorities || '',
        key_stakeholders: profile.key_stakeholders || '',
        regulatory_environment: profile.regulatory_environment || '',
        additional_context: profile.additional_context || '',
      });
    }
  };

  const handleNewProfile = () => {
    setSelectedProfileId(null);
    setFormData(DEFAULT_FORM_DATA);
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      await onSave({
        ...formData,
        id: selectedProfileId || undefined,
      });
      onOpenChange(false);
    } catch (error) {
      console.error('Error saving profile:', error);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogPortal>
        <DialogPrimitive.Overlay
          className="fixed inset-0 z-[60] bg-black/50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0"
        />
        <DialogPrimitive.Content
          className={cn(
            "bg-white data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95 fixed top-[50%] left-[50%] z-[60] grid w-full max-w-6xl translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border shadow-lg duration-200 max-h-[90vh] overflow-hidden p-0"
          )}
        >
          <DialogPrimitive.Close className="ring-offset-background focus:ring-ring data-[state=open]:bg-accent data-[state=open]:text-muted-foreground absolute top-4 right-4 z-10 rounded-xs opacity-70 transition-opacity hover:opacity-100 focus:ring-2 focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4">
            <XIcon />
            <span className="sr-only">Close</span>
          </DialogPrimitive.Close>
        <div className="flex h-[90vh]">
          {/* Left Sidebar - Profile List */}
          <div className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col">
            <div className="p-4 border-b border-gray-200">
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold text-sm">Profile</h3>
                <Button
                  size="sm"
                  className="h-7 bg-pink-500 hover:bg-pink-600 text-white text-xs"
                  onClick={handleNewProfile}
                >
                  New +
                </Button>
              </div>
            </div>

            {/* Profile List */}
            <div className="flex-1 overflow-y-auto">
              {profiles.map((profile) => (
                <button
                  key={profile.id}
                  onClick={() => handleProfileSelect(profile.id)}
                  className={`w-full text-left px-4 py-3 border-b border-gray-200 hover:bg-white transition-colors ${
                    selectedProfileId === profile.id ? 'bg-white' : ''
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-sm text-gray-950 mb-0.5">
                        {profile.name}
                      </div>
                      <div className="text-xs text-gray-600 mb-1">
                        {profile.industry} • {profile.organization_type}
                      </div>
                      <div className="text-xs text-gray-700 mb-1">
                        {profile.tags?.join(' • ')}
                      </div>
                      <span className="inline-block text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">
                        Default
                      </span>
                    </div>
                    <Edit2 className="w-3.5 h-3.5 text-pink-500 shrink-0" />
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Right Side - Form */}
          <div className="flex-1 flex flex-col overflow-hidden">
            {/* Header */}
            <DialogHeader className="px-6 py-4 border-b border-gray-200">
              <DialogTitle className="text-xl font-bold">
                {selectedProfileId ? 'Edit Profile: ' : 'New Profile: '}
                {formData.name || 'Untitled'}
              </DialogTitle>
            </DialogHeader>

            {/* Form Content */}
            <div className="flex-1 overflow-y-auto px-6 py-4">
              <div className="space-y-4 max-w-4xl">
                {/* Row 1: Name | Key Concerns */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">
                      Name <span className="text-red-500">*</span>
                    </label>
                    <Input
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      placeholder="Cybersecurity Organization"
                      className="h-9"
                    />
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Key Concerns</label>
                    <Textarea
                      value={formData.key_concerns}
                      onChange={(e) => setFormData({ ...formData, key_concerns: e.target.value })}
                      placeholder="Advanced persistent threats, Zero-day vulnerabilities..."
                      className="min-h-[60px] text-sm resize-none"
                    />
                    <p className="text-xs text-gray-600 mt-0.5">
                      ⓘ Separate multiple priorities with commas
                    </p>
                  </div>
                </div>

                {/* Row 2: Industry | Organization Type */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Industry</label>
                    <Select
                      value={formData.industry}
                      onValueChange={(value) => setFormData({ ...formData, industry: value })}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Cybersecurity" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Cybersecurity">Cybersecurity</SelectItem>
                        <SelectItem value="Financial Services">Financial Services</SelectItem>
                        <SelectItem value="Healthcare">Healthcare</SelectItem>
                        <SelectItem value="Technology">Technology</SelectItem>
                        <SelectItem value="Manufacturing">Manufacturing</SelectItem>
                        <SelectItem value="Retail">Retail</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Organization Type</label>
                    <Input
                      value={formData.organization_type}
                      onChange={(e) =>
                        setFormData({ ...formData, organization_type: e.target.value })
                      }
                      placeholder="security_team"
                      className="h-9"
                    />
                    <p className="text-xs text-gray-600 mt-0.5">
                      ⓘ Separate multiple priorities with commas
                    </p>
                  </div>
                </div>

                {/* Row 3: Risk Tolerance | Strategic Priorities */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Risk Tolerance</label>
                    <Select
                      value={formData.risk_tolerance}
                      onValueChange={(value) => setFormData({ ...formData, risk_tolerance: value })}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Conservative (Low Risk)" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Conservative">Conservative (Low Risk)</SelectItem>
                        <SelectItem value="Moderate">Moderate</SelectItem>
                        <SelectItem value="Aggressive">Aggressive (High Risk)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Strategic Priorities</label>
                    <Textarea
                      value={formData.strategic_priorities}
                      onChange={(e) =>
                        setFormData({ ...formData, strategic_priorities: e.target.value })
                      }
                      placeholder="Threat prevention, Incident response..."
                      className="min-h-[60px] text-sm resize-none"
                    />
                    <p className="text-xs text-gray-600 mt-0.5">
                      ⓘ Separate multiple priorities with commas
                    </p>
                  </div>
                </div>

                {/* Row 4: Innovation Approach | Key Stakeholders */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Innovation Approach</label>
                    <Select
                      value={formData.innovation_approach}
                      onValueChange={(value) =>
                        setFormData({ ...formData, innovation_approach: value })
                      }
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Conservative" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Conservative">Conservative</SelectItem>
                        <SelectItem value="Balanced">Balanced</SelectItem>
                        <SelectItem value="Aggressive">Aggressive</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Key Stakeholders</label>
                    <Textarea
                      value={formData.key_stakeholders}
                      onChange={(e) =>
                        setFormData({ ...formData, key_stakeholders: e.target.value })
                      }
                      placeholder="C-suite executives, IT teams..."
                      className="min-h-[60px] text-sm resize-none"
                    />
                    <p className="text-xs text-gray-600 mt-0.5">
                      ⓘ Separate multiple priorities with commas
                    </p>
                  </div>
                </div>

                {/* Row 5: Region | (empty) */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Region</label>
                    <Select
                      value={formData.region}
                      onValueChange={(value) => setFormData({ ...formData, region: value })}
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Global" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Global">Global</SelectItem>
                        <SelectItem value="North America">North America</SelectItem>
                        <SelectItem value="Europe">Europe</SelectItem>
                        <SelectItem value="Asia Pacific">Asia Pacific</SelectItem>
                        <SelectItem value="Latin America">Latin America</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Regulatory Environment</label>
                    <Textarea
                      value={formData.regulatory_environment}
                      onChange={(e) =>
                        setFormData({ ...formData, regulatory_environment: e.target.value })
                      }
                      placeholder="GDPR, SOC 2, ISO 27001..."
                      className="min-h-[60px] text-sm resize-none"
                    />
                  </div>
                </div>

                {/* Row 6: Decision Making Style | (empty) */}
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="text-sm font-semibold mb-1.5 block">Decision Making Style</label>
                    <Select
                      value={formData.decision_making_style}
                      onValueChange={(value) =>
                        setFormData({ ...formData, decision_making_style: value })
                      }
                    >
                      <SelectTrigger className="h-9">
                        <SelectValue placeholder="Data-Driven" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="Data-Driven">Data-Driven</SelectItem>
                        <SelectItem value="Intuitive">Intuitive</SelectItem>
                        <SelectItem value="Collaborative">Collaborative</SelectItem>
                        <SelectItem value="Hierarchical">Hierarchical</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div></div>
                </div>

                {/* Competitive Landscape */}
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">Competitive Landscape</label>
                  <Textarea
                    value={formData.competitive_landscape}
                    onChange={(e) =>
                      setFormData({ ...formData, competitive_landscape: e.target.value })
                    }
                    placeholder="Nation-state actors, Cybercriminal groups..."
                    className="min-h-[60px] text-sm resize-none"
                  />
                </div>

                {/* Description */}
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">Description</label>
                  <Textarea
                    value={formData.description}
                    onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                    placeholder="Security and risk management team focused on protecting digital assets..."
                    className="min-h-[60px] text-sm resize-none"
                  />
                </div>

                {/* Additional Context */}
                <div>
                  <label className="text-sm font-semibold mb-1.5 block">Additional Context</label>
                  <Textarea
                    value={formData.additional_context}
                    onChange={(e) =>
                      setFormData({ ...formData, additional_context: e.target.value })
                    }
                    placeholder="Zero-trust security approach with emphasis on proactive threat detection..."
                    className="min-h-[80px] text-sm resize-none"
                  />
                </div>
              </div>
            </div>

            {/* Footer Actions */}
            <div className="border-t border-gray-200 px-6 py-4 flex justify-end gap-3">
              <Button
                variant="outline"
                onClick={() => onOpenChange(false)}
                className="px-6 text-pink-500 border-pink-200 hover:bg-pink-50"
              >
                Clear
              </Button>
              <Button
                onClick={handleSave}
                disabled={isSaving || !formData.name}
                className="px-6 bg-pink-500 hover:bg-pink-600"
              >
                {isSaving ? 'Saving...' : 'Save'}
              </Button>
            </div>
          </div>
        </div>
        </DialogPrimitive.Content>
      </DialogPortal>
    </Dialog>
  );
}
