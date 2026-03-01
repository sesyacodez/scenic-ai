"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type PreferenceKey = "nature" | "water" | "historic" | "quiet";

type Preferences = Record<PreferenceKey, boolean>;

type SessionState = {
  schemaVersion: 1;
  durationMinutes: number;
  preferences: Preferences;
  refineText: string;
};

const STORAGE_KEY = "scenicai.session";

const defaultPreferences: Preferences = {
  nature: true,
  water: false,
  historic: false,
  quiet: true,
};

const defaultState: SessionState = {
  schemaVersion: 1,
  durationMinutes: 45,
  preferences: defaultPreferences,
  refineText: "",
};

const MIN_SIDEBAR_WIDTH = 280;
const MAX_SIDEBAR_WIDTH = 460;
const DEFAULT_SIDEBAR_WIDTH = 308;

export function ScenicPlannerShell() {
  const shellRef = useRef<HTMLDivElement>(null);
  const [sessionState, setSessionState] = useState<SessionState>(() => {
    if (typeof window === "undefined") {
      return defaultState;
    }

    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return defaultState;
    }

    try {
      const parsed = JSON.parse(raw) as SessionState;
      if (parsed.schemaVersion !== 1) {
        return defaultState;
      }
      return parsed;
    } catch {
      window.localStorage.removeItem(STORAGE_KEY);
      return defaultState;
    }
  });
  const [status, setStatus] = useState<"idle" | "generating">("idle");
  const [sidebarWidth, setSidebarWidth] = useState(DEFAULT_SIDEBAR_WIDTH);

  const { durationMinutes, preferences, refineText } = sessionState;

  useEffect(() => {
    const state: SessionState = {
      schemaVersion: 1,
      durationMinutes,
      preferences,
      refineText,
    };
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [durationMinutes, preferences, refineText]);

  const selectedPreferences = useMemo(
    () => Object.entries(preferences).filter(([, enabled]) => enabled).map(([key]) => key),
    [preferences],
  );

  const togglePreference = (key: PreferenceKey) => {
    setSessionState((prev) => ({
      ...prev,
      preferences: { ...prev.preferences, [key]: !prev.preferences[key] },
    }));
  };

  const handleGenerate = () => {
    setStatus("generating");
    window.setTimeout(() => {
      setStatus("idle");
    }, 1000);
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
              <div className="mt-3 flex h-9 items-center rounded-xl border border-panel-border bg-white px-3 text-sm text-app-foreground/85">
                <span className="mr-2 text-app-muted">◉</span>
                142 Riverfront Ave, Downtown
              </div>
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
                {(["nature", "water", "historic", "quiet"] as const).map((key) => {
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
                      {key}
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
              {status === "generating" ? "Generating scenic route..." : "Generate Scenic Route"}
            </button>

            <section className="space-y-3 border-t border-panel-border pt-4">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <p className="text-[22px] font-medium leading-tight">Riverside Botanical Loop</p>
                  <p className="text-sm text-app-muted">3.8 km ・ 42 min walk</p>
                </div>
                <div className="rounded-xl bg-accent/10 px-3 py-2 text-right text-accent">
                  <p className="text-2xl font-semibold leading-none">94</p>
                  <p className="text-[10px] font-semibold uppercase tracking-wide">Scenic</p>
                </div>
              </div>
              <div className="rounded-xl border border-panel-border bg-white p-3 text-sm text-app-muted">
                This route maximizes your time near the water and favors {selectedPreferences.join(", ")} while
                avoiding busy streets.
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
          <div className="absolute inset-0 scenic-gradient opacity-35" aria-hidden />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,_var(--color-panel-border)_1px,_transparent_1px)] [background-size:22px_22px] opacity-35" />

          <svg className="absolute inset-0 h-full w-full" viewBox="0 0 1100 760" preserveAspectRatio="none" aria-hidden>
            <path d="M30 190 C 290 220, 540 250, 1050 285" stroke="currentColor" className="text-panel-border" strokeWidth="6" fill="none" strokeLinecap="round" opacity="0.6" />
            <path d="M160 95 C 185 260, 205 510, 255 700" stroke="currentColor" className="text-panel-border" strokeWidth="6" fill="none" strokeLinecap="round" opacity="0.55" />
            <path d="M690 50 C 680 180, 650 430, 610 745" stroke="currentColor" className="text-panel-border" strokeWidth="6" fill="none" strokeLinecap="round" opacity="0.45" />
            <path d="M0 495 C 310 575, 650 535, 1100 460" stroke="currentColor" className="text-accent" strokeWidth="26" fill="none" strokeLinecap="round" opacity="0.08" />

            <defs>
              <radialGradient id="routeGlow" cx="50%" cy="30%" r="55%">
                <stop offset="0%" stopColor="currentColor" className="text-accent" stopOpacity="0.2" />
                <stop offset="100%" stopColor="currentColor" className="text-accent" stopOpacity="0" />
              </radialGradient>
            </defs>
            <ellipse cx="520" cy="390" rx="260" ry="240" fill="url(#routeGlow)" />

            <path
              d="M190 425 C 245 220, 530 170, 730 255 C 845 300, 925 385, 965 570"
              stroke="currentColor"
              className="text-accent"
              strokeWidth="6"
              fill="none"
              strokeLinecap="round"
            />
            <circle cx="190" cy="425" r="14" fill="white" stroke="currentColor" className="text-panel-border" strokeWidth="5" />
            <circle cx="190" cy="425" r="5" fill="currentColor" className="text-app-foreground" />
            <circle cx="965" cy="570" r="21" fill="none" stroke="currentColor" className="text-accent" strokeWidth="8" opacity="0.35" />
            <circle cx="965" cy="570" r="12" fill="none" stroke="currentColor" className="text-accent" strokeWidth="6" />
          </svg>

          <button className="absolute right-5 top-4 flex h-8 w-8 items-center justify-center rounded-full border border-panel-border bg-white text-xs text-app-muted">
            N
          </button>
          <button className="absolute left-[56%] top-[30%] flex h-8 w-8 items-center justify-center rounded-lg border border-panel-border bg-white text-accent">
            ☐
          </button>
          <div className="absolute bottom-4 right-4 space-y-2">
            <button className="block h-7 w-7 rounded-lg border border-panel-border bg-white" aria-label="Map control" />
            <button className="block h-7 w-7 rounded-lg border border-panel-border bg-white" aria-label="Map control" />
            <button className="block h-7 w-7 rounded-lg border border-panel-border bg-white" aria-label="Map control" />
          </div>
        </section>
      </div>
    </main>
  );
}
