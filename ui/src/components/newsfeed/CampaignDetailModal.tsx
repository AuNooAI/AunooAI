import React from 'react';
import { X, Globe, Shield, Calendar, Target, AlertTriangle } from 'lucide-react';
import type { Campaign } from '../../services/threatIntelligenceApi';

interface CampaignDetailModalProps {
  campaign: Campaign;
  onClose: () => void;
  onViewArticles?: (campaignId: number) => void;
}

export function CampaignDetailModal({ campaign, onClose, onViewArticles }: CampaignDetailModalProps) {
  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-red-500" />
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
              {campaign.name}
            </h2>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded">
            <X className="w-5 h-5 text-gray-500" />
          </button>
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          {campaign.description && (
            <p className="text-sm text-gray-700 dark:text-gray-300">{campaign.description}</p>
          )}

          <div className="grid grid-cols-2 gap-4">
            {/* Status */}
            <div className="flex items-center gap-2 text-sm">
              <AlertTriangle className="w-4 h-4 text-yellow-500" />
              <span className="text-gray-500 dark:text-gray-400">Status:</span>
              <span className={`font-medium ${campaign.is_active ? 'text-red-600' : 'text-green-600'}`}>
                {campaign.is_active ? 'Active' : 'Inactive'}
              </span>
            </div>

            {/* Threat Actor */}
            {campaign.threat_actor_name && (
              <div className="flex items-center gap-2 text-sm">
                <Target className="w-4 h-4 text-purple-500" />
                <span className="text-gray-500 dark:text-gray-400">Actor:</span>
                <span className="font-medium text-gray-900 dark:text-gray-100">{campaign.threat_actor_name}</span>
              </div>
            )}

            {/* Dates */}
            {campaign.start_date && (
              <div className="flex items-center gap-2 text-sm">
                <Calendar className="w-4 h-4 text-blue-500" />
                <span className="text-gray-500 dark:text-gray-400">Period:</span>
                <span className="text-gray-900 dark:text-gray-100">
                  {campaign.start_date}{campaign.end_date ? ` — ${campaign.end_date}` : ' — Present'}
                </span>
              </div>
            )}

            {/* Counts */}
            <div className="flex items-center gap-2 text-sm">
              <span className="text-gray-500 dark:text-gray-400">Threats:</span>
              <span className="font-medium text-gray-900 dark:text-gray-100">{campaign.threat_count}</span>
              <span className="text-gray-400 mx-1">|</span>
              <span className="text-gray-500 dark:text-gray-400">Articles:</span>
              <span className="font-medium text-gray-900 dark:text-gray-100">{campaign.article_count}</span>
            </div>
          </div>

          {/* Target Countries */}
          {campaign.target_countries && campaign.target_countries.length > 0 && (
            <div>
              <div className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400 mb-2">
                <Globe className="w-4 h-4" />
                Target Countries
              </div>
              <div className="flex flex-wrap gap-1">
                {campaign.target_countries.map((country) => (
                  <span key={country} className="px-2 py-0.5 text-xs bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 rounded-full">
                    {country}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Target Industries */}
          {campaign.target_industries && campaign.target_industries.length > 0 && (
            <div>
              <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">Target Industries</div>
              <div className="flex flex-wrap gap-1">
                {campaign.target_industries.map((industry) => (
                  <span key={industry} className="px-2 py-0.5 text-xs bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-300 rounded-full">
                    {industry}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Techniques */}
          {campaign.techniques_used && campaign.techniques_used.length > 0 && (
            <div>
              <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">MITRE ATT&CK Techniques</div>
              <div className="flex flex-wrap gap-1">
                {campaign.techniques_used.map((technique) => (
                  <span key={technique} className="px-2 py-0.5 text-xs bg-red-100 dark:bg-red-900/30 text-red-800 dark:text-red-300 rounded-full font-mono">
                    {technique}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Malware */}
          {campaign.malware_used && campaign.malware_used.length > 0 && (
            <div>
              <div className="text-sm text-gray-500 dark:text-gray-400 mb-2">Malware</div>
              <div className="flex flex-wrap gap-1">
                {campaign.malware_used.map((malware) => (
                  <span key={malware} className="px-2 py-0.5 text-xs bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-300 rounded-full">
                    {malware}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end gap-2 p-4 border-t border-gray-200 dark:border-gray-700">
          {onViewArticles && (
            <button
              onClick={() => onViewArticles(campaign.id)}
              className="px-3 py-1.5 text-sm bg-red-600 hover:bg-red-700 text-white rounded-lg"
            >
              View Articles
            </button>
          )}
          <button
            onClick={onClose}
            className="px-3 py-1.5 text-sm bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-800 dark:text-gray-200 rounded-lg"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
