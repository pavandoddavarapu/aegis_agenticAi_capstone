"use client";

import { mockWorkflowData } from "@/lib/mock-data";

export default function ExecutionTimeline() {
  const timeline = mockWorkflowData.timeline;
  const totalDuration = timeline.reduce((acc, curr) => acc + curr.duration_ms, 0);

  return (
    <div className="bg-card rounded-lg border border-border p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-sm">Execution Timeline</h3>
        <span className="text-xs text-muted-foreground bg-secondary px-2 py-1 rounded-md">
          {totalDuration}ms total
        </span>
      </div>

      <div className="relative">
        {timeline.map((step, idx) => {
          const width = Math.max((step.duration_ms / totalDuration) * 100, 2);
          const isSlow = step.duration_ms > 500;
          
          return (
            <div key={idx} className="flex items-center gap-4 mb-3 text-sm relative">
              <div className="w-28 flex-shrink-0 text-right font-mono text-xs text-muted-foreground">
                {step.node}
              </div>
              
              <div className="flex-1 flex items-center group">
                <div 
                  className={`h-2 rounded-full transition-all ${
                    !step.success 
                      ? "bg-destructive" 
                      : isSlow 
                        ? "bg-amber-500" 
                        : "bg-primary"
                  }`}
                  style={{ width: `${width}%` }}
                />
                <span className="ml-3 text-xs text-muted-foreground opacity-70 group-hover:opacity-100 transition-opacity">
                  {step.duration_ms}ms
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
