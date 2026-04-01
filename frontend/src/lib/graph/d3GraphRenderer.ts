import {
  forceCenter,
  forceLink,
  forceManyBody,
  forceSimulation,
  type Simulation,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3";
import type { GraphRelayoutMode } from "./graphRenderer";
import type { GraphScene } from "./graphScene";

export type D3GraphNodeDatum = SimulationNodeDatum & {
  id: string;
  label: string;
  degree: number;
  iconUrl: string | null;
  showLabel: boolean;
  isHeavy: boolean;
  x: number;
  y: number;
  baseX: number;
  baseY: number;
};

export type D3GraphLinkDatum = SimulationLinkDatum<D3GraphNodeDatum> & {
  id: string;
  source: string | D3GraphNodeDatum;
  target: string | D3GraphNodeDatum;
  label: string;
};

export function createD3GraphData(scene: GraphScene) {
  const nodes: D3GraphNodeDatum[] = scene.nodes.map((node) => ({
    id: node.id,
    label: node.label,
    degree: node.degree,
    iconUrl: node.iconUrl,
    showLabel: node.visual.showLabel,
    isHeavy: node.visual.isHeavy,
    x: node.position.x,
    y: node.position.y,
    baseX: node.basePosition.x,
    baseY: node.basePosition.y,
  }));

  const links: D3GraphLinkDatum[] = scene.edges.map((edge) => ({
    id: edge.id,
    source: edge.source,
    target: edge.target,
    label: edge.label,
  }));

  return { nodes, links };
}

export function resetFixedPositions(nodes: D3GraphNodeDatum[], mode: GraphRelayoutMode) {
  if (mode !== "full") {
    return;
  }

  nodes.forEach((node) => {
    node.fx = null;
    node.fy = null;
  });
}

export function createGraphSimulation(
  nodes: D3GraphNodeDatum[],
  links: D3GraphLinkDatum[],
  width: number,
  height: number,
): Simulation<D3GraphNodeDatum, D3GraphLinkDatum> {
  return forceSimulation(nodes)
    .force(
      "link",
      forceLink<D3GraphNodeDatum, D3GraphLinkDatum>(links)
        .id((node) => node.id)
        .distance(90)
        .strength(0.24),
    )
    .force("charge", forceManyBody().strength(-180))
    .force("center", forceCenter(width / 2, height / 2));
}
