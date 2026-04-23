/**
 * Frontend-owned normalized graph models derived from backend `/api/*` payloads.
 */
export interface GraphNode {
  id: number;
  url: string;
  domain: string;
  title: string | null;
  iconUrl: string | null;
  description?: string | null;
  x?: number;
  y?: number;
  degree?: number;
  incomingCount?: number;
  outgoingCount?: number;
  priorityScore?: number;
  componentId?: string;
}

export interface GraphEdge {
  id: string;
  source: number;
  target: number;
  linkText: string | null;
  linkUrlRaw: string;
}

export interface GraphMeta {
  strategy: string;
  limit: number;
  focusNodeId?: number | null;
  hops?: number | null;
  hasStablePositions?: boolean;
  snapshotVersion?: string;
  generatedAt?: string;
  source?: string;
  totalNodes?: number;
  totalEdges?: number;
  availableNodes?: number;
  availableEdges?: number;
  selectedNodes?: number;
  selectedEdges?: number;
  snapshotNamespace?: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  meta?: GraphMeta;
}

export interface LookupResult {
  queryUrl: string;
  normalizedQueryUrl: string;
  matchReason: string | null;
  totalMatches: number;
  items: GraphNode[];
}

export interface RecommendedBlog extends GraphNode {
  viaBlogs: GraphNode[];
}

export interface BlogDetail extends GraphNode {
  incomingLinks: number;
  outgoingLinks: number;
  relatedNodes: GraphNode[];
  recommendedBlogs: RecommendedBlog[];
}

export interface StatsData {
  totalNodes: number;
  totalEdges: number;
}

export interface StatusData {
  isRunning: boolean;
  pendingTasks: number;
  processingTasks: number;
  finishedTasks: number;
  failedTasks: number;
  totalNodes: number;
  totalEdges: number;
}

export interface BlogCatalogItem extends GraphNode {
  normalizedUrl: string;
  identityKey: string;
  identityReasonCodes: string[];
  identityRulesetVersion: string;
  email: string | null;
  statusCode: number | null;
  crawlStatus: string;
  friendLinksCount: number;
  lastCrawledAt: string | null;
  createdAt: string;
  updatedAt: string;
  incomingCount: number;
  outgoingCount: number;
  connectionCount: number;
  activityAt: string | null;
  identityComplete: boolean;
}

export interface BlogCatalogPage {
  items: BlogCatalogItem[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
  sort: string;
}

export interface AdminRuntimeStatus {
  runnerStatus: string;
  activeRunId: string | null;
  workerCount: number;
  activeWorkers: number;
  currentBlogId: number | null;
  currentUrl: string | null;
  currentStage: string | null;
  elapsedSeconds: number | null;
  maintenanceInProgress: boolean;
}

export interface AdminRuntimeCurrent {
  runnerStatus: string;
  activeRunId: string | null;
  workerCount: number;
  activeWorkers: number;
  currentBlogId: number | null;
  currentUrl: string | null;
  currentStage: string | null;
  elapsedSeconds: number | null;
}

export interface AdminDedupSummary {
  id: number;
  status: string;
  totalCount: number;
  scannedCount: number;
  removedCount: number;
  keptCount: number;
  createdAt: string;
  updatedAt: string;
}

export interface AdminUrlRefilterRun {
  id: number;
  status: string;
  filterChainVersion: string;
  crawlerWasRunning: boolean;
  backupPath: string | null;
  totalCount: number;
  scannedCount: number;
  unchangedCount: number;
  activatedCount: number;
  deactivatedCount: number;
  retaggedCount: number;
  lastRawUrlId: number | null;
  startedAt: string | null;
  completedAt: string | null;
  errorMessage: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface AdminUrlRefilterRunEvent {
  id: number;
  runId: number;
  message: string;
  createdAt: string | null;
}

export interface FilterStatsData {
  byFilterReason: Record<string, number>;
}
