export interface GraphNode {
  id: string;
  label: string;
  group: string;
  size: number;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
  metadata: {
    totalNodes: number;
    totalEdges: number;
    orphans: string[];
    generatedAt: string;
  };
}

export interface SearchDoc {
  id: string;
  title: string;
  group: string;
  tags: string[];
  headings: string[];
  body: string;
}

const graphCache = new Map<string, GraphData>();
const indexCache = new Map<string, Record<string, string>>();
const searchCache = new Map<string, { documents: SearchDoc[] }>();

async function fetchData<T>(url: string): Promise<T> {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function getGraphData(wiki: string): Promise<GraphData> {
  const cached = graphCache.get(wiki);
  if (cached) return cached;

  const data = await fetchData<GraphData>(`/data/${encodeURIComponent(wiki)}/graph.json`);
  graphCache.set(wiki, data);
  return data;
}

export async function getWikiIndex(wiki: string): Promise<Record<string, string>> {
  const cached = indexCache.get(wiki);
  if (cached) return cached;

  const data = await fetchData<Record<string, string>>(
    `/data/${encodeURIComponent(wiki)}/index.json`
  );
  indexCache.set(wiki, data);
  return data;
}

export async function getSearchData(wiki: string): Promise<{ documents: SearchDoc[] }> {
  const cached = searchCache.get(wiki);
  if (cached) return cached;

  const data = await fetchData<{ documents: SearchDoc[] }>(
    `/data/${encodeURIComponent(wiki)}/search.json`
  );
  searchCache.set(wiki, data);
  return data;
}
