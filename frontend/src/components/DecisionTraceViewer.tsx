"use client";

import { mockWorkflowData } from "@/lib/mock-data";

export default function DecisionTraceViewer() {
  const trace = {
    query_type: mockWorkflowData.query_type,
    risk_level: mockWorkflowData.risk_level,
    workflow: mockWorkflowData.workflow,
    retrieval_strategy: mockWorkflowData.retrieval_strategy,
    validation_policy: mockWorkflowData.validation_policy,
    reflection_strategy: mockWorkflowData.reflection_strategy,
    escalation_decision: mockWorkflowData.escalation_decision,
  };

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
        <pre className="text-[11px] font-mono leading-relaxed text-blue-300">
          <span className="text-foreground">{"{"}</span>
          {Object.entries(trace).map(([key, value], idx, arr) => (
            <div key={key} className="pl-4">
              <span className="text-blue-400">"{key}"</span>
              <span className="text-foreground">: </span>
              <span className={typeof value === 'boolean' ? 'text-orange-400' : 'text-green-400'}>
                {typeof value === 'boolean' ? value.toString() : `"${value}"`}
              </span>
              {idx < arr.length - 1 && <span className="text-foreground">,</span>}
            </div>
          ))}
          <span className="text-foreground">{"}"}</span>
        </pre>
      </div>
    </div>
  );
}
