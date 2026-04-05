import {
  drag,
  select,
  zoom,
  zoomIdentity,
  type D3DragEvent,
  type ZoomBehavior,
  type ZoomTransform,
} from "d3";
import { forwardRef, useEffect, useId, useImperativeHandle, useRef, type MutableRefObject } from "react";
import {
  createD3GraphData,
  createGraphSimulation,
  resetFixedPositions,
  type D3GraphLinkDatum,
  type D3GraphNodeDatum,
} from "../../lib/graph/d3GraphRenderer";
import {
  DEFAULT_GRAPH_VIEWPORT,
  type GraphRendererHandle,
  type GraphViewportSnapshot,
} from "../../lib/graph/graphRenderer";
import type { GraphPoint, GraphPositionOverlay, GraphScene } from "../../lib/graph/graphScene";

const VIEWPORT_WIDTH = 960;
const VIEWPORT_HEIGHT = 620;
const VIEWPORT_PADDING = 80;
const LINK_ARROW_SIZE = 7;
const LINK_TARGET_GAP = 3;

function nodeRadius(datum: D3GraphNodeDatum) {
  return 10 + Math.min(datum.degree, 18) * 1.1;
}

function resolveNodeRef(nodes: D3GraphNodeDatum[], value: string | D3GraphNodeDatum) {
  if (typeof value !== "string") {
    return value;
  }
  return nodes.find((node) => node.id === value) ?? null;
}

function resolveLinkPoints(nodes: D3GraphNodeDatum[], datum: D3GraphLinkDatum) {
  const source = resolveNodeRef(nodes, datum.source);
  const target = resolveNodeRef(nodes, datum.target);
  if (!source || !target) {
    return {
      x1: 0,
      y1: 0,
      x2: 0,
      y2: 0,
    };
  }

  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const distance = Math.hypot(dx, dy);
  if (distance === 0) {
    return {
      x1: source.x,
      y1: source.y,
      x2: target.x,
      y2: target.y,
    };
  }

  const unitX = dx / distance;
  const unitY = dy / distance;
  const sourceOffset = nodeRadius(source) * 0.92;
  const targetOffset = nodeRadius(target) * 0.92 + LINK_ARROW_SIZE + LINK_TARGET_GAP;

  return {
    x1: source.x + unitX * sourceOffset,
    y1: source.y + unitY * sourceOffset,
    x2: target.x - unitX * targetOffset,
    y2: target.y - unitY * targetOffset,
  };
}

type Props = {
  scene: GraphScene;
  selectedNodeId: string | null;
  onSelect: (nodeId: string | null) => void;
  onViewportChange: (snapshot: GraphViewportSnapshot) => void;
  onOverlayChange: (overlay: GraphPositionOverlay) => void;
};

function toSnapshot(transform: ZoomTransform): GraphViewportSnapshot {
  return {
    x: transform.x,
    y: transform.y,
    k: transform.k,
  };
}

function toTransform(snapshot: GraphViewportSnapshot) {
  return zoomIdentity.translate(snapshot.x, snapshot.y).scale(snapshot.k);
}

function emitOverlay(
  nodesRef: MutableRefObject<D3GraphNodeDatum[]>,
  graphFingerprint: string | null,
  onOverlayChange: (overlay: GraphPositionOverlay) => void,
) {
  const positions = new Map<string, GraphPoint>();
  nodesRef.current.forEach((node) => {
    positions.set(node.id, {
      x: node.x,
      y: node.y,
    });
  });

  onOverlayChange({
    graphFingerprint,
    positions,
  });
}

export const D3GraphCanvas = forwardRef<GraphRendererHandle, Props>(function D3GraphCanvas(
  { scene, selectedNodeId, onSelect, onViewportChange, onOverlayChange },
  ref,
) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const zoomRef = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const simulationRef = useRef<ReturnType<typeof createGraphSimulation> | null>(null);
  const nodesRef = useRef<D3GraphNodeDatum[]>([]);
  const linksRef = useRef<D3GraphLinkDatum[]>([]);
  const viewportRef = useRef(DEFAULT_GRAPH_VIEWPORT);
  const onSelectRef = useRef(onSelect);
  const onViewportChangeRef = useRef(onViewportChange);
  const onOverlayChangeRef = useRef(onOverlayChange);
  const graphFingerprintRef = useRef(scene.graphFingerprint);
  const clipIdPrefix = useId().replace(/[:]/g, "");

  useEffect(() => {
    onSelectRef.current = onSelect;
  }, [onSelect]);

  useEffect(() => {
    onViewportChangeRef.current = onViewportChange;
  }, [onViewportChange]);

  useEffect(() => {
    onOverlayChangeRef.current = onOverlayChange;
  }, [onOverlayChange]);

  useEffect(() => {
    graphFingerprintRef.current = scene.graphFingerprint;
  }, [scene.graphFingerprint]);

  function clipIdFor(nodeId: string) {
    return `graph-node-icon-${clipIdPrefix}-${nodeId}`;
  }

  function linkArrowId() {
    return `graph-link-arrow-${clipIdPrefix}`;
  }

  function renderSelectionState(nextSelectedNodeId: string | null, nextScene: GraphScene) {
    const svg = svgRef.current;
    if (!svg) {
      return;
    }

    const root = select(svg);
    const zoomLayer = root.select<SVGGElement>("g.graph-zoom-layer");
    const nodeSelection = zoomLayer.select<SVGGElement>("g.graph-nodes").selectAll<SVGGElement, D3GraphNodeDatum>("g.graph-node");

    nodeSelection
      .classed("is-selected", (datum) => datum.id === nextSelectedNodeId)
      .select<SVGCircleElement>("circle.graph-node-circle")
      .attr("fill", (datum) => {
        if (datum.id === nextSelectedNodeId) {
          return "#ffe49b";
        }
        return datum.isHeavy ? "#78e6c7" : "#6aa4ff";
      });

    const visibleLabelNodes = nodesRef.current.filter(
      (node) =>
        nextSelectedNodeId === node.id ||
        (!nextScene.performanceMode.reduceLabels && node.showLabel) ||
        node.degree >= nextScene.performanceMode.labelDegreeThreshold,
    );

    zoomLayer
      .select<SVGGElement>("g.graph-labels")
      .selectAll<SVGTextElement, D3GraphNodeDatum>("text")
      .data(visibleLabelNodes, (datum) => datum.id)
      .join((enter) => enter.append("text").attr("class", "graph-label").attr("text-anchor", "middle"))
      .text((datum) => datum.label)
      .classed("is-selected", (datum) => datum.id === nextSelectedNodeId);

    renderPositions();
  }

  function renderPositions() {
    const svg = svgRef.current;
    if (!svg) {
      return;
    }

    const root = select(svg);
    const zoomLayer = root.select<SVGGElement>("g.graph-zoom-layer");
    const linkSelection = zoomLayer.select<SVGGElement>("g.graph-links").selectAll<SVGLineElement, D3GraphLinkDatum>("line");
    const nodeSelection = zoomLayer.select<SVGGElement>("g.graph-nodes").selectAll<SVGGElement, D3GraphNodeDatum>("g.graph-node");
    const labelSelection = zoomLayer.select<SVGGElement>("g.graph-labels").selectAll<SVGTextElement, D3GraphNodeDatum>("text");

    linkSelection
      .attr("x1", (datum) => resolveLinkPoints(nodesRef.current, datum).x1)
      .attr("y1", (datum) => resolveLinkPoints(nodesRef.current, datum).y1)
      .attr("x2", (datum) => resolveLinkPoints(nodesRef.current, datum).x2)
      .attr("y2", (datum) => resolveLinkPoints(nodesRef.current, datum).y2);

    nodeSelection.attr("transform", (datum) => `translate(${datum.x}, ${datum.y})`);
    nodeSelection
      .select<SVGImageElement>("image.graph-node-icon")
      .attr("x", (datum) => -nodeRadius(datum) * 0.7)
      .attr("y", (datum) => -nodeRadius(datum) * 0.7)
      .attr("width", (datum) => nodeRadius(datum) * 1.4)
      .attr("height", (datum) => nodeRadius(datum) * 1.4);
    labelSelection
      .attr("x", (datum) => datum.x)
      .attr("y", (datum) => datum.y + 28);
  }

  function applyViewport(snapshot: GraphViewportSnapshot) {
    const svg = svgRef.current;
    if (!svg) {
      return;
    }

    viewportRef.current = snapshot;
    const root = select(svg);
    const nextTransform = toTransform(snapshot);
    if (zoomRef.current) {
      root.call(zoomRef.current.transform, nextTransform);
      return;
    }
    root.select<SVGGElement>("g.graph-zoom-layer").attr("transform", nextTransform.toString());
    onViewportChangeRef.current(snapshot);
  }

  function fitToNodes() {
    if (nodesRef.current.length === 0) {
      applyViewport(DEFAULT_GRAPH_VIEWPORT);
      return;
    }

    const xs = nodesRef.current.map((node) => node.x);
    const ys = nodesRef.current.map((node) => node.y);
    const minX = Math.min(...xs);
    const maxX = Math.max(...xs);
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    const width = Math.max(maxX - minX, 1);
    const height = Math.max(maxY - minY, 1);
    const scale = Math.min(
      2.5,
      Math.max(
        0.25,
        Math.min(
          (VIEWPORT_WIDTH - VIEWPORT_PADDING * 2) / width,
          (VIEWPORT_HEIGHT - VIEWPORT_PADDING * 2) / height,
        ),
      ),
    );
    const x = VIEWPORT_WIDTH / 2 - ((minX + maxX) / 2) * scale;
    const y = VIEWPORT_HEIGHT / 2 - ((minY + maxY) / 2) * scale;

    applyViewport({ x, y, k: scale });
  }

  function startRelayout(mode: "soft" | "full") {
    simulationRef.current?.stop();
    resetFixedPositions(nodesRef.current, mode);
    simulationRef.current = createGraphSimulation(nodesRef.current, linksRef.current, VIEWPORT_WIDTH, VIEWPORT_HEIGHT);
    simulationRef.current.on("tick", () => {
      renderPositions();
    });
    simulationRef.current.on("end", () => {
      renderPositions();
      emitOverlay(nodesRef, graphFingerprintRef.current, onOverlayChangeRef.current);
    });
    simulationRef.current.alpha(mode === "full" ? 1 : 0.6).restart();
  }

  useImperativeHandle(
    ref,
    () => ({
      captureViewport: () => viewportRef.current,
      restoreViewport: (snapshot) => {
        applyViewport(snapshot);
      },
      fitView: () => {
        fitToNodes();
      },
      requestRelayout: (mode) => {
        startRelayout(mode);
      },
      clearSelection: () => {
        onSelectRef.current(null);
      },
    }),
    [],
  );

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) {
      return;
    }

    const { nodes, links } = createD3GraphData(scene);
    nodesRef.current = nodes;
    linksRef.current = links;

    const root = select(svg);
    let zoomLayer = root.select<SVGGElement>("g.graph-zoom-layer");
    if (zoomLayer.empty()) {
      zoomLayer = root.append("g").attr("class", "graph-zoom-layer");
      zoomLayer.append("g").attr("class", "graph-links");
      zoomLayer.append("g").attr("class", "graph-nodes");
      zoomLayer.append("g").attr("class", "graph-labels");
    }

    if (!zoomRef.current) {
      zoomRef.current = zoom<SVGSVGElement, unknown>()
        .scaleExtent([0.25, 2.5])
        .on("zoom", (event) => {
          zoomLayer.attr("transform", event.transform.toString());
          viewportRef.current = toSnapshot(event.transform);
          onViewportChangeRef.current(viewportRef.current);
        });
      root.call(zoomRef.current);
      root.on("dblclick.zoom", null);
    }

    let defs = root.select<SVGDefsElement>("defs.graph-node-defs");
    if (defs.empty()) {
      defs = root.insert("defs", ":first-child").attr("class", "graph-node-defs");
    }

    defs
      .selectAll<SVGClipPathElement, D3GraphNodeDatum>("clipPath.graph-node-clip")
      .data(nodes.filter((node) => Boolean(node.iconUrl)), (datum) => datum.id)
      .join(
        (enter) => {
          const clipPath = enter.append("clipPath").attr("class", "graph-node-clip");
          clipPath.append("circle");
          return clipPath;
        },
        (update) => update,
        (exit) => exit.remove(),
      )
      .attr("id", (datum) => clipIdFor(datum.id))
      .select("circle")
      .attr("r", (datum) => nodeRadius(datum) * 0.72);

    const markerSelection = defs
      .selectAll<SVGMarkerElement, null>("marker.graph-link-arrow")
      .data([null])
      .join((enter) => {
        const marker = enter
          .append("marker")
          .attr("class", "graph-link-arrow")
          .attr("orient", "auto")
          .attr("markerUnits", "userSpaceOnUse");
        marker.append("path").attr("class", "graph-link-arrow-shape");
        return marker;
      })
      .attr("id", linkArrowId())
      .attr("viewBox", `0 0 ${LINK_ARROW_SIZE} ${LINK_ARROW_SIZE}`)
      .attr("refX", LINK_ARROW_SIZE)
      .attr("refY", LINK_ARROW_SIZE / 2)
      .attr("markerWidth", LINK_ARROW_SIZE)
      .attr("markerHeight", LINK_ARROW_SIZE);

    markerSelection
      .select("path")
      .attr("d", `M0,0 L${LINK_ARROW_SIZE},${LINK_ARROW_SIZE / 2} L0,${LINK_ARROW_SIZE} z`);

    const linkLayer = zoomLayer.select<SVGGElement>("g.graph-links");
    linkLayer
      .selectAll<SVGLineElement, D3GraphLinkDatum>("line")
      .data(links, (datum) => datum.id)
      .join((enter) => enter.append("line").attr("class", "graph-link"))
      .attr("marker-end", `url(#${linkArrowId()})`)
      .classed("is-deemphasized", scene.performanceMode.reduceEdgeDetail);

    const nodeLayer = zoomLayer.select<SVGGElement>("g.graph-nodes");
    const nodeSelection = nodeLayer
      .selectAll<SVGGElement, D3GraphNodeDatum>("g.graph-node")
      .data(nodes, (datum) => datum.id)
      .join((enter) => {
        const group = enter
          .append("g")
          .attr("class", "graph-node")
          .attr("role", "button")
          .attr("tabindex", 0);
        group.append("circle").attr("class", "graph-node-circle");
        group.append("image").attr("class", "graph-node-icon").attr("preserveAspectRatio", "xMidYMid slice");
        return group;
      });

    nodeSelection
      .attr("aria-label", (datum) => datum.label)
      .on("keydown", (event, datum) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelectRef.current(datum.id);
        }
      })
      .on("click", (_, datum) => {
        onSelectRef.current(datum.id);
      });

    nodeSelection
      .select<SVGCircleElement>("circle")
      .attr("r", (datum) => nodeRadius(datum));

    nodeSelection
      .select<SVGImageElement>("image.graph-node-icon")
      .attr("href", (datum) => datum.iconUrl ?? "")
      .attr("clip-path", (datum) => (datum.iconUrl ? `url(#${clipIdFor(datum.id)})` : null))
      .attr("display", (datum) => (datum.iconUrl ? null : "none"))
      .attr("pointer-events", "none");

    nodeSelection.call(
      drag<SVGGElement, D3GraphNodeDatum>()
        .on("start", (event: D3DragEvent<SVGGElement, D3GraphNodeDatum, D3GraphNodeDatum>, datum) => {
          if (!event.active) {
            simulationRef.current?.alphaTarget(0.15).restart();
          }
          datum.fx = datum.x;
          datum.fy = datum.y;
        })
        .on("drag", (event: D3DragEvent<SVGGElement, D3GraphNodeDatum, D3GraphNodeDatum>, datum) => {
          datum.fx = event.x;
          datum.fy = event.y;
          datum.x = event.x;
          datum.y = event.y;
          renderPositions();
        })
        .on("end", (event: D3DragEvent<SVGGElement, D3GraphNodeDatum, D3GraphNodeDatum>, datum) => {
          if (!event.active) {
            simulationRef.current?.alphaTarget(0);
          }
          datum.fx = null;
          datum.fy = null;
          emitOverlay(nodesRef, scene.graphFingerprint, onOverlayChangeRef.current);
        }),
    );

    renderPositions();
    renderSelectionState(selectedNodeId, scene);
    emitOverlay(nodesRef, scene.graphFingerprint, onOverlayChangeRef.current);

    return () => {
      simulationRef.current?.stop();
    };
  }, [scene]);

  useEffect(() => {
    renderSelectionState(selectedNodeId, scene);
  }, [scene, selectedNodeId]);

  return (
    <div className="graph-canvas-shell">
      <svg
        ref={svgRef}
        data-testid="graph-canvas"
        className="graph-canvas"
        viewBox={`0 0 ${VIEWPORT_WIDTH} ${VIEWPORT_HEIGHT}`}
        width="100%"
        height="100%"
        onClick={(event) => {
          if (event.target === event.currentTarget) {
            onSelectRef.current(null);
          }
        }}
      />
    </div>
  );
});
