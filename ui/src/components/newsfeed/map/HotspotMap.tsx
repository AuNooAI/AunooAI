/**
 * HotspotMap Component
 * Interactive Leaflet map for displaying geopolitical hotspots
 */

import { useEffect, useRef, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import MarkerClusterGroup from 'react-leaflet-cluster';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import type { Hotspot, RiskLevel } from '../../../services/geopoliticalHotspotsApi';
import { RISK_COLORS } from '../../../services/geopoliticalHotspotsApi';
import { MapLegend } from './MapLegend';

// Critical: Fix Leaflet tile rendering with Tailwind CSS
// Tailwind's Preflight applies max-width: 100% to images which breaks tile positioning
// We need multiple approaches to ensure the fix applies:
// 1. CSS with high specificity via inline style element
// 2. Direct style manipulation via MutationObserver

// Inject CSS fix - append to body for higher priority over bundled Tailwind
if (!document.getElementById('leaflet-tailwind-fix-v2')) {
  const leafletFix = document.createElement('style');
  leafletFix.id = 'leaflet-tailwind-fix-v2';
  leafletFix.textContent = `
    /* Override Tailwind's img reset for Leaflet tiles */
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
    /* Ensure tiles have absolute positioning */
    .leaflet-tile-pane .leaflet-tile {
      position: absolute !important;
    }
    /* Fix tile container */
    .leaflet-tile-container {
      pointer-events: none;
    }
    /* Custom tooltip styling - compact rectangle card */
    .leaflet-tooltip.custom-tooltip {
      background-color: #1f2937 !important;
      border: none !important;
      border-radius: 6px !important;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3) !important;
      padding: 8px 10px !important;
      font-family: inherit !important;
      color: #f9fafb !important;
      font-size: 11px !important;
      max-width: 180px !important;
      min-width: 120px !important;
      white-space: normal !important;
      pointer-events: none !important;
      transition: none !important;
    }
    .leaflet-tooltip.custom-tooltip::before {
      border-top-color: #1f2937 !important;
    }
    /* Cluster tooltip - compact rectangle */
    .leaflet-tooltip.cluster-tooltip {
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
      transition: none !important;
    }
    .leaflet-tooltip.cluster-tooltip::before {
      border-top-color: #1f2937 !important;
    }
    /* Prevent tooltip flickering */
    .leaflet-tooltip {
      pointer-events: none !important;
    }
  `;
  // Append to body to override head styles
  document.body.appendChild(leafletFix);
}

// Function to fix tile image styles directly
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

// Fix for default marker icons in React-Leaflet
delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
});

// Create custom marker icons for different risk levels
const createMarkerIcon = (riskLevel: RiskLevel): L.DivIcon => {
  const color = RISK_COLORS[riskLevel];
  const size = riskLevel === 'critical' ? 24 : riskLevel === 'high' ? 20 : 16;

  return L.divIcon({
    className: 'custom-marker',
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

// Create cluster icon
const createClusterIcon = (cluster: L.MarkerCluster): L.DivIcon => {
  const count = cluster.getChildCount();
  const markers = cluster.getAllChildMarkers();

  // Determine cluster risk level based on highest risk marker
  const riskPriority: Record<RiskLevel, number> = {
    critical: 5,
    high: 4,
    medium: 3,
    low: 2,
    info: 1,
  };

  let highestRisk: RiskLevel = 'info';
  markers.forEach((marker) => {
    const risk = (marker.options as any).riskLevel as RiskLevel;
    if (riskPriority[risk] > riskPriority[highestRisk]) {
      highestRisk = risk;
    }
  });

  const color = RISK_COLORS[highestRisk];
  const size = count > 50 ? 50 : count > 20 ? 40 : 30;

  return L.divIcon({
    className: 'marker-cluster',
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

// Component to fix tile rendering issues caused by Tailwind CSS
function TileFixer() {
  const map = useMap();

  useEffect(() => {
    const container = map.getContainer();
    if (!container) return;

    // Initial fix
    fixTileStyles(container);

    // Use MutationObserver to fix tiles as they load
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

    // Also fix on map events
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

// Component to update map view when hotspots change
function MapUpdater({ hotspots }: { hotspots: Hotspot[] }) {
  const map = useMap();

  useEffect(() => {
    if (hotspots.length > 0) {
      const bounds = L.latLngBounds(hotspots.map((h) => [h.latitude, h.longitude]));
      map.fitBounds(bounds, { padding: [50, 50], maxZoom: 6 });
    }
  }, [hotspots, map]);

  return null;
}

interface HotspotMapProps {
  hotspots: Hotspot[];
  selectedHotspot?: Hotspot | null;
  onHotspotClick?: (hotspot: Hotspot) => void;
  height?: string;
  showLegend?: boolean;
  centerOnSelected?: boolean;
  fillContainer?: boolean;
}

export function HotspotMap({
  hotspots,
  selectedHotspot,
  onHotspotClick,
  height = '500px',
  showLegend = true,
  centerOnSelected = true,
  fillContainer = false,
}: HotspotMapProps) {
  const mapRef = useRef<L.Map | null>(null);

  // Center on selected hotspot
  useEffect(() => {
    if (centerOnSelected && selectedHotspot && mapRef.current) {
      mapRef.current.setView([selectedHotspot.latitude, selectedHotspot.longitude], 8, {
        animate: true,
      });
    }
  }, [selectedHotspot, centerOnSelected]);

  // Dark theme tile layer (CartoDB Dark Matter)
  const tileUrl = 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png';
  const attribution =
    '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/attributions">CARTO</a>';

  // Calculate height - if fillContainer, use calc to fill available space
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
        <MapUpdater hotspots={hotspots} />

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

              // Get risk breakdown
              const riskCounts: Record<string, number> = {};
              markers.forEach((m: any) => {
                const risk = m.options?.riskLevel || 'info';
                riskCounts[risk] = (riskCounts[risk] || 0) + 1;
              });

              const riskSummary = Object.entries(riskCounts)
                .sort((a, b) => b[1] - a[1])
                .map(([risk, cnt]) => `${cnt} ${risk}`)
                .join(', ');

              const tooltipContent = `<strong>${count} Hotspots</strong><br/><span style="opacity:0.8">${riskSummary}</span>`;

              cluster.bindTooltip(tooltipContent, {
                direction: 'top',
                offset: [0, -10],
                className: 'cluster-tooltip',
              }).openTooltip();
            },
            clustermouseout: (e: any) => {
              const cluster = e.propagatedFrom || e.layer;
              cluster.closeTooltip();
            },
          }}
        >
          {hotspots.map((hotspot) => (
            <Marker
              key={hotspot.id}
              position={[hotspot.latitude, hotspot.longitude]}
              icon={createMarkerIcon(hotspot.risk_level)}
              eventHandlers={{
                click: () => onHotspotClick?.(hotspot),
                add: (e) => {
                  // Bind native Leaflet tooltip for better compatibility with clustering
                  const marker = e.target;
                  const tooltipContent = `<strong>${hotspot.location_name}</strong><br/><span style="opacity:0.8">${hotspot.risk_level.toUpperCase()} • ${hotspot.article_count} articles${hotspot.primary_category ? ` • ${hotspot.primary_category}` : ''}</span>`;
                  marker.bindTooltip(tooltipContent, {
                    direction: 'top',
                    offset: [0, -8],
                    className: 'custom-tooltip',
                  });
                },
              }}
              {...({ riskLevel: hotspot.risk_level } as any)}
            >
              {/* Click popup with full details */}
              <Popup>
                <div className="min-w-[200px]">
                  <h3 className="font-semibold text-gray-900 mb-1">{hotspot.location_name}</h3>
                  {hotspot.country_name && (
                    <p className="text-sm text-gray-600 mb-2">{hotspot.country_name}</p>
                  )}
                  <div className="flex flex-wrap gap-2 mb-2">
                    <span
                      className="px-2 py-0.5 text-xs font-medium rounded-full text-white"
                      style={{ backgroundColor: RISK_COLORS[hotspot.risk_level] }}
                    >
                      {hotspot.risk_level.toUpperCase()}
                    </span>
                    {hotspot.primary_category && (
                      <span className="px-2 py-0.5 text-xs font-medium rounded-full bg-gray-200 text-gray-700">
                        {hotspot.primary_category}
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-gray-600 space-y-1">
                    <p>Intensity: {Math.round(hotspot.intensity_score)}%</p>
                    <p>Articles: {hotspot.article_count}</p>
                    {hotspot.trend && (
                      <p className="flex items-center gap-1">
                        Trend:{' '}
                        <span
                          className={
                            hotspot.trend === 'escalating'
                              ? 'text-red-500'
                              : hotspot.trend === 'de-escalating'
                                ? 'text-green-500'
                                : 'text-gray-500'
                          }
                        >
                          {hotspot.trend === 'escalating' ? '↑' : hotspot.trend === 'de-escalating' ? '↓' : '→'}{' '}
                          {hotspot.trend}
                        </span>
                      </p>
                    )}
                  </div>
                  {onHotspotClick && (
                    <button
                      className="mt-2 w-full text-xs text-blue-600 hover:text-blue-800 font-medium"
                      onClick={() => onHotspotClick(hotspot)}
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

      {showLegend && <MapLegend />}
    </div>
  );
}
