import {
  ArrowLeft,
  ArrowRight,
  Loader2,
  Network,
  Route,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { BlogDetailLink } from "../components/BlogDetailLink";
import { BlogExternalLink } from "../components/BlogExternalLink";
import { Navigation } from "../components/Navigation";
import { fetchBlogDetail } from "../lib/api";
import { openTrackedBlogDetail } from "../lib/blogInteractions";
import { resolveBlogIconUrls, resolveIconProxyUrl } from "../lib/icon";
import type { BlogDetail, BlogDiscoveryPath, BlogDiscoveryStep, BlogRelationGraph, GraphNode } from "../types/graph";

const RELATION_GRAPH_LINK_DISTANCE = 78;
const RELATION_GRAPH_CHARGE_STRENGTH = -260;
const DETAIL_PAGE_EXTERNAL_ENTRANCE_KIND = "blog_detail_hero_external";
const DETAIL_DISCOVERY_PATH_ENTRANCE_KIND = "blog_detail_discovery_path";
const DETAIL_RELATION_GRAPH_ENTRANCE_KIND = "blog_detail_relation_graph";

/**
 * Format a numeric count for compact detail cards.
 *
 * @param value Count value to display.
 * @returns Localized count string.
 */
function formatCount(value: number) {
  return new Intl.NumberFormat("zh-CN").format(value);
}

/**
 * Render a detail page hero icon with favicon fallbacks.
 *
 * @param props Blog detail node used to resolve icon candidates.
 * @returns Blog icon image or a text fallback.
 */
function BlogHeroIcon({ detail }: { detail: BlogDetail }) {
  const iconUrls = resolveBlogIconUrls(detail);
  const [iconIndex, setIconIndex] = useState(0);
  const iconUrl = iconUrls[iconIndex];

  useEffect(() => {
    setIconIndex(0);
  }, [detail.id, detail.iconUrl, detail.url, detail.domain]);

  return (
    <div className="mb-4 flex h-16 w-16 items-center justify-center overflow-hidden rounded-lg bg-sky-100 text-2xl font-semibold text-sky-700 ring-1 ring-sky-200">
      {iconUrl ? (
        <img
          src={iconUrl}
          alt={`${detail.domain} icon`}
          className="h-full w-full object-cover"
          loading="lazy"
          referrerPolicy="no-referrer"
          onError={() => setIconIndex((currentIndex) => currentIndex + 1)}
        />
      ) : (
        <span>{(detail.domain || "?").slice(0, 1).toUpperCase()}</span>
      )}
    </div>
  );
}

/**
 * Render one compact card for a historical discovery path step.
 *
 * @param props Discovery step returned by the blog detail API.
 * @returns Clickable blog card with title, icon, and URL.
 */
function DiscoveryPathCard({ step, entranceUrl }: { step: BlogDiscoveryStep; entranceUrl: string }) {
  const blog = {
    id: step.blogId,
    url: step.url,
    domain: step.domain,
    title: step.blog?.title ?? null,
    iconUrl: step.blog?.iconUrl ?? null,
  };
  const iconUrls = resolveBlogIconUrls(blog);
  const [iconIndex, setIconIndex] = useState(0);
  const iconUrl = iconUrls[iconIndex];

  useEffect(() => {
    setIconIndex(0);
  }, [step.blogId, step.url, step.domain, step.blog?.iconUrl]);

  return (
    <BlogDetailLink
      blog={blog}
      entranceKind={DETAIL_DISCOVERY_PATH_ENTRANCE_KIND}
      entranceUrl={entranceUrl}
      className="flex w-56 items-center gap-3 rounded-lg border border-slate-200 bg-slate-50 px-3 py-3 transition-colors hover:border-sky-300 hover:bg-sky-50"
    >
      <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center overflow-hidden rounded-lg bg-white text-sm font-semibold text-slate-500 ring-1 ring-slate-200">
        {iconUrl ? (
          <img
            src={iconUrl}
            alt={`${step.domain} icon`}
            className="h-full w-full object-cover"
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => setIconIndex((currentIndex) => currentIndex + 1)}
          />
        ) : (
          <span>{(step.domain || "?").slice(0, 1).toUpperCase()}</span>
        )}
      </div>
      <div className="min-w-0">
        <div className="truncate text-sm font-medium text-slate-950">{step.blog?.title || step.domain}</div>
        <div className="mt-1 truncate text-xs text-slate-500">{step.url}</div>
      </div>
    </BlogDetailLink>
  );
}

/**
 * Render only the historical discovery path, without outgoing branches.
 *
 * @param props Discovery path payload.
 * @returns Historical discovery path section or null when unavailable.
 */
function DiscoveryPathSection({ path, entranceUrl }: { path: BlogDiscoveryPath | null; entranceUrl: string }) {
  if (!path || path.steps.length === 0) {
    return null;
  }

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Route className="h-5 w-5 text-sky-600" />
        <h2 className="text-xl text-slate-950">发现路径</h2>
      </div>
      <div className="overflow-x-auto">
        <div className="flex min-w-max items-center gap-3">
          {path.steps.map((step, index) => (
            <div key={`${step.blogId}-${index}`} className="flex items-center gap-3">
              <DiscoveryPathCard step={step} entranceUrl={entranceUrl} />
              {index < path.steps.length - 1 ? (
                <div className="flex items-center gap-2 text-slate-300">
                  <div className="h-px w-6 bg-slate-300" />
                  <ArrowRight className="h-4 w-4" />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

interface RelationRenderNode extends Omit<GraphNode, "id" | "iconUrl"> {
  id: string;
  blogId: number;
  original: GraphNode;
  label: string;
  iconUrls: string[];
  radius: number;
}

interface RelationRenderLink {
  id: string;
  source: string | RelationRenderNode;
  target: string | RelationRenderNode;
}

interface RelationRenderGraph {
  nodes: RelationRenderNode[];
  links: RelationRenderLink[];
}

/**
 * Build force-graph render data from the blog relation API payload.
 *
 * @param graph Directional relation graph payload.
 * @returns Render nodes and links for react-force-graph-2d.
 */
function buildRelationRenderGraph(graph: BlogRelationGraph): RelationRenderGraph {
  const nodes = graph.nodes.map((node) => {
    const iconUrls = resolveBlogIconUrls(node).map(resolveIconProxyUrl);
    return {
      ...node,
      id: String(node.id),
      blogId: node.id,
      original: node,
      label: node.title?.trim() || node.domain || node.url,
      iconUrls,
      radius: node.id === graph.focusBlogId ? 18 : 13,
    };
  });
  const nodeIds = new Set(nodes.map((node) => node.id));
  return {
    nodes,
    links: graph.edges
      .map((edge) => ({
        id: edge.id,
        source: String(edge.source),
        target: String(edge.target),
      }))
      .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)),
  };
}

/**
 * Resolve a force-graph link endpoint id after d3 mutates links.
 *
 * @param endpoint Link source or target value.
 * @returns Stable render node id.
 */
function relationEndpointId(endpoint: string | RelationRenderNode): string {
  return typeof endpoint === "object" ? endpoint.id : String(endpoint);
}

/**
 * Draw a relation graph node on a 2D force-graph canvas.
 *
 * @param node Render node to draw.
 * @param context Canvas context from react-force-graph-2d.
 * @param imageCache Loaded icon cache keyed by proxied icon URL.
 * @param focusBlogId Current detail blog id.
 * @param hoveredBlogId Hovered blog id, if any.
 */
function paintRelationNode(
  node: RelationRenderNode,
  context: CanvasRenderingContext2D,
  imageCache: Map<string, HTMLImageElement>,
  focusBlogId: number,
  hoveredBlogId: number | null,
) {
  const x = node.x ?? 0;
  const y = node.y ?? 0;
  const isFocus = node.blogId === focusBlogId;
  const isHovered = node.blogId === hoveredBlogId;
  const radius = node.radius + (isHovered ? 3 : 0);
  const icon = node.iconUrls.map((url) => imageCache.get(url)).find((image) => image?.complete && image.naturalWidth > 0);

  context.save();
  context.beginPath();
  context.arc(x, y, radius + (isFocus ? 5 : 3), 0, Math.PI * 2);
  context.fillStyle = isFocus ? "rgba(14, 165, 233, 0.2)" : "rgba(148, 163, 184, 0.18)";
  context.fill();

  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.fillStyle = icon ? "#ffffff" : isFocus ? "#bae6fd" : "#cbd5e1";
  context.fill();
  context.lineWidth = isFocus ? 3 : 1.5;
  context.strokeStyle = isFocus ? "#0284c7" : "#ffffff";
  context.stroke();

  if (icon) {
    context.save();
    context.beginPath();
    context.arc(x, y, radius - 1, 0, Math.PI * 2);
    context.clip();
    context.drawImage(icon, x - radius, y - radius, radius * 2, radius * 2);
    context.restore();
  }
  context.restore();
}

/**
 * Paint the clickable pointer area for one relation graph node.
 *
 * @param node Render node to cover.
 * @param paintColor Hidden pointer-picking color supplied by force graph.
 * @param context Canvas context from react-force-graph-2d.
 */
function paintRelationPointerArea(node: RelationRenderNode, paintColor: string, context: CanvasRenderingContext2D) {
  const radius = node.radius + 5;
  context.fillStyle = paintColor;
  context.beginPath();
  context.arc(node.x ?? 0, node.y ?? 0, radius, 0, Math.PI * 2);
  context.fill();
}

/**
 * Render one paged blog relation graph as an interactive 2D force graph.
 *
 * @param props Directional relation graph payload.
 * @returns 2D force-graph relation view.
 */
function RelationGraphView({ graph, entranceUrl }: { graph: BlogRelationGraph; entranceUrl: string }) {
  const navigate = useNavigate();
  const graphRef = useRef<ForceGraphMethods<RelationRenderNode, RelationRenderLink> | undefined>(undefined);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const imageCacheRef = useRef(new Map<string, HTMLImageElement>());
  const [size, setSize] = useState({ width: 960, height: 360 });
  const [isMeasured, setIsMeasured] = useState(false);
  const [hoveredBlog, setHoveredBlog] = useState<GraphNode | null>(null);
  const [iconPaintVersion, setIconPaintVersion] = useState(0);
  const renderGraph = useMemo(() => buildRelationRenderGraph(graph), [graph]);
  const hoveredBlogId = hoveredBlog?.id ?? null;
  const fitGraphToView = useCallback((durationMs = 500) => {
    graphRef.current?.zoomToFit(durationMs, 44);
  }, []);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }
    const observer = new ResizeObserver(([entry]) => {
      setSize({
        width: Math.max(320, Math.floor(entry.contentRect.width)),
        height: Math.max(320, Math.floor(entry.contentRect.height)),
      });
      setIsMeasured(true);
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const graphInstance = graphRef.current;
    if (!isMeasured || !graphInstance) {
      return undefined;
    }
    graphInstance.d3Force("center", null);
    const chargeForce = graphInstance.d3Force("charge") as { strength?: (value: number) => unknown } | undefined;
    chargeForce?.strength?.(RELATION_GRAPH_CHARGE_STRENGTH);
    const linkForce = graphInstance.d3Force("link") as { distance?: (value: number) => unknown } | undefined;
    linkForce?.distance?.(RELATION_GRAPH_LINK_DISTANCE);
    graphInstance.d3ReheatSimulation();
    const firstFitTimer = window.setTimeout(() => fitGraphToView(450), 120);
    const settledFitTimer = window.setTimeout(() => fitGraphToView(450), 620);
    return () => {
      window.clearTimeout(firstFitTimer);
      window.clearTimeout(settledFitTimer);
    };
  }, [fitGraphToView, isMeasured, renderGraph, size.height, size.width]);

  useEffect(() => {
    let isDisposed = false;
    const urls = Array.from(new Set(renderGraph.nodes.flatMap((node) => node.iconUrls)));
    urls.forEach((url) => {
      if (imageCacheRef.current.has(url)) {
        return;
      }
      const image = new Image();
      image.crossOrigin = "anonymous";
      image.onload = () => {
        if (!isDisposed) {
          imageCacheRef.current.set(url, image);
          setIconPaintVersion((version) => version + 1);
        }
      };
      image.onerror = () => {
        imageCacheRef.current.delete(url);
      };
      image.src = url;
      imageCacheRef.current.set(url, image);
    });
    return () => {
      isDisposed = true;
    };
  }, [renderGraph.nodes]);

  const nodeCanvasObject = useCallback(
    (node: RelationRenderNode, context: CanvasRenderingContext2D) => {
      paintRelationNode(node, context, imageCacheRef.current, graph.focusBlogId, hoveredBlogId);
    },
    [graph.focusBlogId, hoveredBlogId, iconPaintVersion],
  );

  return (
    <div ref={containerRef} className="relative h-[380px] overflow-hidden rounded-lg bg-slate-50">
      {isMeasured ? (
        <ForceGraph2D<RelationRenderNode, RelationRenderLink>
          ref={graphRef}
          graphData={renderGraph}
          nodeId="id"
          width={size.width}
          height={size.height}
          backgroundColor="#f8fafc"
          nodeLabel={(node) => `${node.label}\n${node.url}`}
          nodeVal={(node) => node.radius}
          nodeCanvasObjectMode={() => "replace"}
          nodeCanvasObject={nodeCanvasObject}
          nodePointerAreaPaint={paintRelationPointerArea}
          linkSource="source"
          linkTarget="target"
          linkColor={() => (graph.direction === "incoming" ? "rgba(2, 132, 199, 0.58)" : "rgba(5, 150, 105, 0.58)")}
          linkWidth={() => 1.7}
          linkDirectionalArrowLength={5}
          linkDirectionalArrowRelPos={1}
          linkDirectionalArrowColor={() => (graph.direction === "incoming" ? "#0284c7" : "#059669")}
          enableNodeDrag={false}
          enablePointerInteraction
          cooldownTicks={90}
          d3VelocityDecay={0.34}
          d3AlphaDecay={0.04}
          onNodeHover={(node) => setHoveredBlog(node?.original ?? null)}
          onNodeClick={(node) => {
            openTrackedBlogDetail(
              navigate,
              node.original,
              {
                entranceKind: DETAIL_RELATION_GRAPH_ENTRANCE_KIND,
                entranceUrl,
              },
              { relation_direction: graph.direction, focus_blog_id: graph.focusBlogId },
            );
          }}
          showPointerCursor={(item) => Boolean(item && "blogId" in item)}
        />
      ) : null}
      <div className="sr-only" aria-live="polite">
        {renderGraph.nodes.map((node) => (
          <span key={node.id}>{`${node.label} ${node.url}`}</span>
        ))}
      </div>
      {hoveredBlog ? (
        <div
          role="tooltip"
          className="pointer-events-none absolute left-4 top-4 z-30 max-w-[min(360px,calc(100%-2rem))] rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm shadow-lg"
        >
          <div className="truncate font-medium text-slate-950">{hoveredBlog.title || hoveredBlog.domain}</div>
          <div className="mt-1 break-all text-xs text-slate-500">{hoveredBlog.url || hoveredBlog.domain}</div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Render the paged blog association module.
 *
 * @param props Incoming and outgoing relation graphs.
 * @returns Blog association section with two graph pages.
 */
function BlogAssociationSection({ detail, entranceUrl }: { detail: BlogDetail; entranceUrl: string }) {
  const [activeGraph, setActiveGraph] = useState<"incoming" | "outgoing">("incoming");
  const graph = detail.relationGraphs[activeGraph];

  return (
    <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-4 flex items-center gap-2">
        <Network className="h-5 w-5 text-sky-600" />
        <h2 className="text-xl text-slate-950">博客关联</h2>
      </div>
      <div className="mb-4 inline-flex rounded-lg border border-slate-200 bg-slate-50 p-1">
        <button
          type="button"
          onClick={() => setActiveGraph("incoming")}
          className={[
            "rounded-md px-4 py-2 text-sm transition-colors",
            activeGraph === "incoming" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-900",
          ].join(" ")}
        >
          入链关系
        </button>
        <button
          type="button"
          onClick={() => setActiveGraph("outgoing")}
          className={[
            "rounded-md px-4 py-2 text-sm transition-colors",
            activeGraph === "outgoing" ? "bg-white text-slate-950 shadow-sm" : "text-slate-500 hover:text-slate-900",
          ].join(" ")}
        >
          出链关系
        </button>
      </div>
      {graph.nodes.length > 1 ? (
        <RelationGraphView graph={graph} entranceUrl={entranceUrl} />
      ) : (
        <div className="flex h-[260px] items-center justify-center rounded-lg bg-slate-50 text-sm text-slate-500">
          暂无{activeGraph === "incoming" ? "入链" : "出链"}关联。
        </div>
      )}
    </section>
  );
}

/**
 * Render the public blog detail page.
 *
 * @returns Blog detail route UI.
 */
export function BlogDetailPage() {
  const { blogId } = useParams();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<BlogDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const numericBlogId = Number(blogId);

  useEffect(() => {
    let isDisposed = false;

    /**
     * Load the route blog detail payload.
     *
     * @returns Promise resolved when detail state settles.
     */
    async function loadDetail() {
      if (!Number.isInteger(numericBlogId) || numericBlogId <= 0) {
        setErrorMessage("博客 ID 无效。");
        setIsLoading(false);
        return;
      }

      setIsLoading(true);
      setErrorMessage(null);
      try {
        const payload = await fetchBlogDetail(numericBlogId);
        if (!isDisposed) {
          setDetail(payload);
        }
      } catch {
        if (!isDisposed) {
          setDetail(null);
          setErrorMessage("博客详情加载失败。");
          toast.error("博客详情加载失败，请稍后重试。");
        }
      } finally {
        if (!isDisposed) {
          setIsLoading(false);
        }
      }
    }

    void loadDetail();
    return () => {
      isDisposed = true;
    };
  }, [numericBlogId]);

  return (
    <div className="min-h-screen overflow-x-hidden bg-white">
      <Navigation />
      <main className="mx-auto max-w-6xl px-6 pb-16 pt-24 sm:px-8">
        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mb-8 inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm text-slate-600 transition-colors hover:border-sky-300 hover:text-sky-700"
        >
          <ArrowLeft className="h-4 w-4" />
          返回
        </button>

        {isLoading ? (
          <section className="flex min-h-[360px] items-center justify-center">
            <div className="flex flex-col items-center gap-4 text-slate-500">
              <Loader2 className="h-10 w-10 animate-spin text-sky-500" />
              <div>正在加载博客详情...</div>
            </div>
          </section>
        ) : null}

        {!isLoading && errorMessage ? (
          <section className="rounded-lg border border-rose-200 bg-rose-50 px-6 py-8 text-rose-700">
            {errorMessage}
          </section>
        ) : null}

        {!isLoading && detail ? (
          <div className="space-y-8">
            <section className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
                <div className="min-w-0">
                  <BlogHeroIcon detail={detail} />
                  <h1 className="break-words text-4xl leading-tight text-slate-950">{detail.title || detail.domain}</h1>
                  <div className="mt-2 text-base text-slate-500">{detail.domain}</div>
                  <BlogExternalLink
                    blog={detail}
                    entranceKind={DETAIL_PAGE_EXTERNAL_ENTRANCE_KIND}
                    entranceUrl={window.location.href}
                    className="mt-4 inline-flex max-w-full items-center gap-2 break-all text-sm text-sky-700 hover:underline"
                  >
                    {detail.url}
                  </BlogExternalLink>
                </div>
              </div>
            </section>

            <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-sky-100 text-sky-700">
                  <ArrowLeft className="h-5 w-5" />
                </div>
                <div className="text-sm text-slate-500">入链</div>
                <div className="mt-2 text-3xl text-slate-950">{formatCount(detail.incomingLinks)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700">
                  <ArrowRight className="h-5 w-5" />
                </div>
                <div className="text-sm text-slate-500">出链</div>
                <div className="mt-2 text-3xl text-slate-950">{formatCount(detail.outgoingLinks)}</div>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-violet-100 text-violet-700">
                  <Network className="h-5 w-5" />
                </div>
                <div className="text-sm text-slate-500">直接相关博客</div>
                <div className="mt-2 text-3xl text-slate-950">{formatCount(detail.relatedNodes.length)}</div>
              </div>
            </section>

            <DiscoveryPathSection path={detail.discoveryPath} entranceUrl={window.location.href} />

            <BlogAssociationSection detail={detail} entranceUrl={window.location.href} />
          </div>
        ) : null}
      </main>
    </div>
  );
}
