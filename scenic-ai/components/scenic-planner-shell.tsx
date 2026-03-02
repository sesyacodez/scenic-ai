"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ScenicMap } from "@/components/scenic-map";

type PreferenceKey = "nature" | "water" | "historic" | "quiet" | "viewpoints" | "culture" | "cafes";

type Preferences = Record<PreferenceKey, boolean>;

type SessionState = {
  schemaVersion: 2;
  durationMinutes: number;
  preferences: Preferences;
  refineText: string;
};

type LegacySessionState = {
  schemaVersion: 1;
  durationMinutes: number;
  preferences: Partial<Preferences>;
  refineText: string;
};

type GeneratedRoute = {
  id: string;
  distanceMeters: number;
  durationSeconds: number;
  scenicScore: number;
  scoreDebug?: ScoreDebugData;
  geometry: {
    type: "LineString";
    coordinates: number[][];
  };
};

type TagObjectMatch = {
  objectId: string;
  objectType: string;
  name?: string | null;
  lat?: number | null;
  lng?: number | null;
  matchedBy: string[];
  tags: Record<string, string>;
};

type DebugHoverTarget = {
  coordinates: [number, number];
  name: string;
};

type ScoreDebugData = {
  contextAvailable: boolean;
  poiContextFetchFailed?: boolean;
  natureFeatureCount: number;
  waterFeatureCount: number;
  historicFeatureCount: number;
  busyRoadFeatureCount: number;
  viewpointFeatureCount: number;
  cultureFeatureCount: number;
  cafeFeatureCount: number;
  quietFromSpeed: number;
  quietFromRoads: number;
  tagObjectMatches?: Partial<Record<PreferenceKey | "busyRoad", TagObjectMatch[]>>;
};

type GenerateResponse = {
  selectedRouteId: string | null;
  routes: GeneratedRoute[];
  explanation: {
    summary: string;
    reasons: string[];
  };
};

type BackendErrorPayload = {
  detail?: unknown;
  message?: unknown;
};

type GeoOrigin = {
  lat: number;
  lng: number;
  accuracy: number;
};

type PlaceSuggestion = {
  id: string;
  label: string;
  fullLabel: string;
  location: {
    lat: number;
    lng: number;
    label?: string | null;
  };
};

type WaypointDraft = {
  searchText: string;
  label: string;
  lat: string;
  lng: string;
};

const STORAGE_KEY = "scenicai.session";
const ORIGIN_STORAGE_KEY = "scenicai.origin";
const STOPS_STORAGE_KEY = "scenicai.stops";

const defaultPreferences: Preferences = {
  nature: true,
  water: false,
  historic: false,
  quiet: false,
  viewpoints: false,
  culture: false,
  cafes: false,
};

const defaultState: SessionState = {
  schemaVersion: 2,
  durationMinutes: 45,
  preferences: defaultPreferences,
  refineText: "",
};

const MIN_SIDEBAR_WIDTH = 280;
const MAX_SIDEBAR_WIDTH = 460;
const DEFAULT_SIDEBAR_WIDTH = 308;
const MAX_ACCEPTABLE_ACCURACY_METERS = 250;
const ORIGIN_SEARCH_DEBOUNCE_MS = 220;
const MAX_WAYPOINTS = 3;
const DEBUG_HOVER_CLEAR_DELAY_MS = 1000;

const resolveBackendBaseUrl = () => {
  if (process.env.NEXT_PUBLIC_BACKEND_BASE_URL) {
    return process.env.NEXT_PUBLIC_BACKEND_BASE_URL;
  }

  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "https" : "http";
    return `${protocol}://${window.location.hostname}:8000`;
  }

  return "http://127.0.0.1:8000";
};

const extractBackendErrorDetail = async (response: Response): Promise<string | null> => {
  try {
    const payload = (await response.json()) as BackendErrorPayload;

    if (typeof payload.detail === "string") {
      return payload.detail;
    }

    if (Array.isArray(payload.detail) && payload.detail.length > 0) {
      const first = payload.detail[0];
      if (typeof first === "string") {
        return first;
      }
      if (first && typeof first === "object") {
        const maybeMessage = (first as { msg?: unknown }).msg;
        if (typeof maybeMessage === "string") {
          return maybeMessage;
        }
      }
    }

    if (typeof payload.message === "string") {
      return payload.message;
    }
  } catch {
    return null;
  }

  return null;
};

export function ScenicPlannerShell() {
  const shellRef = useRef<HTMLDivElement>(null);
  const backendBaseUrl = useMemo(() => resolveBackendBaseUrl(), []);
  const [sessionState, setSessionState] = useState<SessionState>(defaultState);
  const [isStorageReady, setIsStorageReady] = useState(false);
  const [status, setStatus] = useState<"idle" | "generating" | "refining">("idle");
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [originLat, setOriginLat] = useState("");
  const [originLng, setOriginLng] = useState("");
  const [originLabel, setOriginLabel] = useState("");
  const [originSearchText, setOriginSearchText] = useState("");
  const [originSuggestions, setOriginSuggestions] = useState<PlaceSuggestion[]>([]);
  const [isOriginSearchLoading, setIsOriginSearchLoading] = useState(false);
  const [showOriginSuggestions, setShowOriginSuggestions] = useState(false);
  const [activeOriginSuggestionIndex, setActiveOriginSuggestionIndex] = useState(-1);
  const [originSearchError, setOriginSearchError] = useState<string | null>(null);
  const originSearchAbortRef = useRef<AbortController | null>(null);
  const originSearchDebounceRef = useRef<number | null>(null);
  const [destinationLat, setDestinationLat] = useState("");
  const [destinationLng, setDestinationLng] = useState("");
  const [destinationLabel, setDestinationLabel] = useState("");
  const [destinationSearchText, setDestinationSearchText] = useState("");
  const [destinationSuggestions, setDestinationSuggestions] = useState<PlaceSuggestion[]>([]);
  const [isDestinationSearchLoading, setIsDestinationSearchLoading] = useState(false);
  const [showDestinationSuggestions, setShowDestinationSuggestions] = useState(false);
  const [activeDestinationSuggestionIndex, setActiveDestinationSuggestionIndex] = useState(-1);
  const [destinationSearchError, setDestinationSearchError] = useState<string | null>(null);
  const destinationSearchAbortRef = useRef<AbortController | null>(null);
  const destinationSearchDebounceRef = useRef<number | null>(null);
  const [waypoints, setWaypoints] = useState<WaypointDraft[]>([]);
  const [activeWaypointIndex, setActiveWaypointIndex] = useState<number | null>(null);
  const [waypointSuggestions, setWaypointSuggestions] = useState<PlaceSuggestion[]>([]);
  const [isWaypointSearchLoading, setIsWaypointSearchLoading] = useState(false);
  const [showWaypointSuggestions, setShowWaypointSuggestions] = useState(false);
  const [activeWaypointSuggestionIndex, setActiveWaypointSuggestionIndex] = useState(-1);
  const [waypointSearchError, setWaypointSearchError] = useState<string | null>(null);
  const waypointSearchAbortRef = useRef<AbortController | null>(null);
  const waypointSearchDebounceRef = useRef<number | null>(null);
  const [requestError, setRequestError] = useState<string | null>(null);
  const [locationNote, setLocationNote] = useState<string | null>(null);
  const [routeTitle, setRouteTitle] = useState("Scenic Route");
  const [routeMeta, setRouteMeta] = useState("—");
  const [scenicScore, setScenicScore] = useState<number | null>(null);
  const [explanationText, setExplanationText] = useState(
    "Generate a route to see AI reasoning grounded in scored alternatives.",
  );
  const [selectedRouteDebug, setSelectedRouteDebug] = useState<ScoreDebugData | null>(null);
  const [activeDebugTag, setActiveDebugTag] = useState<PreferenceKey>("nature");
  const [hoveredDebugTarget, setHoveredDebugTarget] = useState<DebugHoverTarget | null>(null);
  const debugHoverClearTimeoutRef = useRef<number | null>(null);
  const [selectedRouteCoordinates, setSelectedRouteCoordinates] = useState<number[][] | null>(null);
  const [mapCenter, setMapCenter] = useState<[number, number]>([-0.1278, 51.5074]);

  const { durationMinutes, preferences, refineText } = sessionState;

  useEffect(() => {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      setIsStorageReady(true);
      return;
    }

    try {
      const parsed = JSON.parse(raw) as SessionState | LegacySessionState;
      if (parsed.schemaVersion === 2) {
        setSessionState({
          ...parsed,
          preferences: { ...defaultPreferences, ...parsed.preferences },
        });
      } else if (parsed.schemaVersion === 1) {
        setSessionState({
          schemaVersion: 2,
          durationMinutes: parsed.durationMinutes,
          preferences: { ...defaultPreferences, ...parsed.preferences },
          refineText: parsed.refineText,
        });
      } else {
        window.localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
    } finally {
      setIsStorageReady(true);
    }
  }, []);

  useEffect(() => {
    if (!isStorageReady) {
      return;
    }

    const state: SessionState = {
      schemaVersion: 2,
      durationMinutes,
      preferences,
      refineText,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [durationMinutes, isStorageReady, preferences, refineText]);

  useEffect(() => {
    const raw = window.localStorage.getItem(ORIGIN_STORAGE_KEY);
    if (!raw) {
      return;
    }

    try {
      const parsed = JSON.parse(raw) as { lat?: string; lng?: string; label?: string };
      setOriginLat(typeof parsed.lat === "string" ? parsed.lat : "");
      setOriginLng(typeof parsed.lng === "string" ? parsed.lng : "");
      const label = typeof parsed.label === "string" ? parsed.label : "";
      setOriginLabel(label);
      setOriginSearchText(label);
    } catch {
      window.localStorage.removeItem(ORIGIN_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    const raw = window.localStorage.getItem(STOPS_STORAGE_KEY);
    if (!raw) {
      return;
    }

    try {
      const parsed = JSON.parse(raw) as {
        destination?: { lat?: string; lng?: string; label?: string };
        waypoints?: WaypointDraft[];
      };

      const destination = parsed.destination;
      if (destination) {
        setDestinationLat(typeof destination.lat === "string" ? destination.lat : "");
        setDestinationLng(typeof destination.lng === "string" ? destination.lng : "");
        const destinationText = typeof destination.label === "string" ? destination.label : "";
        setDestinationLabel(destinationText);
        setDestinationSearchText(destinationText);
      }

      const parsedWaypoints = Array.isArray(parsed.waypoints) ? parsed.waypoints : [];
      setWaypoints(parsedWaypoints.slice(0, MAX_WAYPOINTS));
    } catch {
      window.localStorage.removeItem(STOPS_STORAGE_KEY);
    }
  }, []);

  useEffect(() => {
    window.localStorage.setItem(
      ORIGIN_STORAGE_KEY,
      JSON.stringify({
        lat: originLat,
        lng: originLng,
        label: originLabel,
      }),
    );
  }, [originLabel, originLat, originLng]);

  useEffect(() => {
    window.localStorage.setItem(
      STOPS_STORAGE_KEY,
      JSON.stringify({
        destination: {
          lat: destinationLat,
          lng: destinationLng,
          label: destinationLabel,
        },
        waypoints,
      }),
    );
  }, [destinationLabel, destinationLat, destinationLng, waypoints]);

  useEffect(() => {
    return () => {
      if (originSearchDebounceRef.current !== null) {
        window.clearTimeout(originSearchDebounceRef.current);
      }
      originSearchAbortRef.current?.abort();
      if (destinationSearchDebounceRef.current !== null) {
        window.clearTimeout(destinationSearchDebounceRef.current);
      }
      destinationSearchAbortRef.current?.abort();
      if (waypointSearchDebounceRef.current !== null) {
        window.clearTimeout(waypointSearchDebounceRef.current);
      }
      waypointSearchAbortRef.current?.abort();
      if (debugHoverClearTimeoutRef.current !== null) {
        window.clearTimeout(debugHoverClearTimeoutRef.current);
        debugHoverClearTimeoutRef.current = null;
      }
    };
  }, []);

  const fetchOriginSuggestions = useCallback(
    async (query: string) => {
      originSearchAbortRef.current?.abort();
      const controller = new AbortController();
      originSearchAbortRef.current = controller;

      setIsOriginSearchLoading(true);
      setOriginSearchError(null);

      try {
        const response = await fetch(`${backendBaseUrl}/api/v1/location/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            limit: 6,
            proximityLat: mapCenter[1],
            proximityLng: mapCenter[0],
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const detail = await extractBackendErrorDetail(response);
          throw new Error(detail || `Location search failed (${response.status})`);
        }

        const payload = (await response.json()) as { results?: PlaceSuggestion[] };
        const nextSuggestions = Array.isArray(payload.results) ? payload.results : [];
        setOriginSuggestions(nextSuggestions);
        setShowOriginSuggestions(true);
        setActiveOriginSuggestionIndex(nextSuggestions.length > 0 ? 0 : -1);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setOriginSuggestions([]);
        setActiveOriginSuggestionIndex(-1);
        setOriginSearchError(
          error instanceof Error
            ? error.message
            : "Location search unavailable. You can still enter coordinates below.",
        );
      } finally {
        setIsOriginSearchLoading(false);
      }
    },
    [backendBaseUrl, mapCenter],
  );

  const fetchDestinationSuggestions = useCallback(
    async (query: string) => {
      destinationSearchAbortRef.current?.abort();
      const controller = new AbortController();
      destinationSearchAbortRef.current = controller;

      setIsDestinationSearchLoading(true);
      setDestinationSearchError(null);

      try {
        const response = await fetch(`${backendBaseUrl}/api/v1/location/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            limit: 6,
            proximityLat: mapCenter[1],
            proximityLng: mapCenter[0],
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const detail = await extractBackendErrorDetail(response);
          throw new Error(detail || `Location search failed (${response.status})`);
        }

        const payload = (await response.json()) as { results?: PlaceSuggestion[] };
        const nextSuggestions = Array.isArray(payload.results) ? payload.results : [];
        setDestinationSuggestions(nextSuggestions);
        setShowDestinationSuggestions(true);
        setActiveDestinationSuggestionIndex(nextSuggestions.length > 0 ? 0 : -1);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setDestinationSuggestions([]);
        setActiveDestinationSuggestionIndex(-1);
        setDestinationSearchError(
          error instanceof Error ? error.message : "Destination search unavailable right now.",
        );
      } finally {
        setIsDestinationSearchLoading(false);
      }
    },
    [backendBaseUrl, mapCenter],
  );

  const fetchWaypointSuggestions = useCallback(
    async (query: string) => {
      waypointSearchAbortRef.current?.abort();
      const controller = new AbortController();
      waypointSearchAbortRef.current = controller;

      setIsWaypointSearchLoading(true);
      setWaypointSearchError(null);

      try {
        const response = await fetch(`${backendBaseUrl}/api/v1/location/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            limit: 6,
            proximityLat: mapCenter[1],
            proximityLng: mapCenter[0],
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const detail = await extractBackendErrorDetail(response);
          throw new Error(detail || `Location search failed (${response.status})`);
        }

        const payload = (await response.json()) as { results?: PlaceSuggestion[] };
        const nextSuggestions = Array.isArray(payload.results) ? payload.results : [];
        setWaypointSuggestions(nextSuggestions);
        setShowWaypointSuggestions(true);
        setActiveWaypointSuggestionIndex(nextSuggestions.length > 0 ? 0 : -1);
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setWaypointSuggestions([]);
        setActiveWaypointSuggestionIndex(-1);
        setWaypointSearchError(error instanceof Error ? error.message : "Waypoint search unavailable right now.");
      } finally {
        setIsWaypointSearchLoading(false);
      }
    },
    [backendBaseUrl, mapCenter],
  );

  const reverseGeocodeOrigin = useCallback(
    async (lat: number, lng: number) => {
      try {
        const response = await fetch(`${backendBaseUrl}/api/v1/location/reverse`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ lat, lng }),
        });

        if (!response.ok) {
          const detail = await extractBackendErrorDetail(response);
          if (detail) {
            setLocationNote(detail);
          }
          return;
        }

        const payload = (await response.json()) as { results?: PlaceSuggestion[] };
        const top = payload.results?.[0];
        if (!top) {
          return;
        }

        setOriginLabel(top.fullLabel);
        setOriginSearchText(top.fullLabel);
      } catch {
        // Non-blocking fallback.
      }
    },
    [backendBaseUrl],
  );

  useEffect(() => {
    const query = originSearchText.trim();
    if (!query || query.length < 2 || query === originLabel) {
      setOriginSuggestions([]);
      setShowOriginSuggestions(false);
      setIsOriginSearchLoading(false);
      setOriginSearchError(null);
      return;
    }

    if (originSearchDebounceRef.current !== null) {
      window.clearTimeout(originSearchDebounceRef.current);
    }

    originSearchDebounceRef.current = window.setTimeout(() => {
      fetchOriginSuggestions(query);
    }, ORIGIN_SEARCH_DEBOUNCE_MS);

    return () => {
      if (originSearchDebounceRef.current !== null) {
        window.clearTimeout(originSearchDebounceRef.current);
      }
    };
  }, [fetchOriginSuggestions, originLabel, originSearchText]);

  useEffect(() => {
    const query = destinationSearchText.trim();
    if (!query || query.length < 2 || query === destinationLabel) {
      setDestinationSuggestions([]);
      setShowDestinationSuggestions(false);
      setIsDestinationSearchLoading(false);
      setDestinationSearchError(null);
      return;
    }

    if (destinationSearchDebounceRef.current !== null) {
      window.clearTimeout(destinationSearchDebounceRef.current);
    }

    destinationSearchDebounceRef.current = window.setTimeout(() => {
      fetchDestinationSuggestions(query);
    }, ORIGIN_SEARCH_DEBOUNCE_MS);

    return () => {
      if (destinationSearchDebounceRef.current !== null) {
        window.clearTimeout(destinationSearchDebounceRef.current);
      }
    };
  }, [destinationLabel, destinationSearchText, fetchDestinationSuggestions]);

  useEffect(() => {
    if (activeWaypointIndex === null) {
      setShowWaypointSuggestions(false);
      return;
    }

    const activeWaypoint = waypoints[activeWaypointIndex];
    const query = activeWaypoint?.searchText.trim() ?? "";
    if (!query || query.length < 2 || query === activeWaypoint?.label) {
      setWaypointSuggestions([]);
      setShowWaypointSuggestions(false);
      setIsWaypointSearchLoading(false);
      setWaypointSearchError(null);
      return;
    }

    if (waypointSearchDebounceRef.current !== null) {
      window.clearTimeout(waypointSearchDebounceRef.current);
    }

    waypointSearchDebounceRef.current = window.setTimeout(() => {
      fetchWaypointSuggestions(query);
    }, ORIGIN_SEARCH_DEBOUNCE_MS);

    return () => {
      if (waypointSearchDebounceRef.current !== null) {
        window.clearTimeout(waypointSearchDebounceRef.current);
      }
    };
  }, [activeWaypointIndex, fetchWaypointSuggestions, waypoints]);

  useEffect(() => {
    if (originLabel) {
      return;
    }

    const latValue = Number(originLat);
    const lngValue = Number(originLng);
    if (!Number.isFinite(latValue) || !Number.isFinite(lngValue)) {
      return;
    }

    void reverseGeocodeOrigin(latValue, lngValue);
  }, [originLabel, originLat, originLng, reverseGeocodeOrigin]);

  const selectedPreferences = useMemo(
    () => Object.entries(preferences).filter(([, enabled]) => enabled).map(([key]) => key),
    [preferences],
  );

  const resolveManualOrigin = (): { lat: number; lng: number } | null => {
    const latText = originLat.trim();
    const lngText = originLng.trim();
    if (!latText || !lngText) {
      return null;
    }

    const latValue = Number(latText);
    const lngValue = Number(lngText);

    if (!Number.isFinite(latValue) || !Number.isFinite(lngValue)) {
      return null;
    }

    if (latValue < -90 || latValue > 90 || lngValue < -180 || lngValue > 180) {
      return null;
    }

    return { lat: latValue, lng: lngValue };
  };

  const isLikelyNullIsland = (lat: number, lng: number) => {
    return Math.abs(lat) < 0.001 && Math.abs(lng) < 0.001;
  };

  const getOnePosition = async (options: PositionOptions): Promise<GeoOrigin | null> => {
    if (!navigator.geolocation) {
      return null;
    }

    return new Promise((resolve) => {
      navigator.geolocation.getCurrentPosition(
        (position) => {
          const lat = position.coords.latitude;
          const lng = position.coords.longitude;

          if (isLikelyNullIsland(lat, lng)) {
            resolve(null);
            return;
          }

          resolve({
            lat,
            lng,
            accuracy: position.coords.accuracy,
          });
        },
        () => resolve(null),
        options,
      );
    });
  };

  const resolveBrowserGeolocation = async (preferFresh = false): Promise<GeoOrigin | null> => {
    const attempts: PositionOptions[] = preferFresh
      ? [
          { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
          { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 },
          { enableHighAccuracy: false, timeout: 8000, maximumAge: 0 },
        ]
      : [
          { enableHighAccuracy: true, timeout: 10000, maximumAge: 15000 },
          { enableHighAccuracy: true, timeout: 12000, maximumAge: 0 },
          { enableHighAccuracy: false, timeout: 8000, maximumAge: 30000 },
        ];

    let bestFix: GeoOrigin | null = null;

    for (const options of attempts) {
      const fix = await getOnePosition(options);
      if (!fix) {
        continue;
      }

      if (!bestFix || fix.accuracy < bestFix.accuracy) {
        bestFix = fix;
      }

      if (fix.accuracy <= MAX_ACCEPTABLE_ACCURACY_METERS) {
        return fix;
      }
    }

    return bestFix;
  };

  const resolveOrigin = async (): Promise<GeoOrigin | null> => {
    const manualOrigin = resolveManualOrigin();
    if (manualOrigin) {
      return { ...manualOrigin, accuracy: 0 };
    }

    return resolveBrowserGeolocation(true);
  };

  const toPreferenceWeights = () => ({
    nature: preferences.nature ? 1 : 0,
    water: preferences.water ? 1 : 0,
    historic: preferences.historic ? 1 : 0,
    quiet: preferences.quiet ? 1 : 0,
    viewpoints: preferences.viewpoints ? 1 : 0,
    culture: preferences.culture ? 1 : 0,
    cafes: preferences.cafes ? 1 : 0,
  });

  const preferenceButtonOrder: PreferenceKey[] = [
    "nature",
    "water",
    "historic",
    "quiet",
    "viewpoints",
    "culture",
    "cafes",
  ];

  const preferenceLabels: Record<PreferenceKey, string> = {
    nature: "Nature",
    water: "Water",
    historic: "Historic",
    quiet: "Quiet",
    viewpoints: "Viewpoints",
    culture: "Culture",
    cafes: "Cafes",
  };

  const debugTagLabels: Record<PreferenceKey | "busyRoad", string> = {
    ...preferenceLabels,
    busyRoad: "Busy Roads",
  };

  const applyRouteResponse = (
    payload: GenerateResponse,
    origin: { lat: number; lng: number },
    fallbackNoRouteMessage: string,
  ) => {
    if (payload.routes.length === 0 || payload.selectedRouteId === null) {
      setExplanationText(payload.explanation.summary);
      setRequestError(fallbackNoRouteMessage);
      setSelectedRouteDebug(null);
      if (debugHoverClearTimeoutRef.current !== null) {
        window.clearTimeout(debugHoverClearTimeoutRef.current);
        debugHoverClearTimeoutRef.current = null;
      }
      setHoveredDebugTarget(null);
      return;
    }

    const selected = payload.routes.find((route) => route.id === payload.selectedRouteId) ?? payload.routes[0];
    const distanceKm = (selected.distanceMeters / 1000).toFixed(1);
    const minutes = Math.round(selected.durationSeconds / 60);

    setRouteTitle(`Route ${selected.id.replace("route_", "#")}`);
    setRouteMeta(`${distanceKm} km ・ ${minutes} min walk`);
    setScenicScore(selected.scenicScore);
    setExplanationText(payload.explanation.summary);
    setSelectedRouteDebug(selected.scoreDebug ?? null);
    setActiveDebugTag(preferenceButtonOrder.find((key) => preferences[key]) ?? "nature");
    if (debugHoverClearTimeoutRef.current !== null) {
      window.clearTimeout(debugHoverClearTimeoutRef.current);
      debugHoverClearTimeoutRef.current = null;
    }
    setHoveredDebugTarget(null);
    setSelectedRouteCoordinates(selected.geometry.coordinates);
    setMapCenter([origin.lng, origin.lat]);
  };

  const debugMatches = selectedRouteDebug?.tagObjectMatches?.[activeDebugTag] ?? [];
  const poiContextFetchFailed = selectedRouteDebug?.poiContextFetchFailed === true;

  const togglePreference = (key: PreferenceKey) => {
    setSessionState((prev) => ({
      ...prev,
      preferences: { ...prev.preferences, [key]: !prev.preferences[key] },
    }));
  };

  const applyOriginSuggestion = (suggestion: PlaceSuggestion) => {
    setOriginLat(suggestion.location.lat.toFixed(5));
    setOriginLng(suggestion.location.lng.toFixed(5));
    setOriginLabel(suggestion.fullLabel);
    setOriginSearchText(suggestion.fullLabel);
    setOriginSuggestions([]);
    setShowOriginSuggestions(false);
    setActiveOriginSuggestionIndex(-1);
    setMapCenter([suggestion.location.lng, suggestion.location.lat]);
  };

  const applyDestinationSuggestion = (suggestion: PlaceSuggestion) => {
    setDestinationLat(suggestion.location.lat.toFixed(5));
    setDestinationLng(suggestion.location.lng.toFixed(5));
    setDestinationLabel(suggestion.fullLabel);
    setDestinationSearchText(suggestion.fullLabel);
    setDestinationSuggestions([]);
    setShowDestinationSuggestions(false);
    setActiveDestinationSuggestionIndex(-1);
  };

  const addWaypoint = () => {
    setWaypoints((prev) => {
      if (prev.length >= MAX_WAYPOINTS) {
        return prev;
      }
      return [...prev, { searchText: "", label: "", lat: "", lng: "" }];
    });
  };

  const removeWaypoint = (index: number) => {
    setWaypoints((prev) => prev.filter((_, waypointIndex) => waypointIndex !== index));
    setActiveWaypointIndex((prev) => {
      if (prev === null) {
        return prev;
      }
      if (prev === index) {
        return null;
      }
      return prev > index ? prev - 1 : prev;
    });
    setShowWaypointSuggestions(false);
  };

  const updateWaypointSearchText = (index: number, value: string) => {
    setWaypoints((prev) =>
      prev.map((waypoint, waypointIndex) =>
        waypointIndex === index
          ? {
              ...waypoint,
              searchText: value,
              label: "",
              lat: "",
              lng: "",
            }
          : waypoint,
      ),
    );
  };

  const applyWaypointSuggestion = (index: number, suggestion: PlaceSuggestion) => {
    setWaypoints((prev) =>
      prev.map((waypoint, waypointIndex) =>
        waypointIndex === index
          ? {
              ...waypoint,
              searchText: suggestion.fullLabel,
              label: suggestion.fullLabel,
              lat: suggestion.location.lat.toFixed(5),
              lng: suggestion.location.lng.toFixed(5),
            }
          : waypoint,
      ),
    );
    setWaypointSuggestions([]);
    setShowWaypointSuggestions(false);
    setActiveWaypointSuggestionIndex(-1);
  };

  const normalizeStop = (latText: string, lngText: string, labelText: string) => {
    const normalizedLatText = latText.trim();
    const normalizedLngText = lngText.trim();
    if (!normalizedLatText || !normalizedLngText) {
      return null;
    }

    const latValue = Number(normalizedLatText);
    const lngValue = Number(normalizedLngText);
    if (!Number.isFinite(latValue) || !Number.isFinite(lngValue)) {
      return null;
    }

    if (latValue < -90 || latValue > 90 || lngValue < -180 || lngValue > 180) {
      return null;
    }

    return {
      lat: latValue,
      lng: lngValue,
      label: labelText.trim() || undefined,
    };
  };

  const toStopsPayload = () => {
    const destination = normalizeStop(destinationLat, destinationLng, destinationLabel || destinationSearchText);

    const waypointPayload = waypoints
      .map((waypoint) => normalizeStop(waypoint.lat, waypoint.lng, waypoint.label || waypoint.searchText))
      .filter((item) => item !== null)
      .slice(0, MAX_WAYPOINTS);

    return { destination, waypoints: waypointPayload };
  };

  const handleOriginSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!showOriginSuggestions && originSuggestions.length > 0) {
        setShowOriginSuggestions(true);
      }
      setActiveOriginSuggestionIndex((prev) =>
        originSuggestions.length === 0 ? -1 : Math.min(prev + 1, originSuggestions.length - 1),
      );
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveOriginSuggestionIndex((prev) => (originSuggestions.length === 0 ? -1 : Math.max(prev - 1, 0)));
      return;
    }

    if (event.key === "Enter") {
      if (showOriginSuggestions && activeOriginSuggestionIndex >= 0 && originSuggestions[activeOriginSuggestionIndex]) {
        event.preventDefault();
        applyOriginSuggestion(originSuggestions[activeOriginSuggestionIndex]);
      }
      return;
    }

    if (event.key === "Escape") {
      setShowOriginSuggestions(false);
    }
  };

  const handleDestinationSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!showDestinationSuggestions && destinationSuggestions.length > 0) {
        setShowDestinationSuggestions(true);
      }
      setActiveDestinationSuggestionIndex((prev) =>
        destinationSuggestions.length === 0 ? -1 : Math.min(prev + 1, destinationSuggestions.length - 1),
      );
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveDestinationSuggestionIndex((prev) =>
        destinationSuggestions.length === 0 ? -1 : Math.max(prev - 1, 0),
      );
      return;
    }

    if (
      event.key === "Enter" &&
      showDestinationSuggestions &&
      activeDestinationSuggestionIndex >= 0 &&
      destinationSuggestions[activeDestinationSuggestionIndex]
    ) {
      event.preventDefault();
      applyDestinationSuggestion(destinationSuggestions[activeDestinationSuggestionIndex]);
      return;
    }

    if (event.key === "Escape") {
      setShowDestinationSuggestions(false);
    }
  };

  const handleWaypointSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>, index: number) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!showWaypointSuggestions && waypointSuggestions.length > 0) {
        setShowWaypointSuggestions(true);
      }
      setActiveWaypointSuggestionIndex((prev) =>
        waypointSuggestions.length === 0 ? -1 : Math.min(prev + 1, waypointSuggestions.length - 1),
      );
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveWaypointSuggestionIndex((prev) => (waypointSuggestions.length === 0 ? -1 : Math.max(prev - 1, 0)));
      return;
    }

    if (
      event.key === "Enter" &&
      showWaypointSuggestions &&
      activeWaypointSuggestionIndex >= 0 &&
      waypointSuggestions[activeWaypointSuggestionIndex]
    ) {
      event.preventDefault();
      applyWaypointSuggestion(index, waypointSuggestions[activeWaypointSuggestionIndex]);
      return;
    }

    if (event.key === "Escape") {
      setShowWaypointSuggestions(false);
    }
  };

  const handleGenerate = async () => {
    setRequestError(null);
    setLocationNote(null);
    setStatus("generating");

    const origin = await resolveOrigin();
    if (!origin) {
      setStatus("idle");
      setRequestError("Location unavailable. Search for a place, enter coordinates, or allow geolocation.");
      return;
    }

    if (origin.accuracy > MAX_ACCEPTABLE_ACCURACY_METERS) {
      setLocationNote(
        `Low GPS accuracy (~${Math.round(origin.accuracy)}m). You can retry Use my location for a better fix.`,
      );
    }

    const stopsPayload = toStopsPayload();
    if (destinationSearchText.trim() && !stopsPayload.destination) {
      setStatus("idle");
      setRequestError("Pick a destination from suggestions, or clear destination text.");
      return;
    }

    try {
      const response = await fetch(`${backendBaseUrl}/api/v1/route/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin,
          destination: stopsPayload.destination,
          waypoints: stopsPayload.waypoints,
          durationMinutes,
          preferences: toPreferenceWeights(),
          constraints: { avoidBusyRoads: preferences.quiet },
          sessionId: "anon-web-session",
          refinementText: refineText || undefined,
        }),
      });

      if (!response.ok) {
        let detail = "";
        try {
          const errorPayload = (await response.json()) as BackendErrorPayload;
          detail = typeof errorPayload.detail === "string" ? errorPayload.detail : "";
        } catch {
          detail = "";
        }
        throw new Error(detail || `Backend returned ${response.status}`);
      }

      const payload = (await response.json()) as GenerateResponse;
      applyRouteResponse(payload, origin, "No route could be generated.");
    } catch (error) {
      if (error instanceof TypeError) {
        setRequestError(`Failed to fetch ${backendBaseUrl}. Verify backend is running and CORS is enabled.`);
      } else {
        setRequestError(error instanceof Error ? error.message : "Failed to generate route");
      }
    } finally {
      setStatus("idle");
    }
  };

  const handleRefine = async () => {
    const message = refineText.trim();
    if (!message) {
      setRequestError("Enter a refinement instruction first.");
      return;
    }

    setRequestError(null);
    setStatus("refining");

    const origin = await resolveOrigin();
    if (!origin) {
      setStatus("idle");
      setRequestError("Location unavailable. Search for a place, enter coordinates, or allow geolocation.");
      return;
    }

    const stopsPayload = toStopsPayload();

    try {
      const response = await fetch(`${backendBaseUrl}/api/v1/route/refine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: "anon-web-session",
          message,
          origin,
          destination: stopsPayload.destination,
          waypoints: stopsPayload.waypoints,
          durationMinutes,
          preferences: toPreferenceWeights(),
          constraints: { avoidBusyRoads: preferences.quiet },
        }),
      });

      if (!response.ok) {
        let detail = "";
        try {
          const errorPayload = (await response.json()) as BackendErrorPayload;
          detail = typeof errorPayload.detail === "string" ? errorPayload.detail : "";
        } catch {
          detail = "";
        }
        throw new Error(detail || `Backend returned ${response.status}`);
      }

      const payload = (await response.json()) as GenerateResponse;
      applyRouteResponse(payload, origin, payload.explanation.summary);
    } catch (error) {
      if (error instanceof TypeError) {
        setRequestError(`Failed to fetch ${backendBaseUrl}. Verify backend is running and CORS is enabled.`);
      } else {
        setRequestError(error instanceof Error ? error.message : "Failed to refine route");
      }
    } finally {
      setStatus("idle");
    }
  };

  const handleUseMyLocation = async () => {
    setRequestError(null);
    setLocationNote(null);

    const origin = await resolveBrowserGeolocation(true);
    if (!origin) {
      setRequestError("Could not resolve your location. Check browser location permissions.");
      return;
    }

    if (origin.accuracy > MAX_ACCEPTABLE_ACCURACY_METERS) {
      setLocationNote(
        `Location found with low accuracy (~${Math.round(origin.accuracy)}m). Move to open sky and retry for better precision.`,
      );
    } else {
      setLocationNote(`Location locked (~${Math.round(origin.accuracy)}m accuracy).`);
    }

    setOriginLat(origin.lat.toFixed(5));
    setOriginLng(origin.lng.toFixed(5));
    void reverseGeocodeOrigin(origin.lat, origin.lng);
    setMapCenter([origin.lng, origin.lat]);
  };

  const clampSidebarWidth = useCallback((value: number) => {
    const containerWidth = shellRef.current?.clientWidth ?? 1200;
    const dynamicMax = Math.min(MAX_SIDEBAR_WIDTH, containerWidth - 320);
    const maxWidth = Math.max(MIN_SIDEBAR_WIDTH, dynamicMax);
    return Math.min(maxWidth, Math.max(MIN_SIDEBAR_WIDTH, value));
  }, []);

  const handleDividerPointerDown = (event: React.PointerEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const divider = event.currentTarget;
    const pointerId = event.pointerId;

    divider.setPointerCapture(pointerId);

    const onPointerMove = (moveEvent: PointerEvent) => {
      const shellLeft = shellRef.current?.getBoundingClientRect().left ?? 0;
      const nextWidth = moveEvent.clientX - shellLeft;
      setSidebarWidth(clampSidebarWidth(nextWidth));
    };

    const cleanup = () => {
      divider.removeEventListener("pointermove", onPointerMove);
      divider.removeEventListener("pointerup", cleanup);
      divider.removeEventListener("pointercancel", cleanup);
      if (divider.hasPointerCapture(pointerId)) {
        divider.releasePointerCapture(pointerId);
      }
    };

    divider.addEventListener("pointermove", onPointerMove);
    divider.addEventListener("pointerup", cleanup);
    divider.addEventListener("pointercancel", cleanup);
  };

  const handleDividerKeyDown = (event: React.KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      setSidebarWidth((prev) => clampSidebarWidth(prev - 16));
      return;
    }
    if (event.key === "ArrowRight") {
      event.preventDefault();
      setSidebarWidth((prev) => clampSidebarWidth(prev + 16));
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setSidebarWidth(clampSidebarWidth(MIN_SIDEBAR_WIDTH));
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setSidebarWidth(clampSidebarWidth(MAX_SIDEBAR_WIDTH));
    }
  };

  return (
    <main className="h-screen overflow-hidden bg-app text-app-foreground">
      <div ref={shellRef} className="flex h-full w-full">
        <aside
          className="flex h-full shrink-0 flex-col border-r border-panel-border bg-panel p-4"
          style={{ width: `${sidebarWidth}px` }}
        >
          <div className="flex items-center gap-2">
            <img src="/favicon.ico" alt="ScenicAI" className="h-9 w-9 rounded-xl" />
            <span className="text-lg font-medium">ScenicAI</span>
          </div>

          <div className="mt-10 space-y-6">
            <section>
              <p className="text-sm font-medium">Starting Point</p>
              <div className="relative mt-3">
                <input
                  value={originSearchText}
                  onChange={(event) => {
                    const value = event.target.value;
                    setOriginSearchText(value);
                    setOriginLabel("");
                    setOriginLat("");
                    setOriginLng("");
                    setOriginSearchError(null);
                    setShowOriginSuggestions(true);
                  }}
                  onFocus={() => {
                    if (originSuggestions.length > 0) {
                      setShowOriginSuggestions(true);
                    }
                  }}
                  onBlur={() => {
                    window.setTimeout(() => {
                      setShowOriginSuggestions(false);
                    }, 120);
                  }}
                  onKeyDown={handleOriginSearchKeyDown}
                  placeholder="Search address, place, or landmark"
                  className="h-9 w-full rounded-xl border border-panel-border bg-white px-3 text-sm"
                  aria-label="Search starting location"
                  aria-autocomplete="list"
                />
                {showOriginSuggestions && (isOriginSearchLoading || originSuggestions.length > 0) ? (
                  <div className="absolute z-20 mt-1 w-full rounded-xl border border-panel-border bg-white p-1 shadow-sm">
                    {isOriginSearchLoading ? (
                      <p className="px-2 py-1 text-xs text-app-muted">Searching...</p>
                    ) : (
                      <ul role="listbox" className="max-h-44 overflow-auto">
                        {originSuggestions.map((suggestion, index) => (
                          <li key={suggestion.id}>
                            <button
                              type="button"
                              onMouseDown={(event) => {
                                event.preventDefault();
                                applyOriginSuggestion(suggestion);
                              }}
                              className={`w-full rounded-lg px-2 py-2 text-left text-xs ${
                                index === activeOriginSuggestionIndex ? "bg-accent/10 text-app-foreground" : "text-app-muted"
                              }`}
                            >
                              <p className="font-medium text-app-foreground">{suggestion.label}</p>
                              <p>{suggestion.fullLabel}</p>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
              </div>
              {originSearchError ? <p className="mt-1 text-xs text-amber-700">{originSearchError}</p> : null}
              <details className="mt-2 rounded-xl border border-panel-border bg-white p-2">
                <summary className="cursor-pointer text-xs text-app-muted">Enter coordinates manually</summary>
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <input
                    value={originLat}
                    onChange={(event) => {
                      setOriginLat(event.target.value);
                      setOriginLabel("");
                    }}
                    placeholder="Latitude"
                    className="h-9 rounded-xl border border-panel-border bg-white px-3 text-sm"
                  />
                  <input
                    value={originLng}
                    onChange={(event) => {
                      setOriginLng(event.target.value);
                      setOriginLabel("");
                    }}
                    placeholder="Longitude"
                    className="h-9 rounded-xl border border-panel-border bg-white px-3 text-sm"
                  />
                </div>
              </details>
              <button
                type="button"
                onClick={handleUseMyLocation}
                className="mt-2 h-8 w-full rounded-lg border border-panel-border bg-white text-xs"
              >
                Use my location
              </button>
            </section>

            <section>
              <p className="text-sm font-medium">Destination (Optional)</p>
              <div className="relative mt-3">
                <input
                  value={destinationSearchText}
                  onChange={(event) => {
                    const value = event.target.value;
                    setDestinationSearchText(value);
                    setDestinationLabel("");
                    setDestinationLat("");
                    setDestinationLng("");
                    setDestinationSearchError(null);
                    setShowDestinationSuggestions(true);
                  }}
                  onFocus={() => {
                    if (destinationSuggestions.length > 0) {
                      setShowDestinationSuggestions(true);
                    }
                  }}
                  onBlur={() => {
                    window.setTimeout(() => {
                      setShowDestinationSuggestions(false);
                    }, 120);
                  }}
                  onKeyDown={handleDestinationSearchKeyDown}
                  placeholder="Search destination"
                  className="h-9 w-full rounded-xl border border-panel-border bg-white px-3 text-sm"
                  aria-label="Search destination"
                  aria-autocomplete="list"
                />
                {showDestinationSuggestions && (isDestinationSearchLoading || destinationSuggestions.length > 0) ? (
                  <div className="absolute z-20 mt-1 w-full rounded-xl border border-panel-border bg-white p-1 shadow-sm">
                    {isDestinationSearchLoading ? (
                      <p className="px-2 py-1 text-xs text-app-muted">Searching...</p>
                    ) : (
                      <ul role="listbox" className="max-h-44 overflow-auto">
                        {destinationSuggestions.map((suggestion, index) => (
                          <li key={suggestion.id}>
                            <button
                              type="button"
                              onMouseDown={(event) => {
                                event.preventDefault();
                                applyDestinationSuggestion(suggestion);
                              }}
                              className={`w-full rounded-lg px-2 py-2 text-left text-xs ${
                                index === activeDestinationSuggestionIndex
                                  ? "bg-accent/10 text-app-foreground"
                                  : "text-app-muted"
                              }`}
                            >
                              <p className="font-medium text-app-foreground">{suggestion.label}</p>
                              <p>{suggestion.fullLabel}</p>
                            </button>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                ) : null}
              </div>
              {destinationSearchError ? <p className="mt-1 text-xs text-amber-700">{destinationSearchError}</p> : null}
            </section>

            <section>
              <div className="flex items-center justify-between">
                <p className="text-sm font-medium">Waypoints (Optional)</p>
                <button
                  type="button"
                  onClick={addWaypoint}
                  disabled={waypoints.length >= MAX_WAYPOINTS}
                  className="h-7 rounded-lg border border-panel-border bg-white px-2 text-xs disabled:opacity-50"
                >
                  Add waypoint
                </button>
              </div>
              <div className="mt-3 space-y-2">
                {waypoints.length === 0 ? (
                  <p className="text-xs text-app-muted">Add up to 3 waypoint stops.</p>
                ) : null}
                {waypoints.map((waypoint, index) => (
                  <div key={`waypoint-${index}`} className="relative rounded-xl border border-panel-border bg-white p-2">
                    <div className="mb-2 flex items-center justify-between">
                      <p className="text-xs font-medium text-app-muted">Waypoint {index + 1}</p>
                      <button
                        type="button"
                        onClick={() => removeWaypoint(index)}
                        className="text-xs text-app-muted hover:text-app-foreground"
                      >
                        Remove
                      </button>
                    </div>
                    <input
                      value={waypoint.searchText}
                      onChange={(event) => {
                        updateWaypointSearchText(index, event.target.value);
                        setWaypointSearchError(null);
                        setActiveWaypointIndex(index);
                        setShowWaypointSuggestions(true);
                      }}
                      onFocus={() => {
                        setActiveWaypointIndex(index);
                        if (waypointSuggestions.length > 0) {
                          setShowWaypointSuggestions(true);
                        }
                      }}
                      onBlur={() => {
                        window.setTimeout(() => {
                          setShowWaypointSuggestions(false);
                        }, 120);
                      }}
                      onKeyDown={(event) => handleWaypointSearchKeyDown(event, index)}
                      placeholder="Search waypoint"
                      className="h-8 w-full rounded-lg border border-panel-border px-2 text-xs"
                      aria-label={`Search waypoint ${index + 1}`}
                    />

                    {activeWaypointIndex === index && showWaypointSuggestions && (isWaypointSearchLoading || waypointSuggestions.length > 0) ? (
                      <div className="absolute left-2 right-2 top-[70px] z-20 rounded-xl border border-panel-border bg-white p-1 shadow-sm">
                        {isWaypointSearchLoading ? (
                          <p className="px-2 py-1 text-xs text-app-muted">Searching...</p>
                        ) : (
                          <ul role="listbox" className="max-h-40 overflow-auto">
                            {waypointSuggestions.map((suggestion, suggestionIndex) => (
                              <li key={suggestion.id}>
                                <button
                                  type="button"
                                  onMouseDown={(event) => {
                                    event.preventDefault();
                                    applyWaypointSuggestion(index, suggestion);
                                  }}
                                  className={`w-full rounded-lg px-2 py-2 text-left text-xs ${
                                    suggestionIndex === activeWaypointSuggestionIndex
                                      ? "bg-accent/10 text-app-foreground"
                                      : "text-app-muted"
                                  }`}
                                >
                                  <p className="font-medium text-app-foreground">{suggestion.label}</p>
                                  <p>{suggestion.fullLabel}</p>
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
              {waypointSearchError ? <p className="mt-1 text-xs text-amber-700">{waypointSearchError}</p> : null}
            </section>

            <section>
              <div className="flex items-center justify-between text-sm font-medium">
                <span>Desired Duration</span>
                <span className="text-accent">{durationMinutes} min</span>
              </div>
              <input
                id="duration"
                type="range"
                min={15}
                max={120}
                step={5}
                value={durationMinutes}
                onChange={(event) =>
                  setSessionState((prev) => ({
                    ...prev,
                    durationMinutes: Number(event.target.value),
                  }))
                }
                className="mt-3 w-full accent-accent"
              />
              <div className="mt-2 flex justify-between text-xs text-app-muted">
                <span>15m</span>
                <span>1h</span>
                <span>2h+</span>
              </div>
            </section>

            <section>
              <p className="text-sm font-medium">Vibe &amp; Scenery</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                {preferenceButtonOrder.map((key) => {
                  const enabled = preferences[key];
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => togglePreference(key)}
                      className={`h-8 rounded-lg border px-3 text-left text-sm capitalize transition ${
                        enabled
                          ? "border-accent bg-accent/10 text-app-foreground"
                          : "border-panel-border bg-white text-app-muted"
                      }`}
                      aria-pressed={enabled}
                    >
                      {preferenceLabels[key]}
                    </button>
                  );
                })}
              </div>
            </section>

            <button
              type="button"
              onClick={handleGenerate}
              className="h-10 w-full rounded-xl bg-app-foreground text-sm font-semibold text-panel"
            >
              {status === "generating"
                ? "Generating scenic route..."
                : status === "refining"
                  ? "Refining route..."
                  : "Generate Scenic Route"}
            </button>

            {requestError ? <p className="text-xs text-red-600">{requestError}</p> : null}
            {locationNote ? <p className="text-xs text-amber-700">{locationNote}</p> : null}

            <section className="space-y-3 border-t border-panel-border pt-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[22px] font-medium leading-tight">{routeTitle}</p>
                  <p className="text-sm text-app-muted">{routeMeta}</p>
                </div>
                <div className="rounded-xl bg-accent/10 px-3 py-2 text-right text-accent">
                  <p className="text-2xl font-semibold leading-none">
                    {scenicScore !== null ? Math.round(scenicScore) : "--"}
                  </p>
                  <p className="text-[10px] font-semibold uppercase tracking-wide">Scenic</p>
                </div>
              </div>
              <div className="rounded-xl border border-panel-border bg-white p-3 text-sm text-app-muted">
                {explanationText} Preferences: {selectedPreferences.join(", ") || "balanced"}.
              </div>

              <div className="rounded-xl border border-panel-border bg-white p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs font-semibold uppercase tracking-wider text-app-muted">Tag Debug</p>
                  <select
                    value={activeDebugTag}
                    onChange={(event) => {
                      setActiveDebugTag(event.target.value as PreferenceKey);
                      if (debugHoverClearTimeoutRef.current !== null) {
                        window.clearTimeout(debugHoverClearTimeoutRef.current);
                        debugHoverClearTimeoutRef.current = null;
                      }
                      setHoveredDebugTarget(null);
                    }}
                    className="h-7 rounded-md border border-panel-border bg-white px-2 text-xs"
                  >
                    {preferenceButtonOrder.map((key) => (
                      <option key={key} value={key}>
                        {debugTagLabels[key]}
                      </option>
                    ))}
                  </select>
                </div>

                <div className="mt-2 max-h-40 space-y-2 overflow-auto pr-1">
                  {debugMatches.length > 0 ? (
                    debugMatches.map((match) => {
                      const objectTitle = match.name?.trim() || match.objectId;
                      const tagSummary = Object.entries(match.tags)
                        .filter(([key]) => key !== "name")
                        .slice(0, 3)
                        .map(([key, value]) => `${key}=${value}`)
                        .join(", ");

                      return (
                        <div
                          key={match.objectId}
                          onMouseEnter={() => {
                            if (debugHoverClearTimeoutRef.current !== null) {
                              window.clearTimeout(debugHoverClearTimeoutRef.current);
                              debugHoverClearTimeoutRef.current = null;
                            }
                            if (typeof match.lat === "number" && typeof match.lng === "number") {
                              setHoveredDebugTarget({
                                coordinates: [match.lng, match.lat],
                                name: objectTitle,
                              });
                              return;
                            }
                            setHoveredDebugTarget(null);
                          }}
                          onMouseLeave={() => {
                            if (debugHoverClearTimeoutRef.current !== null) {
                              window.clearTimeout(debugHoverClearTimeoutRef.current);
                            }
                            debugHoverClearTimeoutRef.current = window.setTimeout(() => {
                              setHoveredDebugTarget(null);
                              debugHoverClearTimeoutRef.current = null;
                            }, DEBUG_HOVER_CLEAR_DELAY_MS);
                          }}
                          className="rounded-lg border border-panel-border p-2 text-xs text-app-muted transition duration-150 hover:-translate-y-0.5 hover:scale-[1.01] hover:border-accent/40 hover:bg-accent/5"
                        >
                          <p className="font-medium text-app-foreground">{objectTitle}</p>
                          <p>{tagSummary || "Tagged scenic feature"}</p>
                          {typeof match.lat === "number" && typeof match.lng === "number" ? (
                            <p>
                              {match.lat.toFixed(5)}, {match.lng.toFixed(5)}
                            </p>
                          ) : null}
                        </div>
                      );
                    })
                  ) : (
                    <div className="space-y-1">
                      <p className="text-xs text-app-muted">
                        No matched objects found for {debugTagLabels[activeDebugTag].toLowerCase()} on this route.
                      </p>
                      {poiContextFetchFailed ? (
                        <p className="text-xs text-amber-700">
                          Nearby POI lookup was unavailable for this request, so tag debug may be incomplete.
                        </p>
                      ) : null}
                    </div>
                  )}
                </div>
              </div>
            </section>

            <section>
              <p className="text-xs font-semibold uppercase tracking-wider text-app-muted">Refine Route</p>
              <div className="mt-2 flex items-center rounded-full border border-panel-border bg-white pl-3 pr-1">
                <input
                  id="refine"
                  value={refineText}
                  onChange={(event) =>
                    setSessionState((prev) => ({
                      ...prev,
                      refineText: event.target.value,
                    }))
                  }
                  placeholder="e.g., Make it completely flat..."
                  className="h-8 flex-1 bg-transparent text-sm outline-none"
                />
                <button
                  type="button"
                  onClick={handleRefine}
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-app-foreground text-panel"
                  aria-label="Submit refine request"
                >
                  ↑
                </button>
              </div>
            </section>
          </div>
        </aside>

        <div className="group relative flex h-full w-3 shrink-0 items-center justify-center bg-panel">
          <button
            type="button"
            onPointerDown={handleDividerPointerDown}
            onKeyDown={handleDividerKeyDown}
            aria-label="Resize split view"
            className="h-full w-full cursor-col-resize border-r border-panel-border/70 bg-panel/70 outline-none transition hover:bg-accent/5 focus-visible:ring-2 focus-visible:ring-accent/40"
          />
          <span className="pointer-events-none absolute h-12 w-1 rounded-full bg-panel-border/80 transition group-hover:bg-accent/45" />
        </div>

        <section className="relative h-full flex-1 overflow-hidden bg-panel">
          <ScenicMap
            routeCoordinates={selectedRouteCoordinates}
            fallbackCenter={mapCenter}
            highlightedLocation={hoveredDebugTarget}
          />
        </section>
      </div>
    </main>
  );
}
