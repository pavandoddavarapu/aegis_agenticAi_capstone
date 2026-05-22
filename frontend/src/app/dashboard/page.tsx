import WorkflowGraph from "@/components/WorkflowGraph";
import ExecutionTimeline from "@/components/ExecutionTimeline";
import RetrievalAnalytics from "@/components/RetrievalAnalytics";
import GroundingPanel from "@/components/GroundingPanel";
import ReflectionVisualization from "@/components/ReflectionVisualization";
import DecisionTraceViewer from "@/components/DecisionTraceViewer";
import { mockWorkflowData } from "@/lib/mock-data";

export default function DashboardPage() {
  return (
    <div className="p-6 max-w-[1600px] mx-auto h-full flex flex-col">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground">Orchestration Telemetry</h2>
          <p className="text-sm text-muted-foreground mt-1">Live execution trace for request: <span className="font-mono text-primary/80">{mockWorkflowData.request_id}</span></p>
        </div>
        <div className="flex items-center gap-3">
          <div className="bg-secondary/50 border border-border px-3 py-1.5 rounded-md flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${mockWorkflowData.escalation_decision ? 'bg-destructive' : 'bg-green-500'}`} />
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              {mockWorkflowData.escalation_decision ? 'Escalated' : 'Resolved'}
            </span>
          </div>
          <div className="bg-secondary/50 border border-border px-3 py-1.5 rounded-md">
            <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mr-2">Risk Level</span>
            <span className="text-xs font-bold text-destructive uppercase">{mockWorkflowData.risk_level}</span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-12 gap-6 flex-1 min-h-0">
        {/* CENTER PANEL (Graph + Timeline + Retrieval) */}
        <div className="col-span-8 flex flex-col gap-6 h-full overflow-hidden">
          <div className="flex-1 bg-card rounded-lg border border-border overflow-hidden min-h-[400px]">
             <WorkflowGraph />
          </div>
          <div className="shrink-0">
            <ExecutionTimeline />
          </div>
          <div className="shrink-0 h-[280px]">
            <RetrievalAnalytics />
          </div>
        </div>

        {/* RIGHT PANEL (Trace + Grounding + Reflection) */}
        <div className="col-span-4 flex flex-col gap-6 h-full overflow-y-auto pr-2 pb-6 custom-scrollbar">
          <div className="shrink-0 h-[250px]">
            <DecisionTraceViewer />
          </div>
          
          <div className="shrink-0 h-[380px]">
            <GroundingPanel />
          </div>

          <div className="shrink-0">
             <ReflectionVisualization />
          </div>
        </div>
      </div>
    </div>
  );
}
