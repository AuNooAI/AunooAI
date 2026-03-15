/**
 * ThreatMap Component
 * Interactive Leaflet map for displaying threat intelligence
 */

import { useEffect, useRef } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { ThreatMapData, SeverityLevel } from '../../../services/threatIntelligenceApi';
import { SEVERITY_COLORS, THREAT_CATEGORY_LABELS } from '../../../services/threatIntelligenceApi';
import { ThreatMapLegend } from './ThreatMapLegend';

// Critical: Fix Leaflet tile rendering with Tailwind CSS
if (!document.getElementById('leaflet-tailwind-fix-threat')) {
  const leafletFix = document.createElement('style');
  leafletFix.id = 'leaflet-tailwind-fix-threat';
  leafletFix.textContent = `
    .leaflet-pane > img,
    .leaflet-tile-pane img.leaflet-tile,
    .leaflet-container .leaflet-tile-pane img,
    .leaflet-container .leaflet-overlay-pane img,
    .leaflet-container .leaflet-marker-pane img,
    .leaflet-container .leaflet-shadow-pane img,
    .leaflet-container img.leaflet-image-layer,
    img.leaflet-tile {
      max-width: none !important;
      max-height: none !important;
      width: auto !important;
      height: auto !important;
    }
    .leaflet-tile-pane .leaflet-tile {
      position: absolute !important;
    }
    .leaflet-tile-container {
      pointer-events: none;
    }
    .leaflet-tooltip.threat-tooltip {
      background-color: #1f2937 !important;
      border: none !important;
      border-radius: 6px !important;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
      padding: 8px 10px !important;
      font-family: inherit !important;
      color: #f9fafb !important;
      font-size: 11px !important;
      max-width: 200px !important;
      min-width: 140px !important;
      white-space: normal !important;
      pointer-events: none !important;
    }
    .leaflet-tooltip.threat-tooltip::before {
      border-top-color: #1f2937 !important;
    }
    .leaflet-tooltip.threat-cluster-tooltip {
      background-color: #1f2937 !important;
      border: none !important;
      border-radius: 6px !important;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
      padding: 8px 10px !important;
      color: #f9fafb !important;
      font-size: 11px !important;
      max-width: 160px !important;
      min-width: 100px !important;
      pointer-events: none !important;
    }
    .leaflet-tooltip.threat-cluster-tooltip::before {
      border-top-color: #1f2937 !important;
    }
    .leaflet-tooltip {
      pointer-events: none !important;
    }
    /* Permanent label styling - compact name label */
    .leaflet-tooltip.threat-label {
      background-color: rgba(31, 41, 55, 0.85) !important;
      border: none !important;
      border-radius: 4px !important;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.3) !important;
      padding: 2px 6px !important;
      font-family: inherit !important;
      color: #f9fafb !important;
      font-size: 10px !important;
      font-weight: 500 !important;
      white-space: nowrap !important;
      pointer-events: none !important;
      max-width: 150px !important;
      overflow: hidden !important;
      text-overflow: ellipsis !important;
    }
    .leaflet-tooltip.threat-label::before {
      display: none !important;
    }
  `;
  document.body.appendChild(leafletFix);
}

const fixTileStyles = (container: HTMLElement | null) => {
  if (!container) return;
  const tiles = container.querySelectorAll<HTMLImageElement>('.leaflet-tile, .leaflet-tile-pane img');
  tiles.forEach((tile) => {
    tile.style.maxWidth = 'none';
    tile.style.maxHeight = 'none';
    tile.style.width = 'auto';
    tile.style.height = 'auto';
  });
};

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

const createMarkerIcon = (severityLevel: SeverityLevel): L.DivIcon => {
  const color = SEVERITY_COLORS[severityLevel];
  const size = severityLevel === 'critical' ? 24 : severityLevel === 'high' ? 20 : 16;

  return L.divIcon({
    className: 'threat-marker',
    html: `
      <div style="
        width: ${size}px;
        height: ${size}px;
        background-color: ${color};
        border: 2px solid white;
        border-radius: 50%;
        box-shadow: 0 2px 4px rgba(0,0,0,0.3);
        cursor: pointer;
      "></div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -size / 2],
  });
};

const createClusterIcon = (cluster: L.MarkerCluster): L.DivIcon => {
  const count = cluster.getChildCount();
  const markers = cluster.getAllChildMarkers();

  const severityPriority: Record<SeverityLevel, number> = {
    critical: 5,
    high: 4,
    medium: 3,
    low: 2,
    info: 1,
  };

  let highestSeverity: SeverityLevel = 'info';
  markers.forEach((marker) => {
    const severity = (marker.options as any).severityLevel as SeverityLevel;
    if (severityPriority[severity] > severityPriority[highestSeverity]) {
      highestSeverity = severity;
    }
  });

  const color = SEVERITY_COLORS[highestSeverity];
  const size = count > 50 ? 50 : count > 20 ? 40 : 30;

  return L.divIcon({
    className: 'threat-cluster',
    html: `
      <div style="
        width: ${size}px;
        height: ${size}px;
        background-color: ${color};
        border: 3px solid white;
        border-radius: 50%;
        box-shadow: 0 2px 6px rgba(0,0,0,0.4);
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-weight: bold;
        font-size: ${size > 40 ? 14 : 12}px;
        cursor: pointer;
      ">${count}</div>
    `,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
};

function TileFixer() {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    if (!container) return;

    fixTileStyles(container);

    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'childList') {
          mutation.addedNodes.forEach((node) => {
            if (node instanceof HTMLImageElement && node.classList.contains('leaflet-tile')) {
              node.style.maxWidth = 'none';
              node.style.maxHeight = 'none';
              node.style.width = 'auto';
              node.style.height = 'auto';
            } else if (node instanceof HTMLElement) {
              const tiles = node.querySelectorAll<HTMLImageElement>('.leaflet-tile');
              tiles.forEach((tile) => {
                tile.style.maxWidth = 'none';
                tile.style.maxHeight = 'none';
                tile.style.width = 'auto';
                tile.style.height = 'auto';
              });
            }
          });
        }
      });
    });

    const tilePane = container.querySelector('.leaflet-tile-pane');
    if (tilePane) {
      observer.observe(tilePane, { childList: true, subtree: true });
    }

    const handleTileLoad = () => fixTileStyles(container);
    map.on('load', handleTileLoad);
    map.on('moveend', handleTileLoad);
    map.on('zoomend', handleTileLoad);

    return () => {
      observer.disconnect();
      map.off('load', handleTileLoad);
      map.off('moveend', handleTileLoad);
      map.off('zoomend', handleTileLoad);
    };
  }, [map]);

  return null;
}

function MapUpdater({ threats }: { threats: ThreatMapData[] }) {
  const map = useMap();

  useEffect(() => {
    if (threats.length > 0) {
      const bounds = L.latLngBounds(threats.map((t) => [t.latitude, t.longitude]));
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 6 });
    }
  }, [threats, map]);

  return null;
}

interface ThreatMapProps {
  threats: ThreatMapData[];
  selectedThreat?: ThreatMapData | null;
  onThreatClick?: (threat: ThreatMapData) => void;
  height?: string;
  showLegend?: boolean;
  showLabels?: boolean;
  centerOnSelected?: boolean;
  fillContainer?: boolean;
}

export function ThreatMap({
  threats,
  selectedThreat,
  onThreatClick,
  height = '500px',
  showLegend = true,
  showLabels = false,
  centerOnSelected = true,
  fillContainer = false,
}: ThreatMapProps) {
  const mapRef = useRef<L.Map | null>(null);

  useEffect(() => {
    if (centerOnSelected && selectedThreat && mapRef.current) {
      mapRef.current.setView([selectedThreat.latitude, selectedThreat.longitude], 8, {
        animate: true,
      });
    }
  }, [selectedThreat, centerOnSelected]);

  const tileUrl = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png';
  const attribution =
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

  const containerHeight = fillContainer ? 'calc(100vh - 280px)' : height;
  const minHeight = fillContainer ? '400px' : undefined;

  return (
    <div className="relative" style={{ height: containerHeight, minHeight }}>
      <MapContainer
        center={[20, 0]}
        zoom={2}
        style={{ height: '100%', width: '100%', borderRadius: '0.5rem' }}
        ref={mapRef}
        zoomControl={true}
        scrollWheelZoom={true}
      >
        <TileLayer
          url={tileUrl}
          attribution={attribution}
          subdomains={['a', 'b', 'c', 'd']}
        />

        <TileFixer />
        <MapUpdater threats={threats} />

        <MarkerClusterGroup
          chunkedLoading
          iconCreateFunction={createClusterIcon}
          maxClusterRadius={50}
          spiderfyOnMaxZoom={true}
          showCoverageOnHover={false}
          removeOutsideVisibleBounds={true}
          eventHandlers={{
            clustermouseover: (e: any) => {
              const cluster = e.propagatedFrom || e.layer;
              const markers = cluster.getAllChildMarkers();
              const count = markers.length;

              const severityCounts: Record<string, number> = {};
              markers.forEach((m: any) => {
                const severity = m.options?.severityLevel || 'info';
                severityCounts[severity] = (severityCounts[severity] || 0) + 1;
              });

              const severitySummary = Object.entries(severityCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([s, cnt]) => `${cnt} ${s}`)
                .join(', ');

              const tooltipContent = `<strong>${count} Threats</strong><br/><span style="opacity:0.8">${severitySummary}</span>`;

              cluster.bindTooltip(tooltipContent, {
                direction: 'top',
                offset: [0, -10],
                className: 'threat-cluster-tooltip',
              }).openTooltip();
            },
            clustermouseout: (e: any) => {
              const cluster = e.propagatedFrom || e.layer;
              cluster.closeTooltip();
            },
          }}
        >
          {threats.map((threat) => (
            <Marker
              key={threat.id}
              position={[threat.latitude, threat.longitude]}
              icon={createMarkerIcon(threat.severity_level)}
              eventHandlers={{
                click: () => onThreatClick?.(threat),
                add: (e) => {
                  const marker = e.target;

                  if (showLabels) {
                    // Permanent label with threat name
                    const labelName = threat.threat_name.length > 20
                      ? threat.threat_name.substring(0, 18) + '...'
                      : threat.threat_name;
                    marker.bindTooltip(labelName, {
                      permanent: true,
                      direction: 'right',
                      offset: [10, 0],
                      className: 'threat-label',
                    });
                  } else {
                    // Hover tooltip with full details
                    const typeLabel = THREAT_CATEGORY_LABELS[threat.threat_type] || threat.threat_type;
                    const tooltipContent = `<strong>${threat.threat_name}</strong><br/><span style="opacity:0.8">${threat.severity_level.toUpperCase()} - ${typeLabel}${threat.threat_actor_name ? ` - ${threat.threat_actor_name}` : ''}</span>`;
                    marker.bindTooltip(tooltipContent, {
                      direction: 'top',
                      offset: [0, -8],
                      className: 'threat-tooltip',
                    });
                  }
                },
              }}
              {...({ severityLevel: threat.severity_level } as any)}
            >
              <Popup>
                <div className="min-w-[220px]">
                  <h3 className="font-semibold text-gray-900 mb-1">{threat.threat_name}</h3>
                  {threat.threat_actor_name && (
                    <p className="text-sm text-gray-600 mb-2">Actor: {threat.threat_actor_name}</p>
                  )}
                  <div className="flex flex-wrap gap-2 mb-2">
                    <span
                      className="px-2 py-0.5 text-xs font-medium rounded-full text-white"
                      style={{ backgroundColor: SEVERITY_COLORS[threat.severity_level] }}
                    >
                      {threat.severity_level.toUpperCase()}
                    </span>
                    <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-gray-200 text-gray-700">
                      {THREAT_CATEGORY_LABELS[threat.threat_type] || threat.threat_type}
                    </span>
                  </div>
                  <div className="text-xs text-gray-600 space-y-1">
                    <p>Severity Score: {Math.round(threat.severity_score)}</p>
                    <p>Articles: {threat.article_count}</p>
                    {threat.trend && (
                      <p className="flex items-center gap-1">
                        Trend:{' '}
                        <span
                          className={
                            threat.trend === 'escalating'
                              ? 'text-red-500'
                              : threat.trend === 'declining'
                                ? 'text-green-500'
                                : 'text-gray-500'
                          }
                        >
                          {threat.trend === 'escalating' ? '↑' : threat.trend === 'declining' ? '↓' : '→'}{' '}
                          {threat.trend}
                        </span>
                      </p>
                    )}
                    {threat.attributed_country_name && (
                      <p>Attribution: {threat.attributed_country_name}</p>
                    )}
                  </div>
                  {onThreatClick && (
                    <button
                      className="mt-2 w-full text-xs text-red-600 hover:text-red-800 font-medium"
                      onClick={() => onThreatClick(threat)}
                    >
                      View Details →
                    </button>
                  )}
                </div>
              </Popup>
            </Marker>
          ))}
        </MarkerClusterGroup>
      </MapContainer>

      {showLegend && <ThreatMapLegend />}
    </div>
  );
}
