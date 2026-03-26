from app.crawler.filters import is_blog_candidate


def test_blog_candidate_rejects_self_domain() -> None:
    assert not is_blog_candidate("https://blog.example.com/post", "blog.example.com")


def test_blog_candidate_rejects_known_platform() -> None:
    assert not is_blog_candidate("https://github.com/user/repo", "blog.example.com")


def test_blog_candidate_accepts_external_blog() -> None:
    assert is_blog_candidate("https://other-blog.example.net/", "blog.example.com")
