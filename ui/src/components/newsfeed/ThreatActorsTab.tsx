/**
 * ThreatActorsTab Component
 * Threat actor management and display
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Users,
  Shield,
  Globe,
  Target,
  ChevronRight,
  Calendar,
  FileText,
  MapPin,
  Clock,
  ExternalLink,
  LayoutGrid,
  List,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
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
  onActorArticlesClick?: (actor: ThreatActor) => void;
}

type ViewMode = 'cards' | 'table';
type GroupBy = 'none' | 'type' | 'country';

export function ThreatActorsTab({ onThreatClick, onActorArticlesClick }: ThreatActorsTabProps) {
  const [actors, setActors] = useState<ThreatActor[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedActor, setSelectedActor] = useState<ThreatActor | null>(null);
  const [actorThreats, setActorThreats] = useState<any[]>([]);
  const [loadingThreats, setLoadingThreats] = useState(false);
  const [filterType, setFilterType] = useState<ActorType | ''>('');
  const [viewMode, setViewMode] = useState<ViewMode>('cards');
  const [groupBy, setGroupBy] = useState<GroupBy>('none');
  const [sortColumn, setSortColumn] = useState<'name' | 'threat_count' | 'article_count'>('threat_count');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');

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

  // Sort actors
  const sortedActors = [...actors].sort((a, b) => {
    let aVal: any, bVal: any;
    switch (sortColumn) {
      case 'name':
        aVal = a.name.toLowerCase();
        bVal = b.name.toLowerCase();
        break;
      case 'threat_count':
        aVal = a.threat_count;
        bVal = b.threat_count;
        break;
      case 'article_count':
        aVal = a.article_count;
        bVal = b.article_count;
        break;
      default:
        aVal = a.threat_count;
        bVal = b.threat_count;
    }
    if (sortDirection === 'asc') {
      return aVal > bVal ? 1 : -1;
    }
    return aVal < bVal ? 1 : -1;
  });

  // Group actors
  const groupedActors = (): Map<string, ThreatActor[]> => {
    if (groupBy === 'none') {
      return new Map([['all', sortedActors]]);
    }

    const groups = new Map<string, ThreatActor[]>();
    sortedActors.forEach((actor) => {
      let key: string;
      if (groupBy === 'type') {
        key = ACTOR_TYPE_LABELS[actor.actor_type] || actor.actor_type;
      } else if (groupBy === 'country') {
        key = actor.attributed_country_name || 'Unknown';
      } else {
        key = 'all';
      }
      if (!groups.has(key)) {
        groups.set(key, []);
      }
      groups.get(key)!.push(actor);
    });

    // Sort groups by count
    return new Map([...groups.entries()].sort((a, b) => b[1].length - a[1].length));
  };

  const handleSort = (column: typeof sortColumn) => {
    if (sortColumn === column) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  };

  const SortIcon = ({ column }: { column: typeof sortColumn }) => {
    if (sortColumn !== column) return null;
    return sortDirection === 'asc' ? (
      <ChevronUp className="w-3 h-3" />
    ) : (
      <ChevronDown className="w-3 h-3" />
    );
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
        {/* Controls */}
        <div className="flex flex-wrap items-center gap-3">
          {/* Filter by type */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">Type:</span>
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

          {/* Group by */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500 dark:text-gray-400">Group:</span>
            <select
              value={groupBy}
              onChange={(e) => setGroupBy(e.target.value as GroupBy)}
              className="px-3 py-1.5 text-sm bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-red-500"
            >
              <option value="none">None</option>
              <option value="type">By Type</option>
              <option value="country">By Country</option>
            </select>
          </div>

          {/* View mode toggle */}
          <div className="flex items-center border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
            <button
              onClick={() => setViewMode('cards')}
              className={`p-1.5 ${
                viewMode === 'cards'
                  ? 'bg-red-500 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
              title="Card View"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`p-1.5 ${
                viewMode === 'table'
                  ? 'bg-red-500 text-white'
                  : 'bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400 hover:bg-gray-50 dark:hover:bg-gray-700'
              }`}
              title="Table View"
            >
              <List className="w-4 h-4" />
            </button>
          </div>

          {/* Count */}
          <span className="text-sm text-gray-500 dark:text-gray-400 ml-auto">
            {actors.length} actors
          </span>
        </div>

        {/* Actors Display */}
        {viewMode === 'table' ? (
          /* Table View */
          <div className="space-y-4">
            {Array.from(groupedActors().entries()).map(([groupName, groupActors]) => (
              <div key={groupName}>
                {groupBy !== 'none' && (
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                    {groupName}
                    <span className="text-xs text-gray-500 dark:text-gray-400">({groupActors.length})</span>
                  </h4>
                )}
                <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                  <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                    <thead className="bg-gray-50 dark:bg-gray-900">
                      <tr>
                        <th
                          className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-700 dark:hover:text-gray-200"
                          onClick={() => handleSort('name')}
                        >
                          <div className="flex items-center gap-1">
                            Name
                            <SortIcon column="name" />
                          </div>
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                          Type
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                          Origin
                        </th>
                        <th
                          className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-700 dark:hover:text-gray-200"
                          onClick={() => handleSort('threat_count')}
                        >
                          <div className="flex items-center gap-1">
                            Threats
                            <SortIcon column="threat_count" />
                          </div>
                        </th>
                        <th
                          className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:text-gray-700 dark:hover:text-gray-200"
                          onClick={() => handleSort('article_count')}
                        >
                          <div className="flex items-center gap-1">
                            Articles
                            <SortIcon column="article_count" />
                          </div>
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                          Level
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700">
                      {groupActors.map((actor) => (
                        <tr
                          key={actor.id}
                          onClick={() => handleActorClick(actor)}
                          className={`cursor-pointer transition-colors ${
                            selectedActor?.id === actor.id
                              ? 'bg-red-50 dark:bg-red-900/20'
                              : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                          }`}
                        >
                          <td className="px-4 py-2">
                            <div className="flex items-center gap-2">
                              <Users className="w-4 h-4 text-red-500 flex-shrink-0" />
                              <span className="font-medium text-gray-900 dark:text-gray-100 truncate max-w-[200px]">
                                {actor.name}
                              </span>
                            </div>
                          </td>
                          <td className="px-4 py-2">
                            <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                              {ACTOR_TYPE_LABELS[actor.actor_type]}
                            </span>
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                            {actor.attributed_country_name || '-'}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-900 dark:text-gray-100 font-medium">
                            {actor.threat_count}
                          </td>
                          <td className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400">
                            {actor.article_count}
                          </td>
                          <td className="px-4 py-2">
                            {actor.sophistication_level ? (
                              <span className={`px-2 py-0.5 text-xs font-medium rounded ${getSophisticationColor(actor.sophistication_level)}`}>
                                {actor.sophistication_level}
                              </span>
                            ) : (
                              <span className="text-xs text-gray-400">-</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ))}
          </div>
        ) : (
          /* Card View */
          <div className="space-y-4">
            {Array.from(groupedActors().entries()).map(([groupName, groupActors]) => (
              <div key={groupName}>
                {groupBy !== 'none' && (
                  <h4 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-2">
                    {groupName}
                    <span className="text-xs text-gray-500 dark:text-gray-400">({groupActors.length})</span>
                  </h4>
                )}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {groupActors.map((actor) => (
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
              </div>
            ))}
          </div>
        )}

        {actors.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400 py-12">
            No threat actors found.
          </div>
        )}
      </div>

      {/* Actor Details */}
      <div className="lg:col-span-1">
        {selectedActor ? (
          <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 sticky top-4 space-y-4 max-h-[calc(100vh-120px)] overflow-y-auto">
            {/* Header */}
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100">
                {selectedActor.name}
              </h3>
              <div className="flex items-center gap-2 mt-1">
                <span className="px-2 py-0.5 text-xs font-medium rounded bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                  {ACTOR_TYPE_LABELS[selectedActor.actor_type]}
                </span>
                {selectedActor.sophistication_level && (
                  <span className={`px-2 py-0.5 text-xs font-medium rounded ${getSophisticationColor(selectedActor.sophistication_level)}`}>
                    {selectedActor.sophistication_level}
                  </span>
                )}
              </div>
            </div>

            {/* Stats Cards */}
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400 mb-1">
                  <Shield className="w-3.5 h-3.5" />
                  <span className="text-xs">Threats</span>
                </div>
                <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
                  {selectedActor.threat_count}
                </div>
              </div>
              <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-3">
                <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400 mb-1">
                  <FileText className="w-3.5 h-3.5" />
                  <span className="text-xs">Articles</span>
                </div>
                <div className="text-xl font-bold text-gray-900 dark:text-gray-100">
                  {selectedActor.article_count}
                </div>
              </div>
            </div>

            {/* Timeline */}
            {(selectedActor.first_observed || selectedActor.last_active) && (
              <div className="flex flex-wrap gap-3 text-xs">
                {selectedActor.first_observed && (
                  <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
                    <Calendar className="w-3.5 h-3.5" />
                    <span>First seen: {new Date(selectedActor.first_observed).toLocaleDateString()}</span>
                  </div>
                )}
                {selectedActor.last_active && (
                  <div className="flex items-center gap-1.5 text-gray-500 dark:text-gray-400">
                    <Clock className="w-3.5 h-3.5" />
                    <span>Last active: {new Date(selectedActor.last_active).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
            )}

            {/* Basic Info */}
            <div className="space-y-2 text-sm">
              {selectedActor.attributed_country_name && (
                <div className="flex items-center gap-2">
                  <Globe className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-500 dark:text-gray-400">Origin:</span>
                  <span className="text-gray-900 dark:text-gray-100 font-medium">
                    {selectedActor.attributed_country_name}
                  </span>
                </div>
              )}
              {selectedActor.motivation && (
                <div className="flex items-center gap-2">
                  <Target className="w-4 h-4 text-gray-400" />
                  <span className="text-gray-500 dark:text-gray-400">Motivation:</span>
                  <span className="text-gray-900 dark:text-gray-100 font-medium capitalize">
                    {selectedActor.motivation}
                  </span>
                </div>
              )}
            </div>

            {/* Aliases */}
            {selectedActor.aliases && selectedActor.aliases.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
                  Also Known As
                </h4>
                <div className="flex flex-wrap gap-1">
                  {selectedActor.aliases.map((alias) => (
                    <span
                      key={alias}
                      className="px-2 py-0.5 text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 rounded"
                    >
                      {alias}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Description */}
            {selectedActor.description && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
                  Description
                </h4>
                <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
                  {selectedActor.description}
                </p>
              </div>
            )}

            {/* Target Industries */}
            {selectedActor.target_industries && selectedActor.target_industries.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
                  Target Industries
                </h4>
                <div className="flex flex-wrap gap-1">
                  {selectedActor.target_industries.map((industry) => (
                    <span
                      key={industry}
                      className="px-2 py-0.5 text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded capitalize"
                    >
                      {industry}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Target Regions */}
            {selectedActor.target_regions && selectedActor.target_regions.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
                  Target Regions
                </h4>
                <div className="flex flex-wrap gap-1">
                  {selectedActor.target_regions.map((region) => (
                    <span
                      key={region}
                      className="px-2 py-0.5 text-xs bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 rounded"
                    >
                      {region}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Known TTPs */}
            {selectedActor.known_ttps && selectedActor.known_ttps.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
                  MITRE ATT&CK TTPs
                </h4>
                <div className="flex flex-wrap gap-1">
                  {selectedActor.known_ttps.slice(0, 12).map((ttp) => (
                    <span
                      key={ttp}
                      className="px-2 py-0.5 text-xs bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 rounded font-mono"
                    >
                      {ttp}
                    </span>
                  ))}
                  {selectedActor.known_ttps.length > 12 && (
                    <span className="px-2 py-0.5 text-xs text-gray-500 dark:text-gray-400">
                      +{selectedActor.known_ttps.length - 12} more
                    </span>
                  )}
                </div>
              </div>
            )}

            {/* Associated Malware */}
            {selectedActor.associated_malware && selectedActor.associated_malware.length > 0 && (
              <div>
                <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
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
              <h4 className="text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wide mb-1.5">
                Related Threats ({selectedActor.threat_count})
              </h4>
              {loadingThreats ? (
                <div className="flex items-center justify-center py-4">
                  <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-red-500"></div>
                </div>
              ) : actorThreats.length > 0 ? (
                <div className="space-y-2">
                  {actorThreats.slice(0, 5).map((threat) => (
                    <div
                      key={threat.id}
                      className="p-2 bg-gray-50 dark:bg-gray-700/50 rounded text-sm cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
                      onClick={() => {
                        const threatData = {
                          id: threat.id,
                          threat_name: threat.threat_name,
                          threat_type: threat.threat_type,
                          severity_level: threat.severity_level,
                          severity_score: threat.severity_score,
                          trend: threat.trend,
                          article_count: threat.article_count,
                        } as ThreatMapData;
                        onThreatClick(threatData);
                      }}
                    >
                      <div className="font-medium text-gray-900 dark:text-gray-100 truncate">
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
                  {actorThreats.length > 5 && (
                    <div className="text-xs text-gray-500 dark:text-gray-400 text-center pt-1">
                      +{actorThreats.length - 5} more threats
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-sm text-gray-500 dark:text-gray-400">No threats linked yet.</p>
              )}
            </div>

            {/* Action Buttons */}
            <div className="pt-2 space-y-2">
              {onActorArticlesClick && selectedActor.article_count > 0 && (
                <button
                  onClick={() => onActorArticlesClick(selectedActor)}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-purple-500 text-white rounded-lg hover:bg-purple-600 transition-colors text-sm font-medium"
                >
                  <FileText className="w-4 h-4" />
                  View {selectedActor.article_count} Articles
                </button>
              )}
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
