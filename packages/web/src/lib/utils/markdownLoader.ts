// Cache for markdown files to avoid repeated network requests
const markdownCache = new Map<string, string>();

/**
 * Load markdown content from static/docs folder
 * @param docName - Name of the markdown file (without .md extension)
 * @returns Promise with markdown content
 */
export async function loadMarkdown(docName: string): Promise<string> {
  // Check cache first for better performance
  if (markdownCache.has(docName)) {
    return markdownCache.get(docName)!;
  }

  try {
    // Files in static/ are accessible at root URL
    const response = await fetch(`/docs/${docName}.md`, {
      headers: {
        'Cache-Control': 'max-age=3600' // Cache for 1 hour
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to load ${docName}.md: ${response.status} ${response.statusText}`);
    }

    const markdown = await response.text();
    
    // Cache the result
    markdownCache.set(docName, markdown);
    
    return markdown;
  } catch (error) {
    console.error('Error loading markdown:', error);
    
    // Return a helpful error message
    return `# Error Loading Documentation

We couldn't load the "${docName}" documentation.

**Possible reasons:**
- The file \`static/docs/${docName}.md\` doesn't exist
- There's a network issue
- The file contains invalid content

**Error details:** \`${error instanceof Error ? error.message : 'Unknown error'}\``;
  }
}

/**
 * Document name mappings for cleaner code
 */
export const documentNames = {
  'api-docs': 'api',
  'about': 'about',
  'quick-start': 'quick-start',
  'changelog': 'changelog',
  'contributing': 'contributing'
} as const;

export type DocKey = keyof typeof documentNames;

/**
 * Get all available document names (for dynamic loading)
 */
export async function getAvailableDocs(): Promise<string[]> {
  // In a real app, you might fetch an index file or use a predefined list
  return Object.keys(documentNames);
}