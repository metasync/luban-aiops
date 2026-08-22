// Markdown renderer smoke tests (legacy renderMarkdown parity): the
// escape-first contract is the security-critical part.
import { describe, expect, it } from "vitest";
import { renderMarkdown } from "../markdown";

describe("renderMarkdown", () => {
  it("escapes HTML before introducing markup", () => {
    const html = renderMarkdown("<script>alert('x')</script>");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("renders bold and inline code", () => {
    const html = renderMarkdown("**bold** and `code`");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<code>code</code>");
  });

  it("renders fenced code blocks", () => {
    const html = renderMarkdown("```bash\nkubectl get pods\n```");
    expect(html).toContain('<pre><code class="lang-bash">kubectl get pods</code></pre>');
  });

  it("adds rel=noreferrer to links", () => {
    const html = renderMarkdown("[docs](https://example.com)");
    expect(html).toContain('rel="noreferrer"');
    expect(html).toContain('href="https://example.com"');
  });

  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });
});
