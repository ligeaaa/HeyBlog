import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { openTrackedBlogDetail, type BlogInteractionEntrance } from "../lib/blogInteractions";
import type { BlogCatalogItem, GraphNode } from "../types/graph";

interface BlogDetailLinkProps extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "onClick"> {
  blog: BlogCatalogItem | GraphNode;
  entranceKind: string;
  entranceUrl: string;
  children: ReactNode;
  eventAttributes?: Record<string, unknown>;
  openInNewTab?: boolean;
}

/**
 * Render the canonical tracked navigation control for blog detail routes.
 *
 * @param blog Blog target whose detail route should open.
 * @param entranceKind Stable entry-point category for analytics.
 * @param entranceUrl Raw entry-point URL for analytics.
 * @param children Visible button content.
 * @param eventAttributes Optional event metadata sent with the interaction.
 * @param openInNewTab Whether to open the detail route in a new browser tab.
 * @returns Button that records `detail_open` and navigates to `/blogs/:id`.
 */
export function BlogDetailLink({
  blog,
  entranceKind,
  entranceUrl,
  children,
  eventAttributes,
  openInNewTab,
  ...buttonProps
}: BlogDetailLinkProps) {
  const navigate = useNavigate();
  const entrance: BlogInteractionEntrance = { entranceKind, entranceUrl };
  return (
    <button
      {...buttonProps}
      type={buttonProps.type ?? "button"}
      onClick={() => {
        openTrackedBlogDetail(navigate, blog, entrance, eventAttributes, { newTab: openInNewTab });
      }}
    >
      {children}
    </button>
  );
}
