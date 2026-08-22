// Markdown rendering for agent replies. Direct port of the legacy
// renderMarkdown: escape-first, regex-based block conversion. Output is
// injected as HTML, so every source character passes through the escape
// step (including quotes, which guard attribute contexts) before markup
// is introduced, and links are restricted to http(s) targets.
export function renderMarkdown(text: string): string {
  if (!text) return "";
  let html = text;

  // Escape HTML first.
  html = html
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");

  // Code blocks (``` ... ```).
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang: string, code: string) => {
    return `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`;
  });

  // Inline code.
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  // Headers.
  html = html.replace(/^######\s+(.+)$/gm, "<h6>$1</h6>");
  html = html.replace(/^#####\s+(.+)$/gm, "<h5>$1</h5>");
  html = html.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");

  // Horizontal rules.
  html = html.replace(/^---+$/gm, "<hr>");

  // Bold and italic.
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/__(.+?)__/g, "<strong>$1</strong>");
  html = html.replace(/_(.+?)_/g, "<em>$1</em>");

  // Strikethrough.
  html = html.replace(/~~(.+?)~~/g, "<del>$1</del>");

  // Links — http(s) targets only. Agent replies and incident summaries
  // derive from attacker-influenceable input, so anything else
  // (javascript:, data:, vbscript:, …) renders as plain text instead of
  // a clickable URL.
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_m, label: string, href: string) =>
    /^https?:\/\//i.test(href)
      ? `<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`
      : label,
  );

  // Blockquotes.
  html = html.replace(/^&gt;\s+(.+)$/gm, "<blockquote>$1</blockquote>");

  // Unordered lists.
  html = html.replace(/^[*-]\s+(.+)$/gm, "<li>$1</li>");
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

  // Ordered lists.
  html = html.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");

  // Tables.
  html = html.replace(/^\|(.+)\|$/gm, (_match, content: string) => {
    const cells = content.split("|").map((cell) => cell.trim());
    if (cells.every((cell) => /^[-:]+$/.test(cell))) return ""; // separator
    return (
      "<tr>" + cells.map((cell) => `<td>${cell}</td>`).join("") + "</tr>"
    );
  });
  html = html.replace(/((?:<tr>.*<\/tr>\n?)+)/g, "<table>$1</table>");

  // Paragraphs: wrap remaining lines not already in block elements.
  html = html.replace(
    /^(?!<[hupoltbd]|<\/|<hr|<blockquote|<pre|<code)(.+)$/gm,
    "<p>$1</p>",
  );

  // Clean up empty paragraphs.
  html = html.replace(/<p>\s*<\/p>/g, "");

  return html;
}
