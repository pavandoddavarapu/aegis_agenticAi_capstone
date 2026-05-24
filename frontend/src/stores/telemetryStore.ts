import { create } from "zustand";
import { getApiBase } from "@/lib/utils";

interface TelemetryEvent {
  event_type: string;
  dense_candidates?: number;
  sparse_candidates?: number;
  final_docs?: number;
  top_score?: number;
  avg_score?: number;
  node?: string;
  confidence_score?: any;
}

interface TelemetryData {
  request_id?: string;
  escalation_required?: boolean;
  risk_level?: string;
  events?: TelemetryEvent[];
  query_type?: string;
  selected_workflow?: string;
  workflow?: string;
  status?: string;
  evidence_count?: number;
  retry_count?: number;
  final_confidence?: number;
  query_hash?: string;
}

interface TelemetryTimeline {
  request_id?: string;
  total_ms?: number;
  timeline?: Array<{ node: string; duration_ms: number; success: boolean }>;
}

interface TelemetryMetrics {
  total_requests?: number;
}

interface TelemetryState {
  data: TelemetryData | null;
  timeline: TelemetryTimeline | null;
  metrics: TelemetryMetrics | null;
  isPolling: boolean;
  startPolling: () => void;
  stopPolling: () => void;
  fetchLatest: () => Promise<void>;
}

const API_BASE = getApiBase();

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
