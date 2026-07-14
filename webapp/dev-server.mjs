#!/usr/bin/env node
/**
 * Local development server for the Wiki Platform web app.
 *
 * Implements the same /api/* and /data/* contract as the AWS backend
 * but reads from local filesystem directories instead of CodeCommit.
 *
 * Usage:
 *   node dev-server.mjs [--port 3000] [--wikis-dir ./wikis]
 *
 * Wiki directories are discovered under --wikis-dir. Each subdirectory
 * is treated as a wiki (e.g., ./wikis/llm-wiki/, ./wikis/security-playbook/).
 *
 * Alternatively, set WIKI_DIRS as a colon-separated list of paths:
 *   WIKI_DIRS=/path/to/wiki1:/path/to/wiki2 node dev-server.mjs
 */

import { createServer } from 'http';
import { readFileSync, readdirSync, statSync, existsSync } from 'fs';
import { join, relative, basename, extname, resolve, dirname } from 'path';
import { execSync } from 'child_process';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// --- Config ---
const args = process.argv.slice(2);
const PORT = getArg('--port', '3000');
const WIKIS_DIR = getArg('--wikis-dir', join(process.cwd(), 'wikis'));
const WIKI_DIRS_ENV = process.env.WIKI_DIRS; // colon-separated override

function getArg(name, defaultVal) {
  const idx = args.indexOf(name);
  return idx !== -1 && args[idx + 1] ? args[idx + 1] : defaultVal;
}

// --- Wiki Discovery ---

function discoverWikis() {
  const wikis = [];

  if (WIKI_DIRS_ENV) {
    // Explicit list: WIKI_DIRS=/path/to/wiki1:/path/to/wiki2
    for (const dir of WIKI_DIRS_ENV.split(':').filter(Boolean)) {
      const absDir = resolve(dir);
      if (existsSync(absDir) && statSync(absDir).isDirectory()) {
        const name = basename(absDir);
        wikis.push({ name, path: absDir });
      }
    }
  } else {
    // Auto-discover: each subdirectory of WIKIS_DIR is a wiki
    if (existsSync(WIKIS_DIR) && statSync(WIKIS_DIR).isDirectory()) {
      for (const entry of readdirSync(WIKIS_DIR)) {
        const fullPath = join(WIKIS_DIR, entry);
        if (statSync(fullPath).isDirectory() && !entry.startsWith('.')) {
          wikis.push({ name: entry, path: fullPath });
        }
      }
    }
  }

  return wikis;
}

function getWikiPath(wikiName) {
  const wikis = discoverWikis();
  const wiki = wikis.find(w => w.name === wikiName);
  return wiki ? wiki.path : null;
}

// --- File System Helpers ---

function listDirectory(dirPath, basePath) {
  const files = [];
  const subFolders = [];

  if (!existsSync(dirPath)) return { files, subFolders };

  for (const entry of readdirSync(dirPath)) {
    if (entry.startsWith('.')) continue;
    const fullPath = join(dirPath, entry);
    const relPath = relative(basePath, fullPath);
    const stat = statSync(fullPath);

    if (stat.isDirectory()) {
      subFolders.push({ path: relPath });
    } else {
      files.push({ path: relPath, size: stat.size });
    }
  }

  return { files, subFolders };
}

function getAllMarkdownFiles(wikiPath, dir = wikiPath) {
  const results = [];
  if (!existsSync(dir)) return results;

  for (const entry of readdirSync(dir)) {
    if (entry.startsWith('.') || entry === 'raw' || entry === '_archive') continue;
    const fullPath = join(dir, entry);
    const stat = statSync(fullPath);

    if (stat.isDirectory()) {
      results.push(...getAllMarkdownFiles(wikiPath, fullPath));
    } else if (extname(entry) === '.md') {
      const relPath = relative(wikiPath, fullPath);
      try {
        const content = readFileSync(fullPath, 'utf-8');
        results.push({ path: relPath, content });
      } catch { /* skip unreadable */ }
    }
  }
  return results;
}

// --- Git Helpers (optional, for commits/branches) ---

function gitAvailable(wikiPath) {
  try {
    execSync('git rev-parse --is-inside-work-tree', { cwd: wikiPath, stdio: 'pipe' });
    return true;
  } catch { return false; }
}

function getGitBranch(wikiPath) {
  try {
    return execSync('git rev-parse --abbrev-ref HEAD', { cwd: wikiPath, encoding: 'utf-8' }).trim();
  } catch { return 'main'; }
}

function getGitCommitId(wikiPath) {
  try {
    return execSync('git rev-parse HEAD', { cwd: wikiPath, encoding: 'utf-8' }).trim();
  } catch { return 'local'; }
}

function getGitBranches(wikiPath) {
  try {
    const output = execSync('git branch --format="%(refname:short)"', { cwd: wikiPath, encoding: 'utf-8' });
    return output.trim().split('\n').filter(Boolean);
  } catch { return ['main']; }
}

function getGitCommits(wikiPath, limit = 10) {
  try {
    const format = '%H|%an|%ae|%s|%aI';
    const output = execSync(`git log -${limit} --format="${format}"`, { cwd: wikiPath, encoding: 'utf-8' });
    return output.trim().split('\n').filter(Boolean).map(line => {
      const [commitId, author, email, message, date] = line.split('|');
      return { commitId, author, email, message, date };
    });
  } catch { return []; }
}

// --- Index Builder (same logic as wiki-indexer Lambda) ---

function buildIndexData(wikiPath) {
  const files = getAllMarkdownFiles(wikiPath);
  const nodes = [];
  const edges = [];
  const slugIndex = {};
  const searchDocs = [];

  for (const { path: filePath, content } of files) {
    const slug = basename(filePath, '.md');
    slugIndex[slug] = filePath;

    const title = extractTitle(content) || slug;
    const group = filePath.includes('/') ? filePath.split('/')[0] : 'root';
    const tags = extractTags(content);
    const headings = extractHeadings(content);
    const body = stripMarkdown(content).slice(0, 500);
    const wikilinks = findWikilinks(content);

    nodes.push({ id: filePath, label: title, group, size: 1 });
    for (const link of wikilinks) {
      edges.push({ source: filePath, targetSlug: link });
    }
    searchDocs.push({ id: filePath, title, group, tags, headings, body });
  }

  // Resolve edges
  const resolvedEdges = [];
  for (const edge of edges) {
    const target = slugIndex[edge.targetSlug];
    if (target) {
      resolvedEdges.push({ source: edge.source, target });
    }
  }

  // Compute sizes (inbound link count)
  const inbound = {};
  for (const e of resolvedEdges) {
    inbound[e.target] = (inbound[e.target] || 0) + 1;
  }
  for (const node of nodes) {
    node.size = (inbound[node.id] || 0) + 1;
  }

  const orphans = nodes.filter(n => !inbound[n.id]).map(n => n.id);
  const mostConnected = nodes.reduce((a, b) => a.size > b.size ? a : b, nodes[0])?.id || '';

  const graph = {
    nodes,
    edges: resolvedEdges,
    metadata: {
      totalNodes: nodes.length,
      totalEdges: resolvedEdges.length,
      orphans,
      mostConnected,
      generatedAt: new Date().toISOString(),
      commitId: getGitCommitId(wikiPath),
    },
  };

  const search = { documents: searchDocs, generatedAt: new Date().toISOString() };

  return { graph, index: slugIndex, search };
}

function extractTitle(content) {
  const match = content.match(/^#\s+(.+)$/m);
  return match ? match[1].trim() : null;
}

function extractTags(content) {
  const fmMatch = content.match(/^---\n([\s\S]*?)\n---/);
  if (!fmMatch) return [];
  const tagsMatch = fmMatch[1].match(/tags:\s*\[([^\]]*)\]/);
  if (tagsMatch) return tagsMatch[1].split(',').map(t => t.trim().replace(/['"]/g, '')).filter(Boolean);
  return [];
}

function extractHeadings(content) {
  const matches = content.matchAll(/^#{2,3}\s+(.+)$/gm);
  return [...matches].map(m => m[1].trim());
}

function stripMarkdown(content) {
  return content
    .replace(/^---\n[\s\S]*?\n---\n?/, '')   // front-matter
    .replace(/```[\s\S]*?```/g, '')           // code blocks
    .replace(/\[\[([^\]]+)\]\]/g, '$1')       // wikilinks
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')  // links
    .replace(/[#*>`~_\-|]/g, ' ')            // markers
    .replace(/\s+/g, ' ')
    .trim();
}

function findWikilinks(content) {
  const matches = content.matchAll(/\[\[([^\]]+)\]\]/g);
  return [...matches].map(m => m[1].trim());
}

// --- HTTP Router ---

function json(res, status, body) {
  res.writeHead(status, { 'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*' });
  res.end(JSON.stringify(body));
}

function handleRequest(req, res) {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  const path = url.pathname;
  const params = Object.fromEntries(url.searchParams);

  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
      'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    });
    return res.end();
  }

  try {
    // --- /data/{wiki}/*.json (pre-computed static data) ---
    if (path.startsWith('/data/')) {
      const parts = path.replace('/data/', '').split('/');
      const wikiName = parts[0];
      const fileName = parts[1];
      const wikiPath = getWikiPath(wikiName);

      if (!wikiPath) return json(res, 404, { error: `Wiki '${wikiName}' not found` });

      const data = buildIndexData(wikiPath);

      if (fileName === 'graph.json') return json(res, 200, data.graph);
      if (fileName === 'index.json') return json(res, 200, data.index);
      if (fileName === 'search.json') return json(res, 200, data.search);
      return json(res, 404, { error: 'Unknown data file' });
    }

    // --- /api/wikis ---
    if (path === '/api/wikis' && req.method === 'GET') {
      const wikis = discoverWikis().map(w => ({
        name: w.name,
        description: `Local wiki at ${w.path}`,
        owner: 'local',
        repositoryName: `wiki-${w.name}`,
        cloneUrlHttp: w.path,
        createdAt: new Date().toISOString(),
      }));
      return json(res, 200, wikis);
    }

    if (path === '/api/wikis' && req.method === 'POST') {
      // Local mode: just acknowledge (can't really create repos locally)
      return json(res, 201, { message: 'Wiki creation is not supported in local mode. Create a directory instead.' });
    }

    // --- All other /api/* routes need a wiki param ---
    const wikiName = params.wiki;
    if (!wikiName) return json(res, 400, { error: 'Missing wiki parameter' });

    const wikiPath = getWikiPath(wikiName);
    if (!wikiPath) return json(res, 404, { error: `Wiki '${wikiName}' not found` });

    // /api/tree
    if (path === '/api/tree') {
      const requestedPath = params.path || '/';
      const dirPath = join(wikiPath, requestedPath === '/' ? '' : requestedPath);
      const { files, subFolders } = listDirectory(dirPath, wikiPath);
      return json(res, 200, { path: requestedPath, files, subFolders });
    }

    // /api/file
    if (path === '/api/file') {
      const filePath = params.path;
      if (!filePath) return json(res, 400, { error: 'Missing path parameter' });
      const fullPath = join(wikiPath, filePath.startsWith('/') ? filePath.slice(1) : filePath);
      if (!existsSync(fullPath)) return json(res, 404, { error: 'File not found' });
      const content = readFileSync(fullPath, 'utf-8');
      const size = statSync(fullPath).size;
      return json(res, 200, { path: filePath, content, size });
    }

    // /api/branch
    if (path === '/api/branch') {
      const branch = getGitBranch(wikiPath);
      const commitId = getGitCommitId(wikiPath);
      return json(res, 200, { branch, commitId });
    }

    // /api/branches
    if (path === '/api/branches') {
      const branches = getGitBranches(wikiPath);
      return json(res, 200, { branches });
    }

    // /api/commits
    if (path === '/api/commits') {
      const limit = parseInt(params.limit || '10', 10);
      const commits = getGitCommits(wikiPath, limit);
      return json(res, 200, { commits });
    }

    // /api/diff
    if (path === '/api/diff') {
      // Local mode: return empty diff (would need git diff implementation)
      return json(res, 200, { differences: [], message: 'Diff not fully supported in local mode' });
    }

    return json(res, 404, { error: 'Not found' });

  } catch (err) {
    console.error('Error handling request:', err);
    return json(res, 500, { error: err.message });
  }
}

// --- Start Server ---

const server = createServer(handleRequest);
server.listen(parseInt(PORT, 10), () => {
  const wikis = discoverWikis();
  console.log(`\n📚 Wiki dev server running at http://localhost:${PORT}`);
  console.log(`   Wikis directory: ${WIKI_DIRS_ENV || WIKIS_DIR}`);
  console.log(`   Discovered ${wikis.length} wiki(s):`);
  for (const w of wikis) {
    console.log(`     - ${w.name} → ${w.path}`);
  }
  console.log(`\n   Start the React app: cd webapp && npm run dev\n`);
});
