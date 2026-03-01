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

type ScoreDebugData = {
  contextAvailable: boolean;
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

type GeoOrigin = {
  lat: number;
  lng: number;
  accuracy: number;
};

const STORAGE_KEY = "scenicai.session";

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

export function ScenicPlannerShell() {
  const shellRef = useRef<HTMLDivElement>(null);
  const backendBaseUrl = useMemo(() => resolveBackendBaseUrl(), []);
  const [sessionState, setSessionState] = useState<SessionState>(defaultState);
  const [isStorageReady, setIsStorageReady] = useState(false);
  const [status, setStatus] = useState<"idle" | "generating" | "refining">("idle");
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);
  const [originLat, setOriginLat] = useState("");
  const [originLng, setOriginLng] = useState("");
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
    setSelectedRouteCoordinates(selected.geometry.coordinates);
    setMapCenter([origin.lng, origin.lat]);
  };

  const debugMatches = selectedRouteDebug?.tagObjectMatches?.[activeDebugTag] ?? [];

  const togglePreference = (key: PreferenceKey) => {
    setSessionState((prev) => ({
      ...prev,
      preferences: { ...prev.preferences, [key]: !prev.preferences[key] },
    }));
  };

  const handleGenerate = async () => {
    setRequestError(null);
    setLocationNote(null);
    setStatus("generating");

    const origin = await resolveOrigin();
    if (!origin) {
      setStatus("idle");
      setRequestError("Location unavailable. Enter latitude/longitude or allow geolocation.");
      return;
    }

    if (origin.accuracy > MAX_ACCEPTABLE_ACCURACY_METERS) {
      setLocationNote(
        `Low GPS accuracy (~${Math.round(origin.accuracy)}m). You can retry Use my location for a better fix.`,
      );
    }

    try {
      const response = await fetch(`${backendBaseUrl}/api/v1/route/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          origin,
          durationMinutes,
          preferences: toPreferenceWeights(),
          constraints: { avoidBusyRoads: preferences.quiet },
          sessionId: "anon-web-session",
          refinementText: refineText || undefined,
        }),
      });

      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
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
      setRequestError("Location unavailable. Enter latitude/longitude or allow geolocation.");
      return;
    }

    try {
      const response = await fetch(`${backendBaseUrl}/api/v1/route/refine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          sessionId: "anon-web-session",
          message,
          origin,
          durationMinutes,
          preferences: toPreferenceWeights(),
          constraints: { avoidBusyRoads: preferences.quiet },
        }),
      });

      if (!response.ok) {
        throw new Error(`Backend returned ${response.status}`);
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
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-app-foreground text-xs font-semibold text-panel">
              S
            </div>
            <span className="text-lg font-medium">ScenicAI</span>
          </div>

          <div className="mt-10 space-y-6">
            <section>
              <p className="text-sm font-medium">Starting Point</p>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <input
                  value={originLat}
                  onChange={(event) => setOriginLat(event.target.value)}
                  placeholder="Latitude"
                  className="h-9 rounded-xl border border-panel-border bg-white px-3 text-sm"
                />
                <input
                  value={originLng}
                  onChange={(event) => setOriginLng(event.target.value)}
                  placeholder="Longitude"
                  className="h-9 rounded-xl border border-panel-border bg-white px-3 text-sm"
                />
              </div>
              <button
                type="button"
                onClick={handleUseMyLocation}
                className="mt-2 h-8 w-full rounded-lg border border-panel-border bg-white text-xs"
              >
                Use my location
              </button>
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
                    onChange={(event) => setActiveDebugTag(event.target.value as PreferenceKey)}
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
                        <div key={match.objectId} className="rounded-lg border border-panel-border p-2 text-xs text-app-muted">
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
                    <p className="text-xs text-app-muted">
                      No matched objects found for {debugTagLabels[activeDebugTag].toLowerCase()} on this route.
                    </p>
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
          <ScenicMap routeCoordinates={selectedRouteCoordinates} fallbackCenter={mapCenter} />
        </section>
      </div>
    </main>
  );
}
