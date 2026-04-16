import type { BlogDetail, BlogNode, GraphData, StatsData } from "../types/graph";

const fakeNodes: BlogNode[] = [
  {
    id: "1",
    url: "https://blog.alice.dev",
    title: "Alice 的深度学习手记",
    author: "Alice",
    tags: ["AI", "ML"],
    description: "记录神经网络、实验复盘和个人研究笔记。",
    x: 180,
    y: 220,
  },
  {
    id: "2",
    url: "https://frontend.bob.dev",
    title: "Bob 的前端观察",
    author: "Bob",
    tags: ["React", "Frontend"],
    description: "关注 React、TypeScript 和现代 Web 体验。",
    x: 420,
    y: 140,
  },
  {
    id: "3",
    url: "https://charlie-data.dev",
    title: "Charlie 数据日志",
    author: "Charlie",
    tags: ["Python", "Data"],
    description: "数据分析、爬虫与建模的实践记录。",
    x: 540,
    y: 330,
  },
  {
    id: "4",
    url: "https://diana-notes.dev",
    title: "Diana 编程随记",
    author: "Diana",
    tags: ["TypeScript", "JavaScript"],
    description: "偏工程化的前端与工具链笔记。",
    x: 760,
    y: 220,
  },
  {
    id: "5",
    url: "https://eve-css.dev",
    title: "Eve 的样式实验室",
    author: "Eve",
    tags: ["CSS", "Design"],
    description: "CSS 布局、动效和视觉系统尝试。",
    x: 930,
    y: 380,
  },
  {
    id: "6",
    url: "https://frank-backend.dev",
    title: "Frank 后端周报",
    author: "Frank",
    tags: ["Backend", "Node.js"],
    description: "记录服务设计、接口治理和线上问题复盘。",
    x: 1010,
    y: 140,
  },
];

const fakeLinks = [
  { source: "1", target: "3" },
  { source: "1", target: "2" },
  { source: "2", target: "4" },
  { source: "2", target: "5" },
  { source: "3", target: "1" },
  { source: "3", target: "6" },
  { source: "4", target: "2" },
  { source: "5", target: "2" },
  { source: "6", target: "3" },
  { source: "6", target: "4" },
];

const fakeGraph: GraphData = {
  nodes: fakeNodes,
  links: fakeLinks,
};

/**
 * Return the full fake graph used during the current UI-alignment phase.
 *
 * @returns Deterministic graph dataset mirroring the example interaction flow.
 */
export async function fetchGraphData(): Promise<GraphData> {
  return fakeGraph;
}

/**
 * Look up a fake blog by URL and return derived relationship details.
 *
 * @param url Blog URL provided by the user.
 * @returns Matching fake blog detail when found, otherwise `null`.
 */
export async function searchUrl(url: string): Promise<BlogDetail | null> {
  const normalized = url.trim().toLowerCase();
  const node = fakeNodes.find((item) => item.url.toLowerCase() === normalized);
  if (!node) {
    return null;
  }

  const incomingLinks = fakeLinks.filter((link) => link.target === node.id).length;
  const outgoingLinks = fakeLinks.filter((link) => link.source === node.id).length;
  const relatedNodeIds = [
    ...fakeLinks.filter((link) => link.source === node.id).map((link) => link.target),
    ...fakeLinks.filter((link) => link.target === node.id).map((link) => link.source),
  ];
  const relatedNodes = fakeNodes.filter((item) => relatedNodeIds.includes(item.id));

  return {
    ...node,
    incomingLinks,
    outgoingLinks,
    relatedNodes,
  };
}

/**
 * Return a one-hop subgraph centered on the provided URL.
 *
 * @param url Selected blog URL.
 * @returns Subgraph with the center node plus immediate neighbors.
 */
export async function fetchSubgraph(url: string): Promise<GraphData> {
  const node = fakeNodes.find((item) => item.url === url);
  if (!node) {
    return { nodes: [], links: [] };
  }

  const relatedNodeIds = new Set([node.id]);
  fakeLinks.forEach((link) => {
    if (link.source === node.id) {
      relatedNodeIds.add(link.target);
    }
    if (link.target === node.id) {
      relatedNodeIds.add(link.source);
    }
  });

  return {
    nodes: fakeNodes.filter((item) => relatedNodeIds.has(item.id)),
    links: fakeLinks.filter(
      (link) => relatedNodeIds.has(link.source) && relatedNodeIds.has(link.target),
    ),
  };
}

/**
 * Return fake aggregate statistics derived from the current fake graph.
 *
 * @returns Total node and edge counts for the footer summary.
 */
export async function fetchStats(): Promise<StatsData> {
  return {
    totalNodes: fakeGraph.nodes.length,
    totalEdges: fakeGraph.links.length,
  };
}

/**
 * Fake blog submission endpoint used while the graph UI is still mock-backed.
 *
 * @param data User-submitted blog metadata.
 * @returns Resolved promise after local validation.
 */
export async function submitBlogInfo(data: {
  url: string;
  title?: string;
  description?: string;
  author?: string;
  tags?: string[];
}): Promise<void> {
  if (!data.url.trim()) {
    throw new Error("url_required");
  }
}
