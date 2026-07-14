export interface Wiki {
  name: string;
  description: string;
  owner: string;
  repositoryName: string;
  cloneUrlHttp: string;
  createdAt: string;
}

export interface TreeEntry {
  path: string;
  size?: number;
}

export interface TreeResult {
  path: string;
  files: TreeEntry[];
  subFolders: TreeEntry[];
}

export interface FileResult {
  path: string;
  content: string;
  size: number;
}

export interface BranchResult {
  branch: string;
  commitId: string;
}

export interface Commit {
  commitId: string;
  author: string;
  email: string;
  message: string;
  date: string;
}

export interface DiffEntry {
  changeType: string;
  beforePath?: string;
  afterPath?: string;
}

const TOKEN_KEY = 'auth_token';

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const token = localStorage.getItem(TOKEN_KEY);

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => ({ message: response.statusText }));
    throw new Error(body.message || body.error || `Request failed: ${response.status}`);
  }

  return response.json();
}

export function getWikis(): Promise<Wiki[]> {
  return apiFetch<Wiki[]>('/wikis');
}

export function getTree(wiki: string, path?: string): Promise<TreeResult> {
  const params = new URLSearchParams({ wiki });
  if (path) params.set('path', path);
  return apiFetch<TreeResult>(`/tree?${params.toString()}`);
}

export function getFile(wiki: string, path: string): Promise<FileResult> {
  const params = new URLSearchParams({ wiki, path });
  return apiFetch<FileResult>(`/file?${params.toString()}`);
}

export function getBranch(wiki: string): Promise<BranchResult> {
  return apiFetch<BranchResult>(`/branch?wiki=${encodeURIComponent(wiki)}`);
}

export function getBranches(wiki: string): Promise<{ branches: string[] }> {
  return apiFetch<{ branches: string[] }>(`/branches?wiki=${encodeURIComponent(wiki)}`);
}

export function getCommits(wiki: string, limit?: number): Promise<{ commits: Commit[] }> {
  const params = new URLSearchParams({ wiki });
  if (limit) params.set('limit', String(limit));
  return apiFetch<{ commits: Commit[] }>(`/commits?${params.toString()}`);
}

export function getDiff(
  wiki: string,
  from: string,
  to: string
): Promise<{ differences: DiffEntry[] }> {
  const params = new URLSearchParams({ wiki, from, to });
  return apiFetch<{ differences: DiffEntry[] }>(`/diff?${params.toString()}`);
}

export function createWiki(
  name: string,
  description: string,
  owner: string
): Promise<Wiki> {
  return apiFetch<Wiki>('/wikis', {
    method: 'POST',
    body: JSON.stringify({ name, description, owner }),
  });
}
