"use client";

import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";

type HighlightedLocation = {
  coordinates: [number, number];
  name: string;
};

type ScenicMapProps = {
  routeCoordinates: number[][] | null;
  fallbackCenter?: [number, number];
  highlightedLocation?: HighlightedLocation | null;
};

const SOURCE_ID = "selected-route";
const LAYER_ID = "selected-route-line";
const HIGHLIGHT_SOURCE_ID = "debug-highlight-point";
const HIGHLIGHT_PULSE_LAYER_ID = "debug-highlight-point-pulse-layer";
const HIGHLIGHT_CORE_LAYER_ID = "debug-highlight-point-core-layer";
const HIGHLIGHT_LABEL_LAYER_ID = "debug-highlight-point-label-layer";
const ENDPOINT_SOURCE_ID = "route-endpoints";
const ENDPOINT_CORE_LAYER_ID = "route-endpoints-core-layer";
const ENDPOINT_LABEL_LAYER_ID = "route-endpoints-label-layer";

export function ScenicMap({
  routeCoordinates,
  fallbackCenter = [-0.1278, 51.5074],
  highlightedLocation = null,
}: ScenicMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const hasInitializedRef = useRef(false);
  const pulseAnimationFrameRef = useRef<number | null>(null);
  const pulseStartRef = useRef<number | null>(null);

  const token = process.env.NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN ?? "";

  useEffect(() => {
    if (!containerRef.current || !token || hasInitializedRef.current) {
      return;
    }

    mapboxgl.accessToken = token;

    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: "mapbox://styles/mapbox/outdoors-v12",
      center: fallbackCenter,
      zoom: 12,
      attributionControl: false,
    });

    map.addControl(new mapboxgl.NavigationControl({ visualizePitch: true }), "top-right");

    map.on("load", () => {
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: {
          type: "Feature",
          properties: {},
          geometry: {
            type: "LineString",
            coordinates: routeCoordinates ?? [],
          },
        },
      });

      map.addLayer({
        id: LAYER_ID,
        type: "line",
        source: SOURCE_ID,
        paint: {
          "line-color": "#2f7f62",
          "line-width": 6,
          "line-opacity": 0.92,
        },
      });

      map.addSource(HIGHLIGHT_SOURCE_ID, {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });

      map.addLayer({
        id: HIGHLIGHT_PULSE_LAYER_ID,
        type: "circle",
        source: HIGHLIGHT_SOURCE_ID,
        paint: {
          "circle-radius": 10,
          "circle-color": "#7c3aed",
          "circle-opacity": 0.25,
          "circle-stroke-width": 0,
        },
      });

      map.addLayer({
        id: HIGHLIGHT_CORE_LAYER_ID,
        type: "circle",
        source: HIGHLIGHT_SOURCE_ID,
        paint: {
          "circle-radius": 7,
          "circle-color": "#7c3aed",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 3,
          "circle-opacity": 1,
        },
      });

      map.addLayer({
        id: HIGHLIGHT_LABEL_LAYER_ID,
        type: "symbol",
        source: HIGHLIGHT_SOURCE_ID,
        layout: {
          "text-field": ["get", "name"],
          "text-size": 12,
          "text-offset": [0, -1.6],
          "text-anchor": "top",
          "text-font": ["Open Sans Semibold", "Arial Unicode MS Regular"],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": "#7c3aed",
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.2,
        },
      });

      map.addSource(ENDPOINT_SOURCE_ID, {
        type: "geojson",
        data: {
          type: "FeatureCollection",
          features: [],
        },
      });

      map.addLayer({
        id: ENDPOINT_CORE_LAYER_ID,
        type: "circle",
        source: ENDPOINT_SOURCE_ID,
        paint: {
          "circle-radius": 6,
          "circle-color": [
            "match",
            ["get", "role"],
            "start",
            "#0ea5e9",
            "end",
            "#f97316",
            "#334155",
          ],
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
          "circle-opacity": 1,
        },
      });

      map.addLayer({
        id: ENDPOINT_LABEL_LAYER_ID,
        type: "symbol",
        source: ENDPOINT_SOURCE_ID,
        layout: {
          "text-field": ["get", "name"],
          "text-size": 12,
          "text-offset": [0, -1.4],
          "text-anchor": "top",
          "text-font": ["Open Sans Semibold", "Arial Unicode MS Regular"],
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: {
          "text-color": [
            "match",
            ["get", "role"],
            "start",
            "#0369a1",
            "end",
            "#c2410c",
            "#1e293b",
          ],
          "text-halo-color": "#ffffff",
          "text-halo-width": 1.2,
        },
      });
    });

    mapRef.current = map;
    hasInitializedRef.current = true;

    return () => {
      if (pulseAnimationFrameRef.current !== null) {
        window.cancelAnimationFrame(pulseAnimationFrameRef.current);
        pulseAnimationFrameRef.current = null;
      }
      map.remove();
      mapRef.current = null;
      hasInitializedRef.current = false;
    };
  }, [fallbackCenter, routeCoordinates, token]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) {
      return;
    }

    const source = map.getSource(SOURCE_ID) as mapboxgl.GeoJSONSource | undefined;
    if (!source) {
      return;
    }

    const endpointSource = map.getSource(ENDPOINT_SOURCE_ID) as mapboxgl.GeoJSONSource | undefined;
    if (!endpointSource) {
      return;
    }

    source.setData({
      type: "Feature",
      properties: {},
      geometry: {
        type: "LineString",
        coordinates: routeCoordinates ?? [],
      },
    });

    if (routeCoordinates && routeCoordinates.length > 0) {
      const startCoordinate: [number, number] = [routeCoordinates[0][0], routeCoordinates[0][1]];
      const endCoordinate: [number, number] = [
        routeCoordinates[routeCoordinates.length - 1][0],
        routeCoordinates[routeCoordinates.length - 1][1],
      ];

      const endpointFeatures =
        routeCoordinates.length > 1
          ? [
              {
                type: "Feature" as const,
                properties: {
                  role: "start",
                  name: "Start",
                },
                geometry: {
                  type: "Point" as const,
                  coordinates: startCoordinate,
                },
              },
              {
                type: "Feature" as const,
                properties: {
                  role: "end",
                  name: "End",
                },
                geometry: {
                  type: "Point" as const,
                  coordinates: endCoordinate,
                },
              },
            ]
          : [
              {
                type: "Feature" as const,
                properties: {
                  role: "single",
                  name: "Start",
                },
                geometry: {
                  type: "Point" as const,
                  coordinates: startCoordinate,
                },
              },
            ];

      endpointSource.setData({
        type: "FeatureCollection",
        features: endpointFeatures,
      });
    } else {
      endpointSource.setData({
        type: "FeatureCollection",
        features: [],
      });
    }

    if (routeCoordinates && routeCoordinates.length > 1) {
      const bounds = routeCoordinates.reduce(
        (acc, coordinate) => acc.extend([coordinate[0], coordinate[1]]),
        new mapboxgl.LngLatBounds(
          [routeCoordinates[0][0], routeCoordinates[0][1]],
          [routeCoordinates[0][0], routeCoordinates[0][1]],
        ),
      );

      map.fitBounds(bounds, {
        padding: 64,
        duration: 700,
      });
    }
  }, [routeCoordinates]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) {
      return;
    }

    const highlightSource = map.getSource(HIGHLIGHT_SOURCE_ID) as mapboxgl.GeoJSONSource | undefined;
    if (!highlightSource) {
      return;
    }

    highlightSource.setData({
      type: "FeatureCollection",
      features: highlightedLocation
        ? [
            {
              type: "Feature",
              properties: {
                name: highlightedLocation.name,
              },
              geometry: {
                type: "Point",
                coordinates: highlightedLocation.coordinates,
              },
            },
          ]
        : [],
    });
  }, [highlightedLocation]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !map.isStyleLoaded()) {
      return;
    }

    if (pulseAnimationFrameRef.current !== null) {
      window.cancelAnimationFrame(pulseAnimationFrameRef.current);
      pulseAnimationFrameRef.current = null;
    }

    if (!highlightedLocation) {
      map.setPaintProperty(HIGHLIGHT_PULSE_LAYER_ID, "circle-radius", 10);
      map.setPaintProperty(HIGHLIGHT_PULSE_LAYER_ID, "circle-opacity", 0.25);
      pulseStartRef.current = null;
      return;
    }

    const animatePulse = (timestamp: number) => {
      if (pulseStartRef.current === null) {
        pulseStartRef.current = timestamp;
      }

      const elapsed = (timestamp - pulseStartRef.current) / 1000;
      const cycle = elapsed % 1.3;
      const progress = cycle / 1.3;
      const radius = 10 + progress * 16;
      const opacity = 0.36 * (1 - progress);

      if (map.getLayer(HIGHLIGHT_PULSE_LAYER_ID)) {
        map.setPaintProperty(HIGHLIGHT_PULSE_LAYER_ID, "circle-radius", radius);
        map.setPaintProperty(HIGHLIGHT_PULSE_LAYER_ID, "circle-opacity", opacity);
      }

      pulseAnimationFrameRef.current = window.requestAnimationFrame(animatePulse);
    };

    pulseAnimationFrameRef.current = window.requestAnimationFrame(animatePulse);

    return () => {
      if (pulseAnimationFrameRef.current !== null) {
        window.cancelAnimationFrame(pulseAnimationFrameRef.current);
        pulseAnimationFrameRef.current = null;
      }
    };
  }, [highlightedLocation]);

  if (!token) {
    return (
      <div className="flex h-full items-center justify-center rounded-r-2xl bg-panel">
        <p className="max-w-sm px-4 text-center text-sm text-app-muted">
          Add NEXT_PUBLIC_MAPBOX_ACCESS_TOKEN to render the interactive map.
        </p>
      </div>
    );
  }

  return <div ref={containerRef} className="h-full w-full" aria-label="Interactive scenic map" />;
}
