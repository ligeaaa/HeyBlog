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
 * Build Google's public favicon service URL for one blog domain.
 *
 * @param node Blog-like frontend node that may include a domain.
 * @returns Google favicon URL, or undefined when the domain is missing.
 */
export function resolveGoogleIconUrl(node: Pick<GraphNode, "domain">): string | undefined {
  const hostname = node.domain?.trim();
  if (!hostname) {
    return undefined;
  }
  return `https://t2.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=https://${encodeURIComponent(hostname)}&size=64`;
}

/**
 * Resolve displayable icon candidates for a blog node.
 *
 * @param node Blog-like frontend node with optional crawled icon metadata.
 * @returns Ordered icon candidates for UI display fallback.
 */
export function resolveBlogIconUrls(
  node: Pick<GraphNode, "domain" | "iconUrl" | "url">,
): string[] {
  const originFaviconUrl = resolveOriginFaviconUrl(node);
  const normalizedIconUrl = node.iconUrl?.trim() || undefined;
  const candidates = [
    normalizedIconUrl,
    resolveGoogleIconUrl(node),
    resolveDuckDuckGoIconUrl(node),
    originFaviconUrl,
  ];
  return Array.from(new Set(candidates.filter((candidate): candidate is string => Boolean(candidate))));
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
  return resolveBlogIconUrls(node)[0];
}
