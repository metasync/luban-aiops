// Markdown rendering for agent replies. Direct port of the legacy
// renderMarkdown: escape-first, regex-based block conversion. Output is
// injected as HTML, so every source character passes through the escape
// step (including quotes, which guard attribute contexts) before markup
// is introduced, and links are restricted to http(s) targets.
// One block of consecutive list lines becomes one (possibly nested)
// list. The legacy column-0-only passes dropped indented sub-bullets to
// literal "- text" paragraphs (v0.18.1 live-check finding) and never
// wrapped ordered items in <ol>, so numbered lists lost their markers.
// An indented item now nests inside the previous item (two spaces per
// level, a tab counts as one level; over-indentation clamps instead of
// opening empty wrappers), and each level's container follows its first
// item's marker. Contents are already escaped by the time this runs.
interface ListLevel {
  ordered: boolean;
  minIndent: number;
  html: string;
  itemOpen: boolean;
}

function renderListBlock(block: string): string {
  const stack: ListLevel[] = [];
  let result = "";

  const closeItem = (level: ListLevel) => {
    if (level.itemOpen) {
      level.html += "</li>";
      level.itemOpen = false;
    }
  };

  const closeLevel = () => {
    const level = stack.pop();
    if (!level) return;
    closeItem(level);
    const tag = level.ordered ? "ol" : "ul";
    const wrapped = `<${tag}>${level.html}</${tag}>`;
    const parent = stack[stack.length - 1];
    if (parent) {
      // A nested list lives inside the parent item it indented under;
      // the parent item stays open so further siblings or nested lists
      // append inside it until something closes it.
      parent.html += wrapped;
    } else {
      result = wrapped;
    }
  };

  for (const line of block.split("\n")) {
    const match = /^([ \t]*)([-*]|\d+\.)[ \t]+(.+)$/.exec(line);
    if (!match) continue;
    const indent = match[1].replace(/\t/g, "  ").length;
    // Each level remembers the indent its first item carried, so equally
    // indented items stay siblings even when the whole block (or a whole
    // sub-list) sits indented under a plain paragraph.
    while (stack.length > 0 && stack[stack.length - 1].minIndent > indent) {
      closeLevel();
    }
    const top = stack[stack.length - 1];
    const ordered = /^\d+\.$/.test(match[2]);
    let level: ListLevel;
    if (!top || indent > top.minIndent) {
      // Deeper: nest under the still-open parent item.
      level = { ordered, minIndent: indent, html: "", itemOpen: false };
      stack.push(level);
    } else {
      level = top;
      closeItem(level);
    }
    level.html += `<li>${match[3]}`;
    level.itemOpen = true;
  }
  while (stack.length > 0) closeLevel();
  return result;
}

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

  // Fence code before any further pass: fenced blocks and inline code
  // spans are stashed behind sentinels and restored at the end, so
  // header/emphasis/list/table passes never rewrite code content. Two
  // classes of corruption this prevents: underscore pairs inside tool
  // identifiers (the model-visible sanitized names — k8s_delete_pod —
  // consumed by the emphasis passes, rendering "k8sdeletepod") and
  // heading markers inside fenced blocks becoming real <h*> tags.
  // (v0.27.3 live-test finding.) \u0000 is stripped from the input so
  // the sentinel cannot collide with source text.
  html = html.replace(/\u0000/g, "");
  const fencedBlocks: string[] = [];
  const codeSpans: string[] = [];

  // Code blocks (``` ... ```).
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang: string, code: string) => {
    fencedBlocks.push(`<pre><code class="lang-${lang}">${code.trim()}</code></pre>`);
    return `\u0000F${fencedBlocks.length - 1}\u0000`;
  });

  // Inline code.
  html = html.replace(/`([^`]+)`/g, (_m, code: string) => {
    codeSpans.push(`<code>${code}</code>`);
    return `\u0000S${codeSpans.length - 1}\u0000`;
  });

  // Headers.
  html = html.replace(/^######\s+(.+)$/gm, "<h6>$1</h6>");
  html = html.replace(/^#####\s+(.+)$/gm, "<h5>$1</h5>");
  html = html.replace(/^####\s+(.+)$/gm, "<h4>$1</h4>");
  html = html.replace(/^###\s+(.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^##\s+(.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^#\s+(.+)$/gm, "<h1>$1</h1>");

  // Horizontal rules.
  html = html.replace(/^---+$/gm, "<hr>");

  // Bold and italic. The underscore passes require non-word context on
  // the outer edges (CommonMark flanking): intra-word underscores stay
  // literal, so identifiers like k8s_delete_pod keep their separators.
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/(?<!\w)__(.+?)__(?!\w)/g, "<strong>$1</strong>");
  html = html.replace(/(?<!\w)_([^_]+?)_(?!\w)/g, "<em>$1</em>");

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

  // Lists: unordered and ordered, with nesting (see renderListBlock).
  html = html.replace(/(?:^[ \t]*(?:[-*]|\d+\.)[ \t]+.+\n?)+/gm, renderListBlock);

  // Tables. A block of consecutive `| … |` lines becomes one <table>: the
  // first non-separator row is the header (<th>, inside <thead>), the rest
  // form the body. Emitting the whole block in one pass keeps header and
  // body in a single table even though the `---` separator line is
  // dropped (an earlier line-by-line port split them into two stacked
  // tables, which rendered as a disconnected header).
  html = html.replace(/(?:^\|.+\|\n?)+/gm, (block) => {
    const rows = block.split("\n").filter((line) => line.trim() !== "");
    const parseCells = (line: string) =>
      line.replace(/^\|/, "").replace(/\|$/, "").split("|").map((cell) => cell.trim());
    const isSeparator = (cells: string[]) =>
      cells.length > 0 && cells.every((cell) => /^:?-+:?$/.test(cell));
    const renderRow = (cells: string[], tag: "th" | "td") =>
      "<tr>" + cells.map((cell) => `<${tag}>${cell}</${tag}>`).join("") + "</tr>";
    let head = "";
    const body: string[] = [];
    for (const row of rows) {
      const cells = parseCells(row);
      if (isSeparator(cells)) continue;
      if (!head) head = renderRow(cells, "th");
      else body.push(renderRow(cells, "td"));
    }
    if (!head) return "";
    return `<table><thead>${head}</thead><tbody>${body.join("")}</tbody></table>`;
  });

  // Paragraphs: wrap remaining lines not already in block elements.
  // Lines opening with a code sentinel stay unwrapped so restored
  // fenced blocks are never nested inside <p>.
  html = html.replace(
    /^(?!<[hupoltbd]|<\/|<hr|<blockquote|<pre|<code|\u0000)(.+)$/gm,
    "<p>$1</p>",
  );

  // Clean up empty paragraphs.
  html = html.replace(/<p>\s*<\/p>/g, "");

  // Restore the fenced code, spans first: no placeholder nests inside
  // another (fenced content was stashed before the span pass), and the
  // restored content is already escaped.
  html = html.replace(/\u0000S(\d+)\u0000/g, (_m, index: string) => codeSpans[Number(index)]);
  html = html.replace(/\u0000F(\d+)\u0000/g, (_m, index: string) => fencedBlocks[Number(index)]);

  return html;
}
