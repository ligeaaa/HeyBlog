"""Unit tests for homepage title/icon extraction."""

from crawler.site_metadata import extract_site_metadata


def test_extract_site_metadata_ignores_non_http_icon_urls() -> None:
    """Unsafe icon schemes should be skipped in favor of a safe fallback."""
    metadata = extract_site_metadata(
        "https://blog.example.com/",
        """
        <html>
          <head>
            <title>Alpha Blog</title>
            <link rel="icon" href="data:image/png;base64,AAA" />
            <link rel="shortcut icon" href="javascript:alert('xss')" />
          </head>
        </html>
        """,
    )

    assert metadata.title == "Alpha Blog"
    assert metadata.icon_url == "https://blog.example.com/favicon.ico"


def test_extract_site_metadata_returns_none_when_page_url_is_not_http() -> None:
    """Fallback favicon should only be synthesized for HTTP(S) page URLs."""
    metadata = extract_site_metadata(
        "ftp://blog.example.com/",
        "<html><head><title>Alpha Blog</title></head></html>",
    )

    assert metadata.title == "Alpha Blog"
    assert metadata.icon_url is None
