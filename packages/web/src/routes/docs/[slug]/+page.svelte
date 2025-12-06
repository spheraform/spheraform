<script lang="ts">
  export let data;
</script>

<div class="markdown">
  <h1>{data.title}</h1>

  {@html data.html}
</div>

<style>
.markdown {
  line-height: 1.8;
  max-width: 900px;
  color: #e5e7eb;
}

.markdown :global(h1) {
  font-size: 2.5em;
  font-weight: 700;
  margin-bottom: 0.5em;
  color: #f1f5f9;
  border-bottom: 2px solid #1e293b;
  padding-bottom: 0.3em;
}

.markdown :global(h2) {
  font-size: 2em;
  font-weight: 600;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  color: #f1f5f9;
  border-bottom: 1px solid #1e293b;
  padding-bottom: 0.3em;
}

.markdown :global(h3) {
  font-size: 1.5em;
  font-weight: 600;
  margin-top: 1.2em;
  margin-bottom: 0.5em;
  color: #f1f5f9;
}

.markdown :global(h4) {
  font-size: 1.25em;
  font-weight: 600;
  margin-top: 1em;
  margin-bottom: 0.5em;
  color: #cbd5e1;
}

.markdown :global(p) {
  margin-bottom: 1em;
  color: #cbd5e1;
}

.markdown :global(ul), .markdown :global(ol) {
  margin-bottom: 1em;
  padding-left: 1.5em;
  color: #cbd5e1;
}

.markdown :global(li) {
  margin-bottom: 0.5em;
}

.markdown :global(pre) {
  background: #020617;
  padding: 16px;
  border-radius: 8px;
  overflow-x: auto;
  margin-bottom: 1em;
  border: 1px solid #1e293b;
}

.markdown :global(code) {
  font-family: 'Courier New', Courier, monospace;
  font-size: 0.9em;
}

.markdown :global(pre code) {
  background: transparent;
  padding: 0;
  border-radius: 0;
}

.markdown :global(:not(pre) > code) {
  background: #1e293b;
  padding: 3px 6px;
  border-radius: 4px;
  color: #e879f9;
}

.markdown :global(a) {
  color: #60a5fa;
  text-decoration: none;
  transition: color 0.2s;
}

.markdown :global(a:hover) {
  color: #93c5fd;
  text-decoration: underline;
}

.markdown :global(blockquote) {
  border-left: 4px solid #3b82f6;
  padding-left: 16px;
  margin-left: 0;
  margin-bottom: 1em;
  color: #a5b4fc;
  font-style: italic;
}

.markdown :global(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1em;
  font-size: 0.95em;
}

.markdown :global(th), .markdown :global(td) {
  border: 1px solid #334155;
  padding: 10px 12px;
  text-align: left;
}

.markdown :global(th) {
  background: #1e293b;
  color: #f1f5f9;
  font-weight: 600;
}

.markdown :global(tr:hover) {
  background: rgba(30, 41, 59, 0.3);
}

.markdown :global(img) {
  max-width: 100%;
  height: auto;
  border-radius: 8px;
  margin: 1em 0;
}

.markdown :global(hr) {
  border: none;
  border-top: 1px solid #1e293b;
  margin: 2em 0;
}
</style>
