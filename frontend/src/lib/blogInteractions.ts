import { readStoredAuthSession } from "./auth";
import { postRecommendationEvent } from "./api";
import type { NavigateFunction } from "react-router-dom";
import type { BlogCatalogItem, GraphNode } from "../types/graph";

const BLOG_VISITOR_STORAGE_KEY = "heyblog.blog_interactions.visitor_id";
const BLOG_SESSION_STORAGE_KEY = "heyblog.blog_interactions.session_id";

let interactionOrder = 0;

export interface BlogInteractionEntrance {
  entranceKind: string;
  entranceUrl: string;
}

export interface BlogInteractionTarget {
  id: number;
  requestUuid?: string;
  impressionId?: number;
  position?: number;
}

/**
 * Convert a graph node into the minimal interaction target shape.
 *
 * @param blog Blog-like frontend model.
 * @returns Target fields required by the interaction event API.
 */
export function blogInteractionTarget(blog: BlogCatalogItem | GraphNode): BlogInteractionTarget {
  return {
    id: blog.id,
    requestUuid: "requestUuid" in blog ? blog.requestUuid : undefined,
    impressionId: "impressionId" in blog ? blog.impressionId : undefined,
    position: "position" in blog ? blog.position : undefined,
  };
}

/**
 * Create one browser-local random identifier without requiring crypto support.
 *
 * @param prefix Stable prefix that identifies the ID family.
 * @returns URL-safe identifier string.
 */
export function createBlogInteractionId(prefix: string) {
  const random = Math.random().toString(36).slice(2);
  return `${prefix}_${Date.now().toString(36)}_${random}`;
}

/**
 * Read or create the browser-stable visitor ID used for blog interactions.
 *
 * @returns Stable local visitor ID.
 */
export function getBlogInteractionVisitorId() {
  const existing = localStorage.getItem(BLOG_VISITOR_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const created = createBlogInteractionId("visitor");
  localStorage.setItem(BLOG_VISITOR_STORAGE_KEY, created);
  return created;
}

/**
 * Read or create the tab-session ID used for blog interactions.
 *
 * @returns Stable session ID for the current tab session.
 */
export function getBlogInteractionSessionId() {
  const existing = sessionStorage.getItem(BLOG_SESSION_STORAGE_KEY);
  if (existing) {
    return existing;
  }
  const created = createBlogInteractionId("session");
  sessionStorage.setItem(BLOG_SESSION_STORAGE_KEY, created);
  return created;
}

/**
 * Record one non-blocking blog interaction with required entrance metadata.
 *
 * @param target Blog interaction target.
 * @param eventType Event type recognized by the backend.
 * @param entrance Required entry-point metadata for later aggregation.
 * @param attributes Optional event metadata.
 */
export function recordBlogInteraction(
  target: BlogInteractionTarget,
  eventType: string,
  entrance: BlogInteractionEntrance,
  attributes?: Record<string, unknown>,
) {
  interactionOrder += 1;
  const session = readStoredAuthSession();
  void postRecommendationEvent(
    {
      eventUuid: createBlogInteractionId("event"),
      eventType,
      blogId: target.id,
      visitorId: getBlogInteractionVisitorId(),
      sessionId: getBlogInteractionSessionId(),
      entranceKind: entrance.entranceKind,
      entranceUrl: entrance.entranceUrl,
      requestUuid: target.requestUuid,
      impressionId: target.impressionId,
      position: target.position,
      interactionOrder,
      clientEventAt: new Date().toISOString(),
      attributes,
    },
    session?.token,
  ).catch((error: unknown) => {
    console.warn("Failed to record blog interaction", error);
  });
}

/**
 * Record and open the canonical blog detail route.
 *
 * @param navigate React Router navigation function.
 * @param blog Blog target whose detail route should open.
 * @param entrance Required entry-point metadata for later aggregation.
 * @param attributes Optional event metadata.
 * @param options Optional browser navigation behavior.
 */
export function openTrackedBlogDetail(
  navigate: NavigateFunction,
  blog: BlogCatalogItem | GraphNode,
  entrance: BlogInteractionEntrance,
  attributes?: Record<string, unknown>,
  options?: { newTab?: boolean },
) {
  recordBlogInteraction(blogInteractionTarget(blog), "detail_open", entrance, attributes);
  const detailPath = `/blogs/${blog.id}`;
  if (options?.newTab) {
    window.open(detailPath, "_blank", "noopener,noreferrer");
    return;
  }
  navigate(detailPath);
}
