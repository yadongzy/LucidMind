/**
 * Markdown rendering — marked + DOMPurify + code highlight
 */
import { Marked } from "marked";
import DOMPurify from "dompurify";

const marked = new Marked({
  breaks: true,
  gfm: true,
  renderer: {
    code({ text, lang }) {
      const escaped = text || "";
      const language = lang || "";
      const langLabel = language ? `<span class="code-lang">${language}</span>` : "";
      return `<div class="code-block">${langLabel}<pre><code class="lang-${language}">${escapeHtml(escaped)}</code></pre></div>`;
    },
  },
});

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function renderMarkdown(text) {
  if (!text) return "";
  const raw = marked.parse(text);
  return DOMPurify.sanitize(raw, { ADD_TAGS: ["span"], ADD_ATTR: ["class"] });
}
