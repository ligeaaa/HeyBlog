import { useCallback, useEffect, useRef } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { BlogNode, GraphData } from "../types/graph";

interface GraphVisualizationProps {
  data: GraphData;
  onNodeClick?: (node: BlogNode) => void;
  highlightNodeId?: string;
}

/**
 * Render the example force-graph canvas with lightweight custom node drawing.
 *
 * @param data Graph nodes and links to render.
 * @param onNodeClick Optional click handler for selected nodes.
 * @param highlightNodeId Optional highlighted node id.
 * @returns ForceGraph2D visualization container.
 */
export function GraphVisualization({ data, onNodeClick, highlightNodeId }: GraphVisualizationProps) {
  const graphRef = useRef<any>(null);

  useEffect(() => {
    if (highlightNodeId && graphRef.current) {
      const node = data.nodes.find((item) => item.id === highlightNodeId);
      if (node && typeof node.x === "number" && typeof node.y === "number") {
        graphRef.current.centerAt(node.x, node.y, 1000);
        graphRef.current.zoom(3, 1000);
      }
    }
  }, [highlightNodeId, data.nodes]);

  const handleNodeClick = useCallback(
    (node: unknown) => {
      if (onNodeClick) {
        onNodeClick(node as BlogNode);
      }
    },
    [onNodeClick],
  );

  const nodeCanvasObject = useCallback(
    (node: any, context: CanvasRenderingContext2D, globalScale: number) => {
      const label = (node as BlogNode).title || (node as BlogNode).url;
      const fontSize = 12 / globalScale;
      const isHighlighted = node.id === highlightNodeId;

      context.beginPath();
      context.arc(node.x, node.y, isHighlighted ? 8 : 5, 0, 2 * Math.PI);
      context.fillStyle = isHighlighted ? "#3b82f6" : "#60a5fa";
      context.fill();

      if (isHighlighted) {
        context.strokeStyle = "#1d4ed8";
        context.lineWidth = 2 / globalScale;
        context.stroke();
      }

      context.font = `${fontSize}px Sans-Serif`;
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillStyle = isHighlighted ? "#1e293b" : "#475569";
      context.fillText(label.slice(0, 20), node.x, node.y + (isHighlighted ? 12 : 10));
    },
    [highlightNodeId],
  );

  return (
    <div className="h-full w-full bg-gradient-to-br from-blue-50 to-indigo-50">
      <ForceGraph2D
        ref={graphRef}
        graphData={data}
        nodeId="id"
        nodeLabel={(node: any) => {
          const blogNode = node as BlogNode;
          return `
            <div style="background: white; padding: 8px; border-radius: 4px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);">
              <div style="font-weight: bold; margin-bottom: 4px;">${blogNode.title || "Untitled"}</div>
              <div style="font-size: 12px; color: #666;">${blogNode.url}</div>
              ${blogNode.author ? `<div style="font-size: 11px; color: #888; margin-top: 4px;">作者: ${blogNode.author}</div>` : ""}
            </div>
          `;
        }}
        nodeCanvasObject={nodeCanvasObject}
        nodeCanvasObjectMode={() => "replace"}
        onNodeClick={handleNodeClick}
        linkColor={() => "#94a3b8"}
        linkWidth={2}
        linkDirectionalArrowLength={6}
        linkDirectionalArrowRelPos={1}
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleSpeed={0.005}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
        warmupTicks={100}
        cooldownTicks={0}
        enableNodeDrag
        enableZoomInteraction
        enablePanInteraction
      />
    </div>
  );
}
