"""Unit tests for section-aware candidate extraction."""

from crawler.crawling.extraction import extract_candidate_links


def test_extractor_prefers_friend_link_section_over_navigation() -> None:
    """Extraction should prefer the detected friend-link section over the global nav."""
    html = """
    <html>
      <body>
        <nav>
          <a href="https://github.com/example">GitHub</a>
          <a href="/about">About</a>
        </nav>
        <section class="friend-links">
          <h2>友情链接</h2>
          <ul>
            <li><a href="https://friend-one.example/">Friend One</a></li>
            <li><a href="https://friend-two.example/">Friend Two</a></li>
            <li><a href="https://friend-three.example/">Friend Three</a></li>
          </ul>
        </section>
      </body>
    </html>
    """

    links = extract_candidate_links("https://blog.example.com/", html)
    urls = {link.url for link in links}

    assert "https://friend-one.example/" in urls
    assert "https://friend-two.example/" in urls
    assert "https://github.com/example" not in urls


def test_extractor_uses_first_container_as_fallback_when_no_section_matches() -> None:
    """Fallback extraction should stay within the first structural container."""
    html = """
    <html>
      <body>
        <div>
          <a href="https://friend.example/">Friend</a>
          <a href="https://other.example/">Other</a>
        </div>
        <div>
          <a href="https://third.example/">Third</a>
        </div>
      </body>
    </html>
    """

    links = extract_candidate_links("https://blog.example.com/", html)
    urls = {link.url for link in links}

    assert urls == {
        "https://friend.example/",
        "https://other.example/",
    }


def test_extractor_preserves_context_text_for_filtering() -> None:
    """Extracted candidates should carry the local context needed by filters."""
    html = """
    <html>
      <body>
        <section id="friends">
          <h2>友情链接</h2>
          <p>Recommended blogs from neighbors around the web.</p>
          <a href="https://friend.example/">Friend Blog</a>
        </section>
      </body>
    </html>
    """

    [link] = extract_candidate_links("https://blog.example.com/", html)

    assert link.text == "Friend Blog"
    assert "友情链接" in link.context_text
    assert "neighbors around the web" in link.context_text
