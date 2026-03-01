"use client";

import { useEffect, useRef } from "react";
import mapboxgl from "mapbox-gl";

type ScenicMapProps = {
  routeCoordinates: number[][] | null;
  fallbackCenter?: [number, number];
};

const SOURCE_ID = "selected-route";
const LAYER_ID = "selected-route-line";

export function ScenicMap({ routeCoordinates, fallbackCenter = [-0.1278, 51.5074] }: ScenicMapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const hasInitializedRef = useRef(false);

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
    });

    mapRef.current = map;
    hasInitializedRef.current = true;

    return () => {
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

    source.setData({
      type: "Feature",
      properties: {},
      geometry: {
        type: "LineString",
        coordinates: routeCoordinates ?? [],
      },
    });

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
