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
      const langLabel = "";
      const copyBtn = `<button class="code-copy-btn" title="复制代码">复制</button>`;
      return `<div class="code-block">${langLabel}${copyBtn}<pre><code class="lang-${language}">${escapeHtml(escaped)}</code></pre></div>`;
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
    })
    // 自动链接纯文本 URL（不在 markdown 链接内的）
    .replace(/(?<!\]\(|"|'|\[)(https?:\/\/[^\s<>\[\]()，。、；：！？）)]+)/g, '[$1]($1)');
}

export function renderMarkdown(text) {
  if (!text) return "";
  const processed = preprocessLinks(text);
  const raw = marked.parse(processed);
  return DOMPurify.sanitize(raw, { ADD_TAGS: ["span", "button"], ADD_ATTR: ["class", "target", "rel", "data-path", "title", "src", "alt"] });
}

// 全局事件委托：代码块复制按钮
document.addEventListener("click", (e) => {
  const btn = e.target.closest(".code-copy-btn");
  if (!btn) return;
  const block = btn.closest(".code-block");
  if (!block) return;
  const code = block.querySelector("code");
  if (!code) return;
  navigator.clipboard.writeText(code.textContent).then(() => {
    btn.textContent = "✓ 已复制";
    btn.classList.add("copied");
    setTimeout(() => { btn.textContent = "复制"; btn.classList.remove("copied"); }, 1500);
  }).catch(() => {
    // fallback for non-HTTPS
    const ta = document.createElement("textarea");
    ta.value = code.textContent;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    document.body.removeChild(ta);
    btn.textContent = "✓ 已复制";
    setTimeout(() => { btn.textContent = "复制"; }, 1500);
  });
});
