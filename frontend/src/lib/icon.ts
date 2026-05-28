import type { GraphNode } from "../types/graph";

/**
 * Build the canonical origin favicon URL for a blog node.
 *
 * @param node Blog-like frontend node that may include a page URL.
 * @returns Absolute origin favicon URL, or undefined when the URL is unusable.
 */
export function resolveOriginFaviconUrl(node: Pick<GraphNode, "url">): string | undefined {
  if (!node.url) {
    return undefined;
  }
  try {
    return new URL("/favicon.ico", node.url).toString();
  } catch {
    return undefined;
  }
}

/**
 * Build a deterministic public favicon proxy URL for one blog domain.
 *
 * @param node Blog-like frontend node that may include a domain.
 * @returns DuckDuckGo favicon URL, or undefined when the domain is missing.
 */
export function resolveDuckDuckGoIconUrl(node: Pick<GraphNode, "domain">): string | undefined {
  const hostname = node.domain?.trim();
  if (!hostname) {
    return undefined;
  }
  return `https://icons.duckduckgo.com/ip3/${hostname}.ico`;
}

/**
 * Resolve the best displayable icon URL for a blog node.
 *
 * @param node Blog-like frontend node with optional crawled icon metadata.
 * @returns Preferred icon URL with deterministic fallbacks, or undefined.
 */
export function resolveBlogIconUrl(
  node: Pick<GraphNode, "domain" | "iconUrl" | "url">,
): string | undefined {
  const originFaviconUrl = resolveOriginFaviconUrl(node);
  const normalizedIconUrl = node.iconUrl?.trim() || undefined;

  if (normalizedIconUrl && normalizedIconUrl !== originFaviconUrl) {
    return normalizedIconUrl;
  }

  return resolveDuckDuckGoIconUrl(node) ?? normalizedIconUrl ?? originFaviconUrl ?? undefined;
}
