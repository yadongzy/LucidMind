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
    link({ href, title, text }) {
      const cleanHref = (href || "").replace(/[）)]+$/, "");
      const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
      if (cleanHref.startsWith("file://")) {
        const filePath = decodeURIComponent(cleanHref.replace("file://", ""));
        return `<a href="#" class="file-link" data-path="${escapeHtml(filePath)}" title="点击复制路径"${titleAttr}>📁 ${text || filePath}</a>`;
      }
      return `<a href="${cleanHref}" target="_blank" rel="noopener noreferrer"${titleAttr}>${text || cleanHref}</a>`;
    },
  },
});

function escapeHtml(str) {
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function preprocessLinks(text) {
  return text
    .replace(/(https?:\/\/[^\s）)]+)[）)]/g, "$1 ）")
    .replace(/(www\.[^\s）)]+)[）)]/g, "$1 ）")
    .replace(/(?:^|[\s，。、：:（(])(\/(?:Users|home|private|tmp|var|etc|opt|usr)\/[^\s，。、：）)）]*[^\s，。、：）)\]）])/gm, (match, path) => {
      const prefix = match.slice(0, match.length - path.length);
      return `${prefix}[${path}](file://${encodeURI(path)})`;
    });
}

export function renderMarkdown(text) {
  if (!text) return "";
  const processed = preprocessLinks(text);
  const raw = marked.parse(processed);
  return DOMPurify.sanitize(raw, { ADD_TAGS: ["span"], ADD_ATTR: ["class", "target", "rel", "data-path"] });
}
