import { ArrowUpRight } from "lucide-react";
import type { AnchorHTMLAttributes, ReactNode } from "react";
import { blogInteractionTarget, recordBlogInteraction, type BlogInteractionEntrance } from "../lib/blogInteractions";
import type { BlogCatalogItem, GraphNode } from "../types/graph";

interface BlogExternalLinkProps extends Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href" | "target" | "rel" | "onClick"> {
  blog: BlogCatalogItem | GraphNode;
  entranceKind: string;
  entranceUrl: string;
  children?: ReactNode;
  showIcon?: boolean;
  eventAttributes?: Record<string, unknown>;
}

/**
 * Render the canonical tracked external link for a blog URL.
 *
 * @param blog Blog target whose external URL should open.
 * @param entranceKind Stable entry-point category for analytics.
 * @param entranceUrl Raw entry-point URL for analytics.
 * @param children Optional visible link content.
 * @param showIcon Whether to append the external-link icon.
 * @param eventAttributes Optional event metadata sent with the interaction.
 * @returns External anchor that records `external_open` before opening.
 */
export function BlogExternalLink({
  blog,
  entranceKind,
  entranceUrl,
  children,
  showIcon = true,
  eventAttributes,
  ...anchorProps
}: BlogExternalLinkProps) {
  const entrance: BlogInteractionEntrance = { entranceKind, entranceUrl };
  return (
    <a
      {...anchorProps}
      href={blog.url}
      target="_blank"
      rel="noreferrer"
      onClick={() => recordBlogInteraction(blogInteractionTarget(blog), "external_open", entrance, eventAttributes)}
    >
      {children ?? blog.url}
      {showIcon ? <ArrowUpRight className="h-4 w-4 flex-shrink-0" /> : null}
    </a>
  );
}
