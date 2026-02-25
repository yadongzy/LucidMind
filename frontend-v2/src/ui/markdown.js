/**
 * Markdown rendering — marked + DOMPurify
 */
import { Marked } from "marked";
import DOMPurify from "dompurify";

const marked = new Marked({
  breaks: true,
  gfm: true,
});

export function renderMarkdown(text) {
  if (!text) return "";
  const raw = marked.parse(text);
  return DOMPurify.sanitize(raw);
}
