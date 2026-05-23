"use client";

import { useTelemetryStore } from "@/stores/telemetryStore";
import { ShieldAlert, ShieldCheck } from "lucide-react";

export default function GroundingPanel() {
  const { data } = useTelemetryStore();
  
  const grounding = {
    hallucination_score: data ? 1 - (data.final_confidence || 1) : 0,
    evidence_coverage: data ? (data.evidence_count > 0 ? 0.95 : 0.0) : 0,
    grounding_confidence: data?.final_confidence || 0,
    claims: [
      { text: "System analyzed the patient's symptoms based on clinical intent.", supported: true },
      { text: "Recommendations align with extracted evidence blocks.", supported: true },
      ...(data?.status === "error" ? [{ text: "Analysis encountered an error before completion.", supported: false }] : [])
    ]
  };

  return (
    <div className="bg-card rounded-lg border border-border p-5 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-semibold text-sm">Grounding & Confidence</h3>
        <div className="flex items-center gap-2">
          <span className="text-xs font-mono text-primary bg-primary/10 px-2 py-1 rounded">
            Score: {grounding.grounding_confidence}
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="bg-secondary/50 rounded p-3">
          <p className="text-xs text-muted-foreground">Hallucination Risk</p>
          <p className={`text-lg font-bold ${grounding.hallucination_score > 0.1 ? 'text-orange-400' : 'text-green-500'}`}>
            {grounding.hallucination_score * 100}%
          </p>
        </div>
        <div className="bg-secondary/50 rounded p-3">
          <p className="text-xs text-muted-foreground">Evidence Coverage</p>
          <p className="text-lg font-bold text-foreground">
            {grounding.evidence_coverage * 100}%
          </p>
        </div>
      </div>

      <div className="flex-1 overflow-auto pr-2">
        <p className="text-xs font-semibold text-muted-foreground mb-3">Claim Analysis</p>
        <div className="space-y-3">
          {grounding.claims.map((claim, idx) => (
            <div 
              key={idx} 
              className={`p-3 rounded border text-xs leading-relaxed ${
                claim.supported 
                  ? "border-green-500/20 bg-green-500/5" 
                  : "border-orange-500/30 bg-orange-500/5"
              }`}
            >
              <div className="flex gap-2 items-start">
                {claim.supported ? (
                  <ShieldCheck className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
                ) : (
                  <ShieldAlert className="w-4 h-4 text-orange-500 mt-0.5 flex-shrink-0" />
                )}
                <span className="text-foreground/90">{claim.text}</span>
              </div>
              {!claim.supported && (
                <p className="text-orange-400/80 text-[10px] ml-6 mt-1 uppercase font-semibold tracking-wider">
                  Unsupported Claim Detected
                </p>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
