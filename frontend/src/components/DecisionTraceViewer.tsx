"use client";

import { useTelemetryStore } from "@/stores/telemetryStore";

export default function DecisionTraceViewer() {
  const { data } = useTelemetryStore();
  
  const trace = data ? {
    query_type: data.query_type || "N/A",
    risk_level: data.risk_level || "N/A",
    workflow: data.selected_workflow || data.workflow || "N/A",
    status: data.status || "N/A",
    escalation_required: data.escalation_required || false,
    evidence_count: data.evidence_count || 0,
    retry_count: data.retry_count || 0,
    final_confidence: data.final_confidence || 0,
  } : null;

  return (
    <div className="bg-card rounded-lg border border-border p-5 h-full flex flex-col">
      <div className="flex items-center gap-2 mb-4">
        <div className="w-2 h-2 rounded-full bg-blue-500" />
        <h3 className="font-semibold text-sm">Decision Trace</h3>
      </div>
      
      <p className="text-xs text-muted-foreground mb-4">
        Orchestration policies applied by the Decision Agent prior to execution.
      </p>

      <div className="bg-black/40 p-4 rounded-md flex-1 overflow-auto border border-border/50">
        {!trace ? (
           <div className="text-xs text-muted-foreground italic">Waiting for decision trace...</div>
        ) : (
          <pre className="text-[11px] font-mono leading-relaxed text-blue-300">
            <span className="text-foreground">{"{"}</span>
            {Object.entries(trace).map(([key, value], idx, arr) => (
              <div key={key} className="pl-4">
                <span className="text-blue-400">&quot;{key}&quot;</span>
                <span className="text-foreground">: </span>
                <span className={typeof value === 'boolean' ? 'text-orange-400' : 'text-green-400'}>
                  {typeof value === 'boolean' ? value.toString() : typeof value === 'number' ? value : `"${value}"`}
                </span>
                {idx < arr.length - 1 && <span className="text-foreground">,</span>}
              </div>
            ))}
            <span className="text-foreground">{"}"}</span>
          </pre>
        )}
      </div>
    </div>
  );
}
