/**
 * Simplified graph types used by the example-aligned single-page frontend.
 */
export interface BlogNode {
  id: string;
  url: string;
  title?: string;
  description?: string;
  author?: string;
  tags?: string[];
  x?: number;
  y?: number;
}

export interface BlogLink {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: BlogNode[];
  links: BlogLink[];
}

export interface BlogDetail extends BlogNode {
  incomingLinks: number;
  outgoingLinks: number;
  relatedNodes: BlogNode[];
}

export interface StatsData {
  totalNodes: number;
  totalEdges: number;
}
