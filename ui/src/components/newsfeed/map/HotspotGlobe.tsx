/**
 * HotspotGlobe Component
 * 3D interactive globe for displaying geopolitical hotspots
 */

import { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import Globe, { GlobeMethods } from 'react-globe.gl';
import type { Hotspot, RiskLevel } from '../../../services/geopoliticalHotspotsApi';
import { RISK_COLORS } from '../../../services/geopoliticalHotspotsApi';

interface HotspotGlobeProps {
  hotspots: Hotspot[];
  onHotspotClick?: (hotspot: Hotspot) => void;
  showLegend?: boolean;
}

// Risk level to size mapping
const RISK_SIZES: Record<RiskLevel, number> = {
  critical: 1.2,
  high: 1.0,
  medium: 0.8,
  low: 0.6,
  info: 0.4,
};

export function HotspotGlobe({ hotspots, onHotspotClick, showLegend = true }: HotspotGlobeProps) {
  const globeRef = useRef<GlobeMethods | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [hoveredHotspot, setHoveredHotspot] = useState<Hotspot | null>(null);

  // Update dimensions on resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setDimensions({
          width: rect.width,
          height: rect.height,
        });
      }
    };

    updateDimensions();
    window.addEventListener('resize', updateDimensions);
    return () => window.removeEventListener('resize', updateDimensions);
  }, []);

  // Auto-rotate and initial position
  useEffect(() => {
    if (globeRef.current) {
      // Set initial view to show Europe/Middle East
      globeRef.current.pointOfView({ lat: 30, lng: 20, altitude: 2.5 }, 1000);

      // Enable auto-rotation
      const controls = globeRef.current.controls();
      if (controls) {
        controls.autoRotate = true;
        controls.autoRotateSpeed = 0.5;
      }
    }
  }, []);

  // Stop rotation on interaction
  const handleInteraction = useCallback(() => {
    if (globeRef.current) {
      const controls = globeRef.current.controls();
      if (controls) {
        controls.autoRotate = false;
      }
    }
  }, []);

  // Point data for globe
  const pointsData = useMemo(() => {
    return hotspots.map((hotspot) => ({
      ...hotspot,
      lat: hotspot.latitude,
      lng: hotspot.longitude,
      size: RISK_SIZES[hotspot.risk_level] * (1 + Math.log10(hotspot.article_count + 1) * 0.3),
      color: RISK_COLORS[hotspot.risk_level],
    }));
  }, [hotspots]);

  // HTML labels for hotspots - show all with smart styling
  const htmlElementsData = useMemo(() => {
    // Sort by intensity and take all hotspots
    const sortedHotspots = [...hotspots]
      .sort((a, b) => b.intensity_score - a.intensity_score);

    return sortedHotspots.map((hotspot) => ({
      ...hotspot,
      lat: hotspot.latitude,
      lng: hotspot.longitude,
    }));
  }, [hotspots]);

  // Handle label click - pivot globe and trigger callback
  const handleLabelClick = useCallback((hotspot: Hotspot) => {
    // Pivot globe to center on the hotspot
    if (globeRef.current) {
      globeRef.current.pointOfView(
        { lat: hotspot.latitude, lng: hotspot.longitude, altitude: 1.5 },
        1000
      );
      // Stop auto-rotation
      const controls = globeRef.current.controls();
      if (controls) {
        controls.autoRotate = false;
      }
    }
    // Trigger the callback
    if (onHotspotClick) {
      onHotspotClick(hotspot);
    }
  }, [onHotspotClick]);

  // Create HTML element for each label
  const createHtmlElement = useCallback((d: any) => {
    const hotspot = d as Hotspot;
    const el = document.createElement('div');
    el.style.cssText = `
      pointer-events: none;
      transform: translate(-50%, -100%);
      padding-bottom: 8px;
    `;

    const color = RISK_COLORS[hotspot.risk_level];
    const category = hotspot.primary_category
      ? hotspot.primary_category.charAt(0).toUpperCase() + hotspot.primary_category.slice(1)
      : '';

    // Create the inner card div with pointer events enabled
    const cardDiv = document.createElement('div');
    cardDiv.style.cssText = `
      pointer-events: auto;
      cursor: pointer;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(4px);
      border-left: 3px solid ${color};
      padding: 4px 8px;
      border-radius: 4px;
      font-family: system-ui, -apple-system, sans-serif;
      white-space: nowrap;
      box-shadow: 0 2px 8px rgba(0,0,0,0.4);
      transition: transform 0.15s ease, box-shadow 0.15s ease;
    `;

    cardDiv.innerHTML = `
      <div style="
        font-size: 11px;
        font-weight: 600;
        color: white;
        line-height: 1.2;
      ">${hotspot.location_name}</div>
      ${category ? `
        <div style="
          font-size: 9px;
          color: ${color};
          font-weight: 500;
          margin-top: 1px;
        ">${category} · ${hotspot.risk_level.toUpperCase()}</div>
      ` : ''}
    `;

    // Add hover effect
    cardDiv.addEventListener('mouseenter', () => {
      cardDiv.style.transform = 'scale(1.05)';
      cardDiv.style.boxShadow = '0 4px 12px rgba(0,0,0,0.6)';
    });
    cardDiv.addEventListener('mouseleave', () => {
      cardDiv.style.transform = 'scale(1)';
      cardDiv.style.boxShadow = '0 2px 8px rgba(0,0,0,0.4)';
    });

    // Add click handler
    cardDiv.addEventListener('click', (e) => {
      e.stopPropagation();
      handleLabelClick(hotspot);
    });

    el.appendChild(cardDiv);
    return el;
  }, [handleLabelClick]);

  // Handle point click
  const handlePointClick = useCallback(
    (point: any) => {
      if (onHotspotClick && point) {
        onHotspotClick(point as Hotspot);
      }
    },
    [onHotspotClick]
  );

  // Handle point hover
  const handlePointHover = useCallback((point: any) => {
    setHoveredHotspot(point as Hotspot | null);
    if (containerRef.current) {
      containerRef.current.style.cursor = point ? 'pointer' : 'grab';
    }
  }, []);

  // Custom label for tooltip
  const pointLabel = useCallback((point: any) => {
    const h = point as Hotspot;
    return `
      <div style="
        background: rgba(31, 41, 55, 0.95);
        padding: 12px 16px;
        border-radius: 8px;
        color: white;
        font-family: system-ui, -apple-system, sans-serif;
        font-size: 13px;
        max-width: 280px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
      ">
        <div style="font-weight: 600; font-size: 14px; margin-bottom: 6px;">
          ${h.location_name}
        </div>
        ${h.country_name ? `<div style="color: #9ca3af; margin-bottom: 8px;">${h.country_name}</div>` : ''}
        <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px;">
          <span style="
            background: ${RISK_COLORS[h.risk_level]};
            padding: 2px 8px;
            border-radius: 12px;
            font-size: 11px;
            font-weight: 600;
          ">${h.risk_level.toUpperCase()}</span>
          ${h.primary_category ? `
            <span style="
              background: rgba(255,255,255,0.1);
              padding: 2px 8px;
              border-radius: 12px;
              font-size: 11px;
            ">${h.primary_category}</span>
          ` : ''}
        </div>
        <div style="color: #d1d5db; font-size: 12px;">
          <div>Intensity: ${Math.round(h.intensity_score)}%</div>
          <div>Articles: ${h.article_count.toLocaleString()}</div>
          ${h.trend ? `<div>Trend: ${h.trend === 'escalating' ? '↑' : h.trend === 'de-escalating' ? '↓' : '→'} ${h.trend}</div>` : ''}
        </div>
      </div>
    `;
  }, []);

  return (
    <div
      ref={containerRef}
      className="relative w-full bg-gray-900 rounded-lg overflow-hidden"
      style={{ height: 'calc(100vh - 280px)', minHeight: '500px' }}
      onMouseDown={handleInteraction}
      onTouchStart={handleInteraction}
    >
      <Globe
        ref={globeRef}
        width={dimensions.width}
        height={dimensions.height}
        globeImageUrl="//unpkg.com/three-globe/example/img/earth-night.jpg"
        bumpImageUrl="//unpkg.com/three-globe/example/img/earth-topology.png"
        backgroundImageUrl="//unpkg.com/three-globe/example/img/night-sky.png"
        pointsData={pointsData}
        pointLat="lat"
        pointLng="lng"
        pointColor="color"
        pointAltitude={0.01}
        pointRadius="size"
        pointLabel={pointLabel}
        onPointClick={handlePointClick}
        onPointHover={handlePointHover}
        pointsMerge={false}
        atmosphereColor="#4299e1"
        atmosphereAltitude={0.15}
        htmlElementsData={htmlElementsData}
        htmlLat="lat"
        htmlLng="lng"
        htmlAltitude={0.03}
        htmlElement={createHtmlElement}
      />

      {/* Legend */}
      {showLegend && (
        <div className="absolute bottom-4 left-4 bg-gray-800/90 backdrop-blur-sm rounded-lg p-3 text-xs">
          <div className="text-gray-300 font-medium mb-2">Risk Level</div>
          <div className="space-y-1">
            {(['critical', 'high', 'medium', 'low', 'info'] as RiskLevel[]).map((level) => (
              <div key={level} className="flex items-center gap-2">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: RISK_COLORS[level] }}
                />
                <span className="text-gray-400 capitalize">{level}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Hotspot count */}
      <div className="absolute top-4 right-4 bg-gray-800/90 backdrop-blur-sm rounded-lg px-3 py-2 text-sm text-gray-300">
        {hotspots.length} hotspots
      </div>

      {/* Instructions */}
      <div className="absolute bottom-4 right-4 bg-gray-800/90 backdrop-blur-sm rounded-lg px-3 py-2 text-xs text-gray-400">
        Drag to rotate • Scroll to zoom • Click hotspot for details
      </div>
    </div>
  );
}
