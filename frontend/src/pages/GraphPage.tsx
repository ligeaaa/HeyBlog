import { useEffect, useMemo, useRef, useState } from "react";
import CytoscapeComponent from "react-cytoscapejs";
import cytoscape from "cytoscape";
import fcose from "cytoscape-fcose";
import { PageHeader } from "../components/PageHeader";
import { Surface } from "../components/Surface";
import { GraphInspector } from "../components/graph/GraphInspector";
import { buildCytoscapeGraph, createFcoseLayout, graphStylesheet } from "../lib/graph/cytoscapeGraph";
import { useGraph } from "../lib/hooks";

cytoscape.use(fcose);

type ViewportSnapshot = {
  zoom: number;
  pan: cytoscape.Position;
  selectedNodeId: string | null;
};

function formatLastUpdated(timestamp: number) {
  if (!timestamp) {
    return null;
  }

  return new Date(timestamp).toLocaleString();
}

export function GraphPage() {
  const graph = useGraph();
  const cyRef = useRef<cytoscape.Core | null>(null);
  const positionsRef = useRef(new Map<string, { x: number; y: number }>());
  const viewportRef = useRef<ViewportSnapshot>({
    zoom: 1,
    pan: { x: 0, y: 0 },
    selectedNodeId: null,
  });
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const graphBundle = useMemo(() => buildCytoscapeGraph(graph.data, positionsRef.current), [graph.data]);
  const selectedDetails = selectedNodeId ? graphBundle.detailsById.get(selectedNodeId) ?? null : null;

  function cacheSceneState(cy: cytoscape.Core) {
    const positionMap = new Map<string, { x: number; y: number }>();
    cy.nodes().forEach((node) => {
      positionMap.set(node.id(), node.position());
    });
    positionsRef.current = positionMap;
    viewportRef.current = {
      zoom: cy.zoom(),
      pan: cy.pan(),
      selectedNodeId,
    };
  }

  function runLayout(animate = true) {
    const cy = cyRef.current;
    if (!cy) {
      return;
    }

    cy.layout({
      ...createFcoseLayout(),
      animate,
    } as unknown as cytoscape.LayoutOptions).run();
  }

  useEffect(() => {
    if (selectedNodeId && !graphBundle.detailsById.has(selectedNodeId)) {
      setSelectedNodeId(null);
    }
  }, [graphBundle.detailsById, selectedNodeId]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!cy) {
      return;
    }

    cy.elements().forEach((element) => {
      if (element.isNode()) {
        const cachedPosition = positionsRef.current.get(element.id());
        if (cachedPosition) {
          element.position(cachedPosition);
        }
      }
    });

    cy.zoom(viewportRef.current.zoom);
    cy.pan(viewportRef.current.pan);

    if (viewportRef.current.selectedNodeId) {
      const selectedElement = cy.$id(viewportRef.current.selectedNodeId);
      if (selectedElement.nonempty()) {
        selectedElement.select();
      }
    }
  }, [graphBundle.signature]);

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="Topology"
        title="Blog 友链图谱"
        description="基于 Cytoscape 的图谱工作台：默认保留视口与选中态，10 分钟自动刷新，并提供手动刷新与重新布局控制。"
      />
      <Surface title="Graph Explorer" note="来自 /api/graph，基于 Cytoscape.js + react-cytoscapejs + fCoSE">
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
                    手动刷新只同步数据，重新布局才会再次触发 fCoSE。这样 10 分钟自动刷新不会把你的视口和当前关注节点打散。
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
                      cyRef.current?.fit(undefined, 60);
                    }}
                  >
                    适配视图
                  </button>
                  <button
                    type="button"
                    className="secondary-button"
                    onClick={() => {
                      cyRef.current?.center();
                      cyRef.current?.zoom(1);
                    }}
                  >
                    回到中心
                  </button>
                </div>
              </div>

              <div className="graph-cyto-shell">
                <CytoscapeComponent
                  elements={graphBundle.elements}
                  stylesheet={graphStylesheet}
                  style={{ width: "100%", height: "100%" }}
                  minZoom={0.35}
                  maxZoom={2.2}
                  layout={{ name: "preset", fit: false, padding: 60 }}
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

                    if (cy.elements().length > 0) {
                      runLayout(false);
                      cy.fit(undefined, 60);
                      cacheSceneState(cy);
                    }
                  }}
                />
              </div>
            </div>

            <GraphInspector
              details={selectedDetails}
              lastUpdatedAt={formatLastUpdated(graph.dataUpdatedAt)}
            />
          </div>
        ) : null}
      </Surface>
    </div>
  );
}
