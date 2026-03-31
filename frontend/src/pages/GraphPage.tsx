import { useEffect, useMemo, useRef, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { GraphInspector } from "../components/graph/GraphInspector";
import { api, type GraphViewPayload } from "../lib/api";
import {
  buildCytoscapeGraph,
  createFcoseLayout,
  graphStylesheet,
  mergeGraphViewPayload,
} from "../lib/graph/cytoscapeGraph";
import { useGraphView } from "../lib/hooks";

cytoscape.use(fcose);

type ViewportSnapshot = {
  zoom: number;
  pan: cytoscape.Position;
  selectedNodeId: string | null;
};

type SamplingMode = "off" | "count" | "percent";

type ViewOptions = {
  strategy: "degree" | "seed";
  limit: number;
  sampleMode: SamplingMode;
  sampleValue: number | null;
  sampleSeed: number;
};

const DEFAULT_VIEW_OPTIONS: ViewOptions = {
  strategy: "degree",
  limit: 180,
  sampleMode: "off",
  sampleValue: null,
  sampleSeed: 7,
};

function formatLastUpdated(timestamp: number) {
  if (!timestamp) {
    return null;
  }
  return new Date(timestamp).toLocaleString();
}

function parseNumericInput(value: string, fallback: number) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function GraphPage() {
  const [viewOptions, setViewOptions] = useState<ViewOptions>(DEFAULT_VIEW_OPTIONS);
  const graph = useGraphView(viewOptions);
  const [graphPayload, setGraphPayload] = useState<GraphViewPayload | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [isExpanding, setIsExpanding] = useState(false);
  const cyRef = useRef<cytoscape.Core | null>(null);
  const positionsRef = useRef(new Map<string, { x: number; y: number }>());
  const hasInitializedViewportRef = useRef(false);
  const viewportRef = useRef<ViewportSnapshot>({
    zoom: 1,
    pan: { x: 0, y: 0 },
    selectedNodeId: null,
  });

  useEffect(() => {
    if (graph.data) {
      setGraphPayload(graph.data);
    }
  }, [graph.data]);

  useEffect(() => {
    hasInitializedViewportRef.current = false;
    positionsRef.current = new Map();
    viewportRef.current = {
      zoom: 1,
      pan: { x: 0, y: 0 },
      selectedNodeId: null,
    };
    setSelectedNodeId(null);
  }, [
    viewOptions.strategy,
    viewOptions.limit,
    viewOptions.sampleMode,
    viewOptions.sampleValue,
    viewOptions.sampleSeed,
  ]);

  const graphBundle = useMemo(
    () => buildCytoscapeGraph(graphPayload, positionsRef.current),
    [graphPayload],
  );
  const selectedDetails = selectedNodeId ? graphBundle.detailsById.get(selectedNodeId) ?? null : null;

  function cacheSceneState(cy: cytoscape.Core) {
    const positionMap = new Map<string, { x: number; y: number }>();
    cy.nodes().forEach((node) => {
      positionMap.set(node.id(), node.position());
    });
    const selectedElement = cy.$("node:selected").first();
    positionsRef.current = positionMap;
    viewportRef.current = {
      zoom: cy.zoom(),
      pan: cy.pan(),
      selectedNodeId: selectedElement.nonempty() ? selectedElement.id() : null,
    };
  }

  function runLayout(animate = false) {
    const cy = cyRef.current;
    if (!cy) {
      return;
    }
    cy.layout(createFcoseLayout({ animate })).run();
  }

  async function expandSelectedNode(hops: 1 | 2) {
    if (!selectedNodeId) {
      return;
    }
    setIsExpanding(true);
    try {
      const payload = await api.graphNeighbors(selectedNodeId, {
        hops,
        limit: Math.max(80, Math.min(viewOptions.limit, 240)),
      });
      setGraphPayload((current) => mergeGraphViewPayload(current, payload));
    } finally {
      setIsExpanding(false);
    }
  }

  useEffect(() => {
    if (selectedNodeId && !graphBundle.detailsById.has(selectedNodeId)) {
      setSelectedNodeId(null);
    }
  }, [graphBundle.detailsById, selectedNodeId]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || graphBundle.elements.length === 0) {
      return;
    }

    if (!graphBundle.hasStablePositions) {
      cy.elements().forEach((element) => {
        if (!element.isNode()) {
          return;
        }
        const cachedPosition = positionsRef.current.get(element.id());
        if (cachedPosition) {
          element.position(cachedPosition);
        }
      });
    }

    if (!hasInitializedViewportRef.current) {
      if (graphBundle.shouldRunLayout) {
        runLayout(false);
      }
      cy.fit(undefined, 60);
      cacheSceneState(cy);
      hasInitializedViewportRef.current = true;
    } else {
      cy.zoom(viewportRef.current.zoom);
      cy.pan(viewportRef.current.pan);
      if (graphBundle.shouldRunLayout) {
        runLayout(false);
      } else {
        cacheSceneState(cy);
      }
    }

    if (viewportRef.current.selectedNodeId) {
      const selectedElement = cy.$id(viewportRef.current.selectedNodeId);
      if (selectedElement.nonempty()) {
        selectedElement.select();
      }
    }
  }, [graphBundle.signature, graphBundle.shouldRunLayout, graphBundle.hasStablePositions, graphBundle.elements.length]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Topology"
        title="Blog 友链图谱"
        description="默认进入结构化子图，支持邻域展开、离线 snapshot 坐标和可选随机采样开关；手动刷新与重新布局保持分离。"
      />
      <Surface title="Graph Explorer" note="默认来自 /api/graph/views/core；若 snapshot 可用则优先复用稳定坐标。">
        {graph.isLoading ? <p>正在加载图谱…</p> : null}
        {graph.error ? <p className="error-copy">图谱加载失败：{graph.error.message}</p> : null}
        {!graph.isLoading && !graph.error && graphBundle.elements.length === 0 ? <p>暂无图谱数据。</p> : null}

        {graphBundle.elements.length > 0 ? (
          <div className="graph-layout graph-layout-cyto">
            <div className="graph-workbench">
              <div className="graph-toolbar">
                <div>
                  <p className="eyebrow">Graph Stage</p>
                  <p className="graph-toolbar-copy">
                    当前默认视图 {graphPayload?.meta.selected_nodes ?? 0} nodes / {graphPayload?.meta.selected_edges ?? 0} edges，
                    总可用 {graphPayload?.meta.available_nodes ?? 0} / {graphPayload?.meta.available_edges ?? 0}。
                  </p>
                </div>
                <div className="graph-toolbar-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={graph.isFetching}
                    onClick={async () => {
                      if (cyRef.current) {
                        cacheSceneState(cyRef.current);
                      }
                      await graph.refetch();
                    }}
                  >
                    {graph.isFetching ? "刷新中…" : "手动刷新"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!graph.data}
                    onClick={() => {
                      setGraphPayload(graph.data ?? null);
                      positionsRef.current = new Map();
                      viewportRef.current = {
                        zoom: 1,
                        pan: { x: 0, y: 0 },
                        selectedNodeId: null,
                      };
                      setSelectedNodeId(null);
                      hasInitializedViewportRef.current = false;
                    }}
                  >
                    重置为核心视图
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => {
                      runLayout(true);
                    }}
                  >
                    重新布局
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => {
                      const cy = cyRef.current;
                      if (!cy) {
                        return;
                      }
                      cy.fit(undefined, 60);
                      cacheSceneState(cy);
                    }}
                  >
                    适配视图
                  </button>
                </div>
              </div>

              <div className="graph-control-grid">
                <label className="graph-control">
                  <span>初始策略</span>
                  <select
                    value={viewOptions.strategy}
                    onChange={(event) => {
                      setViewOptions((current) => ({
                        ...current,
                        strategy: event.target.value === "seed" ? "seed" : "degree",
                      }));
                    }}
                  >
                    <option value="degree">核心节点</option>
                    <option value="seed">Seed 节点</option>
                  </select>
                </label>

                <label className="graph-control">
                  <span>视图规模</span>
                  <input
                    type="number"
                    min={24}
                    max={1000}
                    value={viewOptions.limit}
                    onChange={(event) => {
                      setViewOptions((current) => ({
                        ...current,
                        limit: parseNumericInput(event.target.value, current.limit),
                      }));
                    }}
                  />
                </label>

                <label className="graph-control">
                  <span>采样模式</span>
                  <select
                    value={viewOptions.sampleMode}
                    onChange={(event) => {
                      const sampleMode = event.target.value as SamplingMode;
                      setViewOptions((current) => ({
                        ...current,
                        sampleMode,
                        sampleValue:
                          sampleMode === "count"
                            ? current.sampleValue ?? 120
                            : sampleMode === "percent"
                              ? current.sampleValue ?? 20
                              : null,
                      }));
                    }}
                  >
                    <option value="off">关闭</option>
                    <option value="count">随机 N</option>
                    <option value="percent">随机 N%</option>
                  </select>
                </label>

                {viewOptions.sampleMode !== "off" ? (
                  <>
                    <label className="graph-control">
                      <span>{viewOptions.sampleMode === "count" ? "采样数量" : "采样比例 (%)"}</span>
                      <input
                        type="number"
                        min={viewOptions.sampleMode === "count" ? 1 : 1}
                        max={viewOptions.sampleMode === "count" ? 1000 : 100}
                        value={viewOptions.sampleValue ?? ""}
                        onChange={(event) => {
                          setViewOptions((current) => ({
                            ...current,
                            sampleValue: parseNumericInput(
                              event.target.value,
                              current.sampleValue ?? (current.sampleMode === "count" ? 120 : 20),
                            ),
                          }));
                        }}
                      />
                    </label>

                    <label className="graph-control">
                      <span>固定 Seed</span>
                      <input
                        type="number"
                        min={1}
                        max={999999}
                        value={viewOptions.sampleSeed}
                        onChange={(event) => {
                          setViewOptions((current) => ({
                            ...current,
                            sampleSeed: parseNumericInput(event.target.value, current.sampleSeed),
                          }));
                        }}
                      />
                    </label>
                  </>
                ) : null}
              </div>

              <div className="graph-toolbar graph-toolbar-secondary">
                <div>
                  <p className="eyebrow">Expansion</p>
                  <p className="graph-toolbar-copy">
                    选中节点后可按 1 跳或 2 跳展开；若当前使用 snapshot 坐标，则新增节点会保持稳定落位。
                  </p>
                </div>
                <div className="graph-toolbar-actions">
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!selectedNodeId || isExpanding}
                    onClick={() => {
                      void expandSelectedNode(1);
                    }}
                  >
                    {isExpanding ? "展开中…" : "展开 1 跳"}
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={!selectedNodeId || isExpanding}
                    onClick={() => {
                      void expandSelectedNode(2);
                    }}
                  >
                    展开 2 跳
                  </button>
                </div>
              </div>

              <div className="graph-cyto-shell">
                <CytoscapeComponent
                  elements={graphBundle.elements}
                  stylesheet={graphStylesheet}
                  style={{ width: "100%", height: "100%" }}
                  minZoom={0.25}
                  maxZoom={2.5}
                  layout={{ name: "preset", fit: false, padding: 60 }}
                  pixelRatio={1}
                  hideEdgesOnViewport={graphBundle.elements.length > 800}
                  textureOnViewport={graphBundle.elements.length > 1200}
                  cy={(cy: cytoscape.Core) => {
                    cyRef.current = cy;

                    if (cy.scratch("heyblog-events-bound")) {
                      return;
                    }

                    cy.scratch("heyblog-events-bound", true);
                    cy.on("select", "node", (event: cytoscape.EventObject) => {
                      setSelectedNodeId(event.target.id());
                    });
                    cy.on("unselect", "node", () => {
                      const nextSelected = cy.$("node:selected").first();
                      setSelectedNodeId(nextSelected.nonempty() ? nextSelected.id() : null);
                    });
                    cy.on("tap", (event: cytoscape.EventObject) => {
                      if (event.target === cy) {
                        cy.elements().unselect();
                        setSelectedNodeId(null);
                      }
                    });
                    cy.on("zoom pan dragfree layoutstop", () => {
                      cacheSceneState(cy);
                    });
                  }}
                />
              </div>
            </div>

            <GraphInspector
              details={selectedDetails}
              lastUpdatedAt={formatLastUpdated(graph.dataUpdatedAt)}
              viewMeta={graphPayload?.meta ?? null}
            />
          </div>
        ) : null}
      </Surface>
    </div>
  );
}
