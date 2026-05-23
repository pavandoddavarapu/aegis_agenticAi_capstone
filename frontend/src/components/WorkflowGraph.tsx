"use client";

import { useEffect, useState } from "react";
import { ReactFlow, Background, Controls, Node, Edge } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useTelemetryStore } from "@/stores/telemetryStore";

const initialNodes: Node[] = [
  { id: "decide", position: { x: 250, y: 0 }, data: { label: "Decision Engine" }, type: "default" },
  { id: "query_understand", position: { x: 250, y: 100 }, data: { label: "Query Understand" } },
  { id: "retrieve", position: { x: 250, y: 200 }, data: { label: "Retrieve" } },
  { id: "reason", position: { x: 250, y: 300 }, data: { label: "Reason" } },
  { id: "validate", position: { x: 250, y: 400 }, data: { label: "Validate" } },
  { id: "reflect", position: { x: 450, y: 300 }, data: { label: "Reflect" } },
  { id: "finalize", position: { x: 250, y: 500 }, data: { label: "Finalize" } },
];

const initialEdges: Edge[] = [
  { id: "e-d-q", source: "decide", target: "query_understand", animated: true },
  { id: "e-q-r", source: "query_understand", target: "retrieve", animated: true },
  { id: "e-r-re", source: "retrieve", target: "reason", animated: true },
  { id: "e-re-v", source: "reason", target: "validate", animated: true },
  { id: "e-v-f", source: "validate", target: "finalize", animated: true, label: "Pass" },
  { id: "e-v-rf", source: "validate", target: "reflect", animated: true, label: "Fail", style: { stroke: "#ef4444" } },
  { id: "e-rf-r", source: "reflect", target: "retrieve", animated: true, style: { stroke: "#eab308" } },
];

export default function WorkflowGraph() {
  const [nodes, setNodes] = useState<Node[]>(initialNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);

  const { timeline } = useTelemetryStore();
  const timelineSteps = timeline?.timeline || [];

  // Apply some styling to nodes based on timeline success
  useEffect(() => {
    const updatedNodes = nodes.map((node) => {
      const step = timelineSteps.find((t: any) => t.node === node.id);
      if (step) {
        return {
          ...node,
          style: {
            background: step.success ? "hsl(var(--card))" : "hsl(var(--destructive)/0.2)",
            color: "hsl(var(--foreground))",
            border: `1px solid ${step.success ? "hsl(var(--border))" : "hsl(var(--destructive))"}`,
            borderRadius: "8px",
            padding: "10px",
            fontSize: "12px",
            width: 140,
            textAlign: "center" as const,
          }
        };
      }
      return {
          ...node,
          style: {
            background: "hsl(var(--card))",
            color: "hsl(var(--foreground))",
            border: "1px solid hsl(var(--border))",
            borderRadius: "8px",
            padding: "10px",
            fontSize: "12px",
            width: 140,
            textAlign: "center" as const,
          }
      };
    });
    setNodes(updatedNodes);
  }, [timeline]);

  return (
    <div className="h-full w-full bg-secondary/20 rounded-lg border border-border">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        fitView
        attributionPosition="bottom-right"
      >
        <Background color="#333" gap={16} />
        <Controls />
      </ReactFlow>
    </div>
  );
}
