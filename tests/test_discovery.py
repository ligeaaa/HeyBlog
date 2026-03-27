"""Unit tests for friend-link page discovery."""

from app.crawler.discovery import discover_friend_links_pages


def test_discovery_finds_footer_friend_links_page_without_scoring() -> None:
    """Footer context and keyword text should surface a non-standard friend-link page."""
    html = """
    <html>
      <body>
        <footer>
          <section class="neighbors">
            <a href="/pals">邻居们</a>
          </section>
        </footer>
      </body>
    </html>
    """

    result = discover_friend_links_pages("https://blog.example.com/", html)

    assert result[0] == "https://blog.example.com/pals"


def test_discovery_rejects_false_positive_links_page() -> None:
    """Generic resource links should not be treated as friend-link pages."""
    html = """
    <html>
      <body>
        <nav>
          <a href="/resources/links">Useful links</a>
        </nav>
      </body>
    </html>
    """

    result = discover_friend_links_pages("https://blog.example.com/", html)

    assert "https://blog.example.com/resources/links" not in result


def test_discovery_falls_back_to_path_hints_when_no_signal_exists() -> None:
    """When homepage evidence is weak, fallback path hints should still be returned."""
    html = "<html><body><a href=\"/about\">About</a></body></html>"

    result = discover_friend_links_pages("https://blog.example.com/", html)

    assert "https://blog.example.com/links" in result
