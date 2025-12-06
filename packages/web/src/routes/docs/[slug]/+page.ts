import { marked } from 'marked';
import hljs from 'highlight.js';
import type { PageLoad } from './$types';
import { error } from '@sveltejs/kit';

// enable highlight.js for code blocks
marked.setOptions({
  highlight(code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  }
});

export const load: PageLoad = async ({ fetch, params }) => {
  const slug = params.slug;

  const res = await fetch(`/docs/${slug}.md`);

  if (!res.ok) {
    throw error(404, 'Document not found');
  }

  const md = await res.text();

  return {
    title: slug.replace(/-/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
    html: marked.parse(md),
    slug
  };
};
