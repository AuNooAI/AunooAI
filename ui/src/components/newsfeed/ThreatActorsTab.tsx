/**
 * ThreatActorsTab Component
 * Threat actor management and display
 */

import { useState, useEffect, useCallback } from 'react';
import { Users, Shield, Globe, Target, ChevronRight } from 'lucide-react';
import {
  getActors,
  getActorById,
  getActorThreats,
  type ThreatActor,
  type ThreatMapData,
  type ActorType,
  ACTOR_TYPES,
  ACTOR_TYPE_LABELS,
  SEVERITY_COLORS,
} from '../../services/threatIntelligenceApi';

interface ThreatActorsTabProps {
  onThreatClick: (threat: ThreatMapData) => void;
}

export function ThreatActorsTab({ onThreatClick }: ThreatActorsTabProps) {
  const [actors, setActors] = useState<ThreatActor[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedActor, setSelectedActor] = useState<ThreatActor | null>(null);
  const [actorThreats, setActorThreats] = useState<any[]>([]);
  const [loadingThreats, setLoadingThreats] = useState(false);
  const [filterType, setFilterType] = useState<ActorType | ''>('');

  const fetchActors = useCallback(async () => {
    setLoading(true);
    try {
      const result = await getActors({
        actorType: filterType || undefined,
        page: 1,
        pageSize: 50,
        sortBy: 'threat_count',
        sortOrder: 'desc',
      });
      setActors(result.data);
    } catch (error) {
      console.error('Error fetching actors:', error);
    } finally {
      setLoading(false);
    }
  }, [filterType]);

  useEffect(() => {
    fetchActors();
  }, [fetchActors]);

  const handleActorClick = async (actor: ThreatActor) => {
    setSelectedActor(actor);
    setLoadingThreats(true);
    try {
      const result = await getActorThreats(actor.id, 1, 10);
      setActorThreats(result.data);
    } catch (error) {
      console.error('Error fetching actor threats:', error);
    } finally {
      setLoadingThreats(false);
    }
  };

  const getSophisticationColor = (level: string | null) => {
    switch (level) {
      case 'advanced':
        return 'text-red-500 bg-red-50 dark:bg-red-900/20';
      case 'intermediate':
        return 'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20';
      case 'basic':
        return 'text-green-500 bg-green-50 dark:bg-green-900/20';
      default:
        return 'text-gray-500 bg-gray-50 dark:bg-gray-900/20';
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-red-500"></div>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Actor List */}
      <div className="lg:col-span-2 space-y-4">
        {/* Filter */}
        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-500 dark:text-gray-400">Filter by type:</span>
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value as ActorType | '')}
            className="px-3 py-1.5 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
          >
            <option value="">All Types</option>
            {ACTOR_TYPES.map((type) => (
              <option key={type} value={type}>
                {ACTOR_TYPE_LABELS[type]}
              </option>
            ))}
          </select>
        </div>

        {/* Actors Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {actors.map((actor) => (
            <button
              key={actor.id}
              onClick={() => handleActorClick(actor)}
              className={`text-left p-4 rounded-lg border transition-all ${
                selectedActor?.id === actor.id
                  ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                  : 'bg-white dark:bg-gray-800 border-gray-200 dark:border-gray-700 hover:border-red-300 dark:hover:border-red-700'
              }`}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <Users className="w-4 h-4 text-red-500" />
                    <h3 className="font-medium text-gray-900 dark:text-gray-100 truncate">
                      {actor.name}
                    </h3>
                  </div>
                  <div className="flex items-center gap-2 mt-1">
                    <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                      {ACTOR_TYPE_LABELS[actor.actor_type]}
                    </span>
                    {actor.sophistication_level && (
                      <span
                        className={`px-2 py-0.5 text-xs font-medium rounded ${getSophisticationColor(
                          actor.sophistication_level
                        )}`}
                      >
                        {actor.sophistication_level}
                      </span>
                    )}
                  </div>
                </div>
                <ChevronRight className="w-4 h-4 text-gray-400 flex-shrink-0" />
              </div>

              <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
                <div className="flex items-center gap-1 text-gray-500 dark:text-gray-400">
                  <Shield className="w-3 h-3" />
                  {actor.threat_count} threats
                </div>
                {actor.attributed_country_name && (
                  <div className="flex items-center gap-1 text-gray-500 dark:text-gray-400">
                    <Globe className="w-3 h-3" />
                    {actor.attributed_country_name}
                  </div>
                )}
              </div>

              {actor.aliases && actor.aliases.length > 0 && (
                <div className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  Also known as: {actor.aliases.slice(0, 3).join(', ')}
                </div>
              )}
            </button>
          ))}
        </div>

        {actors.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400 py-12">
            No threat actors found.
          </div>
        )}
      </div>

      {/* Actor Details */}
      <div className="lg:col-span-1">
        {selectedActor ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sticky top-4">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
              {selectedActor.name}
            </h3>

            <div className="space-y-4">
              {/* Basic Info */}
              <div className="space-y-2">
                <div className="flex items-center gap-2 text-sm">
                  <span className="text-gray-500 dark:text-gray-400 w-20">Type:</span>
                  <span className="text-gray-900 dark:text-gray-100">
                    {ACTOR_TYPE_LABELS[selectedActor.actor_type]}
                  </span>
                </div>
                {selectedActor.attributed_country_name && (
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-gray-500 dark:text-gray-400 w-20">Origin:</span>
                    <span className="text-gray-900 dark:text-gray-100">
                      {selectedActor.attributed_country_name}
                    </span>
                  </div>
                )}
                {selectedActor.motivation && (
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-gray-500 dark:text-gray-400 w-20">Motivation:</span>
                    <span className="text-gray-900 dark:text-gray-100 capitalize">
                      {selectedActor.motivation}
                    </span>
                  </div>
                )}
              </div>

              {/* Description */}
              {selectedActor.description && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Description
                  </h4>
                  <p className="text-sm text-gray-600 dark:text-gray-400">
                    {selectedActor.description}
                  </p>
                </div>
              )}

              {/* Target Industries */}
              {selectedActor.target_industries && selectedActor.target_industries.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Target Industries
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {selectedActor.target_industries.map((industry) => (
                      <span
                        key={industry}
                        className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded"
                      >
                        {industry}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Known TTPs */}
              {selectedActor.known_ttps && selectedActor.known_ttps.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    MITRE ATT&CK TTPs
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {selectedActor.known_ttps.slice(0, 10).map((ttp) => (
                      <span
                        key={ttp}
                        className="px-2 py-0.5 text-xs bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded font-mono"
                      >
                        {ttp}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Associated Malware */}
              {selectedActor.associated_malware && selectedActor.associated_malware.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Associated Malware
                  </h4>
                  <div className="flex flex-wrap gap-1">
                    {selectedActor.associated_malware.map((malware) => (
                      <span
                        key={malware}
                        className="px-2 py-0.5 text-xs bg-orange-50 dark:bg-orange-900/20 text-orange-700 dark:text-orange-300 rounded"
                      >
                        {malware}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Related Threats */}
              <div>
                <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Related Threats ({selectedActor.threat_count})
                </h4>
                {loadingThreats ? (
                  <div className="flex items-center justify-center py-4">
                    <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-red-500"></div>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {actorThreats.map((threat) => (
                      <div
                        key={threat.id}
                        className="p-2 bg-gray-50 dark:bg-gray-700/50 rounded text-sm"
                      >
                        <div className="font-medium text-gray-900 dark:text-gray-100">
                          {threat.threat_name}
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span
                            className="px-1.5 py-0.5 text-xs rounded text-white"
                            style={{ backgroundColor: SEVERITY_COLORS[threat.severity_level as keyof typeof SEVERITY_COLORS] }}
                          >
                            {threat.severity_level}
                          </span>
                          <span className="text-xs text-gray-500 dark:text-gray-400">
                            {threat.article_count} articles
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-8 text-center">
            <Users className="w-12 h-12 text-gray-300 dark:text-gray-600 mx-auto mb-3" />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Select a threat actor to view details
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
