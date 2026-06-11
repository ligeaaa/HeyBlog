import { describe, expect, test } from "vitest";
import { resolveBlogIconUrls, resolveProxiedBlogIconUrls } from "./icon";

describe("icon helpers", () => {
  test("keeps direct display candidates unchanged", () => {
    const urls = resolveBlogIconUrls({
      url: "https://blog.example.com/posts/1",
      domain: "blog.example.com",
      iconUrl: "https://cdn.example.com/icon.png",
    });

    expect(urls[0]).toBe("https://cdn.example.com/icon.png");
  });

  test("wraps graph texture candidates with the same-origin icon proxy", () => {
    const urls = resolveProxiedBlogIconUrls({
      url: "https://blog.example.com/posts/1",
      domain: "blog.example.com",
      iconUrl: "https://cdn.example.com/icon.png",
    });

    expect(urls[0]).toBe("/api/icons/proxy?url=https%3A%2F%2Fcdn.example.com%2Ficon.png");
    expect(urls.every((url) => url.startsWith("/api/icons/proxy?url="))).toBe(true);
  });
});
