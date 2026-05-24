"use client";

import { useTelemetryStore } from "@/stores/telemetryStore";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

export default function RetrievalAnalytics() {
  const { data: telemetryData } = useTelemetryStore();
  
  // Extract retrieval event from trace
  const retrievalEvent = telemetryData?.events?.find((e: any) => e.event_type === "retrieval");
  
  const totalCandidates = (retrievalEvent?.dense_candidates || 0) + (retrievalEvent?.sparse_candidates || 0);
  const compressionRatio = totalCandidates > 0 ? ((retrievalEvent?.final_docs || 0) / totalCandidates) * 100 : 0;

  const retrieval = {
    dense_hits: retrievalEvent?.dense_candidates || 0,
    sparse_hits: retrievalEvent?.sparse_candidates || 0,
    reranker_lift: retrievalEvent ? parseFloat(((retrievalEvent.top_score || 0) - (retrievalEvent.avg_score || 0)).toFixed(2)) : 0,
    compression_ratio: parseFloat(compressionRatio.toFixed(1)),
    top_chunks: retrievalEvent?.final_docs ? Array(Math.min(3, retrievalEvent.final_docs)).fill({ text: "Retrieved Clinical Evidence", score: retrievalEvent.top_score || 0 }) : []
  };

  const data = [
    { name: "Dense", hits: retrieval.dense_hits },
    { name: "Sparse", hits: retrieval.sparse_hits },
  ];

  return (
    <div className="bg-card rounded-lg border border-border p-5 flex flex-col h-full">
      <h3 className="font-semibold text-sm mb-4">Retrieval Analytics</h3>
      
      <div className="grid grid-cols-2 gap-4 mb-6">
        <div className="bg-secondary/50 rounded p-3">
          <p className="text-xs text-muted-foreground mb-1">Reranker Lift</p>
          <p className="text-xl font-bold text-green-500">+{retrieval.reranker_lift}</p>
        </div>
        <div className="bg-secondary/50 rounded p-3">
          <p className="text-xs text-muted-foreground mb-1">Compression Ratio</p>
          <p className="text-xl font-bold">{retrieval.compression_ratio}%</p>
        </div>
      </div>

      <div className="flex-1 min-h-[150px] mb-4">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
            <XAxis type="number" hide />
            <YAxis dataKey="name" type="category" axisLine={false} tickLine={false} style={{ fontSize: '12px', fill: 'hsl(var(--muted-foreground))' }} />
            <Tooltip 
              cursor={{ fill: 'transparent' }}
              contentStyle={{ backgroundColor: 'hsl(var(--card))', borderColor: 'hsl(var(--border))', borderRadius: '6px' }}
            />
            <Bar dataKey="hits" radius={[0, 4, 4, 0]} barSize={20}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={index === 0 ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))"} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div>
        <p className="text-xs font-semibold text-muted-foreground mb-2">Top Retrieved Chunks</p>
        <div className="space-y-2">
          {retrieval.top_chunks.map((chunk, i) => (
            <div key={i} className="text-xs bg-secondary/30 p-2 rounded flex justify-between items-center">
              <span className="truncate max-w-[200px]">{chunk.text}</span>
              <span className="font-mono text-primary bg-primary/10 px-1 rounded">{chunk.score}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
