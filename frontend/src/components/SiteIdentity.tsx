import { useEffect, useState } from "react";

type NameElement = "div" | "h3" | "p" | "span";

type Props = {
  title?: string | null;
  domain: string;
  iconUrl?: string | null;
  className?: string;
  compact?: boolean;
  nameElement?: NameElement;
};

function fallbackGlyph(value: string) {
  const trimmed = value.trim();
  return trimmed ? trimmed[0]?.toUpperCase() ?? "?" : "?";
}

export function SiteIdentity({
  title,
  domain,
  iconUrl,
  className,
  compact = false,
  nameElement = "p",
}: Props) {
  const [imageFailed, setImageFailed] = useState(false);
  const displayName = title?.trim() || domain;
  const subtitle = title?.trim() && title.trim() !== domain ? domain : null;
  const NameTag = nameElement;

  useEffect(() => {
    setImageFailed(false);
  }, [iconUrl]);

  const wrapperClassName = ["site-identity", compact ? "site-identity-compact" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={wrapperClassName}>
      <div className="site-identity-badge" aria-hidden={iconUrl && !imageFailed ? undefined : true}>
        {iconUrl && !imageFailed ? (
          <img
            className="site-identity-icon"
            src={iconUrl}
            alt={`${displayName} icon`}
            loading="lazy"
            referrerPolicy="no-referrer"
            onError={() => {
              setImageFailed(true);
            }}
          />
        ) : (
          <span className="site-identity-fallback">{fallbackGlyph(displayName)}</span>
        )}
      </div>
      <div className="site-identity-copy">
        <NameTag className="site-identity-name">{displayName}</NameTag>
        {subtitle ? <p className="site-identity-subtitle">{subtitle}</p> : null}
      </div>
    </div>
  );
}
