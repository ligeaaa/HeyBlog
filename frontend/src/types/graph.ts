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
  z?: number;
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

export interface UserProfile {
  id: number;
  email: string;
  displayName: string;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface AuthSession {
  token: string;
  expiresAt: string | null;
  user: UserProfile;
}

export interface UserLabelSelection {
  id: number;
  normalizedUrl: string;
  labelId: number;
  label: string;
  labelName: string;
  createdAt: string | null;
  updatedAt: string | null;
  blog: BlogCatalogItem | null;
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

export interface AdminRequeueFailedBlogsResult {
  requeued: number;
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

export interface AdminBlogLabelTag {
  id: number;
  name: string;
  slug: string;
  createdAt: string;
  updatedAt: string;
}

export interface AdminBlogLabelAssignment extends AdminBlogLabelTag {
  labeledAt: string;
}

export interface AdminBlogLabelingCandidate extends BlogCatalogItem {
  labels: AdminBlogLabelAssignment[];
  labelSlugs: string[];
  lastLabeledAt: string | null;
  isLabeled: boolean;
}

export interface AdminBlogLabelingPage {
  items: AdminBlogLabelingCandidate[];
  availableTags: AdminBlogLabelTag[];
  page: number;
  pageSize: number;
  totalItems: number;
  totalPages: number;
  hasNext: boolean;
  hasPrev: boolean;
  sort: string;
}

export interface AdminBlogLabelCounts {
  totalLabeled: number;
  byLabel: Record<string, number>;
}

export interface AdminBlogLabelParquetStatus {
  path: string;
  filename: string;
  exists: boolean;
  savedCount: number;
  totalLabeled: number;
  missingCount: number;
  batchSize: number;
  rewritten: boolean;
  message: string;
  updatedAt: string | null;
}

export interface FilterStatsData {
  byFilterReason: Record<string, number>;
  ruleDrops: Record<string, number>;
  successSources: Record<string, number>;
  funnel: {
    raw: number;
    afterRules: number;
    modelRejected: number;
    success: number;
    blogs: number;
  };
}
