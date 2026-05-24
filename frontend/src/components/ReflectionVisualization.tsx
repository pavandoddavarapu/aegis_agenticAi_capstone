"use client";

import { useTelemetryStore } from "@/stores/telemetryStore";
import { ArrowRight, RefreshCw, AlertTriangle } from "lucide-react";

export default function ReflectionVisualization() {
  const { data } = useTelemetryStore();
  
  if (!data || !data.retry_count || data.retry_count === 0) {
    return (
      <div className="bg-card rounded-lg border border-border p-5">
        <div className="flex items-center gap-2 mb-4">
          <RefreshCw className="w-4 h-4 text-muted-foreground" />
          <h3 className="font-semibold text-sm">Adaptive Reflection</h3>
        </div>
        <p className="text-xs text-muted-foreground italic">No reflection or retry required for this request.</p>
      </div>
    );
  }

  interface ValidationTelemetryEvent {
    event_type: string;
    node?: string;
    confidence_score?: number;
  }

  // Extract prior confidence from early validation events if available
  const validationEvents = data?.events?.filter((e: ValidationTelemetryEvent) => e.event_type === "node_end" && e.node === "validate") || [];
  const priorConfidence = validationEvents.length > 1 ? parseFloat(validationEvents[0].confidence_score || 0).toFixed(2) : 0.0;
  const triggerReason = validationEvents.length > 1 
    ? `Initial validation score (${priorConfidence}) fell below strict safety threshold.` 
    : "System detected missing critical evidence context.";

  const reflection = {
    trigger_reason: triggerReason,
    retry_count: data.retry_count,
    confidence_before: priorConfidence,
    confidence_after: data.final_confidence ? data.final_confidence.toFixed(2) : "N/A",
    expanded_query: data.query_hash || "Semantic Query Expansion",
  };

  return (
    <div className="bg-card rounded-lg border border-border p-5">
      <div className="flex items-center gap-2 mb-4">
        <RefreshCw className="w-4 h-4 text-amber-500" />
        <h3 className="font-semibold text-sm">Adaptive Reflection</h3>
      </div>

      <div className="bg-secondary/40 rounded-lg p-4 mb-4 border border-border/50">
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="w-4 h-4 text-orange-400" />
          <span className="text-xs font-semibold text-orange-400 uppercase tracking-wider">Trigger Reason</span>
        </div>
        <p className="text-sm text-foreground/80">{reflection.trigger_reason}</p>
      </div>

      <div className="grid grid-cols-[1fr_auto_1fr] gap-4 items-center">
        <div className="bg-secondary/40 border border-border/50 p-4 rounded-lg flex flex-col items-center justify-center text-center">
          <span className="text-xs text-muted-foreground mb-1 uppercase font-semibold tracking-wider">Before</span>
          <span className="text-2xl font-bold text-orange-400">{reflection.confidence_before}</span>
        </div>
        
        <div className="flex flex-col items-center text-muted-foreground">
          <span className="text-[10px] font-mono bg-secondary px-2 py-1 rounded mb-2">Retry {reflection.retry_count}</span>
          <ArrowRight className="w-5 h-5 text-primary animate-pulse" />
        </div>

        <div className="bg-secondary/40 border border-border/50 p-4 rounded-lg flex flex-col items-center justify-center text-center">
          <span className="text-xs text-muted-foreground mb-1 uppercase font-semibold tracking-wider">After</span>
          <span className="text-2xl font-bold text-green-500">{reflection.confidence_after}</span>
        </div>
      </div>

      <div className="mt-4 pt-4 border-t border-border/50">
        <span className="text-[10px] text-muted-foreground uppercase font-semibold tracking-wider block mb-1">
          Expanded Query Used
        </span>
        <code className="text-xs text-primary/80 block break-words bg-primary/5 p-2 rounded">
          {reflection.expanded_query}
        </code>
      </div>
    </div>
  );
}
