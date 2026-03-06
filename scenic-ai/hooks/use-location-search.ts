import { useCallback, useEffect, useRef, useState } from "react";

export type PlaceSuggestion = {
  id: string;
  label: string;
  fullLabel: string;
  location: {
    lat: number;
    lng: number;
    label?: string | null;
  };
};

type UseLocationSearchArgs = {
  backendBaseUrl: string;
  proximity: [number, number];
  debounceMs: number;
  unavailableMessage: string;
};

type UseLocationSearchResult = {
  lat: string;
  lng: string;
  label: string;
  searchText: string;
  suggestions: PlaceSuggestion[];
  isLoading: boolean;
  showSuggestions: boolean;
  activeSuggestionIndex: number;
  error: string | null;
  setSuggestions: (value: PlaceSuggestion[]) => void;
  setShowSuggestions: (value: boolean) => void;
  setActiveSuggestionIndex: (value: number | ((prev: number) => number)) => void;
  setError: (value: string | null) => void;
  setLat: (value: string) => void;
  setLng: (value: string) => void;
  setLabel: (value: string) => void;
  setSearchText: (value: string) => void;
  setResolvedLabel: (value: string) => void;
  clearError: () => void;
  clearSuggestions: () => void;
  handleSearchTextInput: (value: string) => void;
  handleFocus: () => void;
  handleBlur: () => void;
  handleKeyDown: (event: React.KeyboardEvent<HTMLInputElement>, onSelect: (suggestion: PlaceSuggestion) => void) => void;
  applySuggestion: (suggestion: PlaceSuggestion) => void;
};

const extractBackendErrorDetail = async (response: Response): Promise<string | null> => {
  try {
    const payload = (await response.json()) as { detail?: unknown; message?: unknown };

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

export const useLocationSearch = ({
  backendBaseUrl,
  proximity,
  debounceMs,
  unavailableMessage,
}: UseLocationSearchArgs): UseLocationSearchResult => {
  const [lat, setLat] = useState("");
  const [lng, setLng] = useState("");
  const [label, setLabel] = useState("");
  const [searchText, setSearchText] = useState("");
  const [suggestions, setSuggestions] = useState<PlaceSuggestion[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [activeSuggestionIndex, setActiveSuggestionIndex] = useState(-1);
  const [error, setError] = useState<string | null>(null);

  const searchAbortRef = useRef<AbortController | null>(null);
  const searchDebounceRef = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (searchDebounceRef.current !== null) {
        window.clearTimeout(searchDebounceRef.current);
      }
      searchAbortRef.current?.abort();
    };
  }, []);

  const fetchSuggestions = useCallback(
    async (query: string) => {
      searchAbortRef.current?.abort();
      const controller = new AbortController();
      searchAbortRef.current = controller;

      setIsLoading(true);
      setError(null);

      try {
        const response = await fetch(`${backendBaseUrl}/api/v1/location/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            limit: 6,
            proximityLat: proximity[1],
            proximityLng: proximity[0],
          }),
          signal: controller.signal,
        });

        if (!response.ok) {
          const detail = await extractBackendErrorDetail(response);
          throw new Error(detail || `Location search failed (${response.status})`);
        }

        const payload = (await response.json()) as { results?: PlaceSuggestion[] };
        const nextSuggestions = Array.isArray(payload.results) ? payload.results : [];
        setSuggestions(nextSuggestions);
        setShowSuggestions(true);
        setActiveSuggestionIndex(nextSuggestions.length > 0 ? 0 : -1);
      } catch (fetchError) {
        if (fetchError instanceof DOMException && fetchError.name === "AbortError") {
          return;
        }
        setSuggestions([]);
        setActiveSuggestionIndex(-1);
        setError(fetchError instanceof Error ? fetchError.message : unavailableMessage);
      } finally {
        setIsLoading(false);
      }
    },
    [backendBaseUrl, proximity, unavailableMessage],
  );

  useEffect(() => {
    const query = searchText.trim();
    if (!query || query.length < 2 || query === label) {
      setSuggestions([]);
      setShowSuggestions(false);
      setIsLoading(false);
      setError(null);
      return;
    }

    if (searchDebounceRef.current !== null) {
      window.clearTimeout(searchDebounceRef.current);
    }

    searchDebounceRef.current = window.setTimeout(() => {
      fetchSuggestions(query);
    }, debounceMs);

    return () => {
      if (searchDebounceRef.current !== null) {
        window.clearTimeout(searchDebounceRef.current);
      }
    };
  }, [debounceMs, fetchSuggestions, label, searchText]);

  const handleSearchTextInput = (value: string) => {
    setSearchText(value);
    setLabel("");
    setLat("");
    setLng("");
    setError(null);
    setShowSuggestions(true);
  };

  const handleFocus = () => {
    if (suggestions.length > 0) {
      setShowSuggestions(true);
    }
  };

  const handleBlur = () => {
    window.setTimeout(() => {
      setShowSuggestions(false);
    }, 120);
  };

  const clearSuggestions = () => {
    setSuggestions([]);
    setShowSuggestions(false);
    setActiveSuggestionIndex(-1);
  };

  const applySuggestion = (suggestion: PlaceSuggestion) => {
    setLat(suggestion.location.lat.toFixed(5));
    setLng(suggestion.location.lng.toFixed(5));
    setLabel(suggestion.fullLabel);
    setSearchText(suggestion.fullLabel);
    clearSuggestions();
  };

  const handleKeyDown = (
    event: React.KeyboardEvent<HTMLInputElement>,
    onSelect: (suggestion: PlaceSuggestion) => void,
  ) => {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      if (!showSuggestions && suggestions.length > 0) {
        setShowSuggestions(true);
      }
      setActiveSuggestionIndex((prev) =>
        suggestions.length === 0 ? -1 : Math.min(prev + 1, suggestions.length - 1),
      );
      return;
    }

    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveSuggestionIndex((prev) => (suggestions.length === 0 ? -1 : Math.max(prev - 1, 0)));
      return;
    }

    if (event.key === "Enter") {
      if (showSuggestions && activeSuggestionIndex >= 0 && suggestions[activeSuggestionIndex]) {
        event.preventDefault();
        onSelect(suggestions[activeSuggestionIndex]);
      }
      return;
    }

    if (event.key === "Escape") {
      setShowSuggestions(false);
    }
  };

  const setResolvedLabel = (value: string) => {
    setLabel(value);
    setSearchText(value);
  };

  return {
    lat,
    lng,
    label,
    searchText,
    suggestions,
    isLoading,
    showSuggestions,
    activeSuggestionIndex,
    error,
    setSuggestions,
    setShowSuggestions,
    setActiveSuggestionIndex,
    setError,
    setLat,
    setLng,
    setLabel,
    setSearchText,
    setResolvedLabel,
    clearError: () => setError(null),
    clearSuggestions,
    handleSearchTextInput,
    handleFocus,
    handleBlur,
    handleKeyDown,
    applySuggestion,
  };
};
