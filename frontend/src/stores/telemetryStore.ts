import { create } from "zustand";

interface TelemetryState {
  data: any | null;
  timeline: any | null;
  metrics: any | null;
  isPolling: boolean;
  startPolling: () => void;
  stopPolling: () => void;
  fetchLatest: () => Promise<void>;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

let pollInterval: NodeJS.Timeout | null = null;

export const useTelemetryStore = create<TelemetryState>((set, get) => ({
  data: null,
  timeline: null,
  metrics: null,
  isPolling: false,

  fetchLatest: async () => {
    try {
      const [traceRes, timelineRes, metricsRes] = await Promise.all([
        fetch(`${API_BASE}/monitoring/latest/trace`).catch(() => null),
        fetch(`${API_BASE}/monitoring/latest/timeline`).catch(() => null),
        fetch(`${API_BASE}/monitoring/metrics`).catch(() => null),
      ]);

      if (traceRes?.ok) {
        const data = await traceRes.json();
        set({ data });
      }
      if (timelineRes?.ok) {
        const timeline = await timelineRes.json();
        set({ timeline });
      }
      if (metricsRes?.ok) {
        const metrics = await metricsRes.json();
        set({ metrics });
      }
    } catch (err) {
      console.error("Telemetry fetch failed", err);
    }
  },

  startPolling: () => {
    const { isPolling, fetchLatest } = get();
    if (isPolling) return;
    set({ isPolling: true });
    fetchLatest();
    pollInterval = setInterval(() => {
      get().fetchLatest();
    }, 2000);
  },

  stopPolling: () => {
    if (pollInterval) {
      clearInterval(pollInterval);
      pollInterval = null;
    }
    set({ isPolling: false });
  },
}));
