export type GraphViewportSnapshot = {
  x: number;
  y: number;
  k: number;
};

export type GraphRelayoutMode = "soft" | "full";

export type GraphRendererHandle = {
  captureViewport: () => GraphViewportSnapshot;
  restoreViewport: (snapshot: GraphViewportSnapshot) => void;
  fitView: () => void;
  requestRelayout: (mode: GraphRelayoutMode) => void;
  clearSelection: () => void;
};

export const DEFAULT_GRAPH_VIEWPORT: GraphViewportSnapshot = {
  x: 0,
  y: 0,
  k: 1,
};
