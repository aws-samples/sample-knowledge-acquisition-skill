import { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import SegmentedControl from '@cloudscape-design/components/segmented-control';
import Table from '@cloudscape-design/components/table';
import TextFilter from '@cloudscape-design/components/text-filter';
import Pagination from '@cloudscape-design/components/pagination';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import Badge from '@cloudscape-design/components/badge';
import { useCollection } from '@cloudscape-design/collection-hooks';
import ForceGraph2D from 'react-force-graph-2d';
import { getWikis } from '../api/client';
import { getGraphData, type GraphData, type GraphNode, type GraphEdge } from '../api/data';

const GROUP_COLORS: Record<string, string> = {
  concepts: '#0972d3',
  entities: '#037f0c',
  comparisons: '#ec7211',
  queries: '#9469d6',
  errors: '#d13212',
};

interface ForceGraphNode {
  id: string;
  name: string;
  group: string;
  val: number;
  color: string;
  x?: number;
  y?: number;
}

interface ForceGraphLink {
  source: string;
  target: string;
}

export default function GraphPage({ wikiName }: { wikiName?: string }) {
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<string>('graph');
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    async function load() {
      try {
        const wikis = await getWikis();
        const wiki = wikiName
          ? wikis.find(w => w.name === wikiName) || wikis[0]
          : wikis[0];
        if (wiki) {
          const data = await getGraphData(wiki.name);
          setGraphData(data);
        }
      } catch (err) {
        console.error('Failed to load graph:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  useEffect(() => {
    if (!containerRef.current) return;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: Math.max(entry.contentRect.height, 500),
        });
      }
    });
    observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  const handleNodeClick = useCallback((node: ForceGraphNode) => {
    // node.id is like "concepts/experiment-idea-storage.md" — extract group and slug
    const parts = node.id.replace(/\.md$/, '').split('/');
    const slug = parts.pop() || node.id;
    const group = parts[0] || node.group;
    const base = wikiName ? `/w/${wikiName}` : '';
    navigate(`${base}/page/${group}/${slug}`);
  }, [navigate, wikiName]);

  const forceGraphData = graphData ? {
    nodes: graphData.nodes.map((n: GraphNode): ForceGraphNode => ({
      id: n.id,
      name: n.label,
      group: n.group,
      val: n.size * 3,
      color: GROUP_COLORS[n.group] || '#687078',
    })),
    links: graphData.edges.map((e: GraphEdge): ForceGraphLink => ({
      source: e.source,
      target: e.target,
    })),
  } : { nodes: [], links: [] };

  const edgeItems = graphData?.edges || [];

  const { items: edgeCollectionItems, filterProps, paginationProps, collectionProps } = useCollection(
    edgeItems,
    {
      filtering: {
        filteringFunction: (item, text) => {
          const t = text.toLowerCase();
          return item.source.toLowerCase().includes(t) || item.target.toLowerCase().includes(t);
        },
      },
      pagination: { pageSize: 25 },
      sorting: {},
    }
  );

  if (loading) {
    return (
      <Box textAlign="center" padding="xxxl">
        <Spinner size="large" />
      </Box>
    );
  }

  if (!graphData) {
    return (
      <Box textAlign="center" padding="xxxl">
        <StatusIndicator type="warning">No graph data available</StatusIndicator>
      </Box>
    );
  }

  return (
    <SpaceBetween size="l">
      <Header
        variant="h1"
        description={`${graphData.metadata.totalNodes} nodes, ${graphData.metadata.totalEdges} edges`}
        actions={
          <SegmentedControl
            selectedId={viewMode}
            onChange={({ detail }) => setViewMode(detail.selectedId)}
            options={[
              { text: 'Graph', id: 'graph' },
              { text: 'Table', id: 'table' },
            ]}
          />
        }
      >
        Knowledge Graph
      </Header>

      <Container header={<Header variant="h3">Legend</Header>}>
        <SpaceBetween direction="horizontal" size="l">
          {Object.entries(GROUP_COLORS).map(([group, color]) => (
            <div key={group} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: color }} />
              <span style={{ textTransform: 'capitalize' }}>{group}</span>
            </div>
          ))}
        </SpaceBetween>
      </Container>

      {graphData.metadata.orphans.length > 0 && (
        <Container header={<Header variant="h3">Orphan Nodes ({graphData.metadata.orphans.length})</Header>}>
          <SpaceBetween direction="horizontal" size="xs">
            {graphData.metadata.orphans.slice(0, 20).map(o => (
              <Badge key={o} color="grey">{o}</Badge>
            ))}
            {graphData.metadata.orphans.length > 20 && (
              <Box color="text-status-inactive">+{graphData.metadata.orphans.length - 20} more</Box>
            )}
          </SpaceBetween>
        </Container>
      )}

      {viewMode === 'graph' ? (
        <Container>
          <div ref={containerRef} style={{ width: '100%', height: '600px' }}>
            <ForceGraph2D
              graphData={forceGraphData}
              width={dimensions.width}
              height={dimensions.height}
              nodeLabel="name"
              nodeColor="color"
              nodeVal="val"
              linkColor={() => '#aab7b8'}
              linkWidth={1}
              onNodeClick={handleNodeClick}
              nodeCanvasObject={(node: ForceGraphNode, ctx: CanvasRenderingContext2D, globalScale: number) => {
                const label = node.name;
                const fontSize = 12 / globalScale;
                ctx.font = `${fontSize}px Sans-Serif`;
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';

                const size = Math.sqrt(node.val || 1) * 2;
                ctx.beginPath();
                ctx.arc(node.x || 0, node.y || 0, size, 0, 2 * Math.PI);
                ctx.fillStyle = node.color;
                ctx.fill();

                if (globalScale > 1.5) {
                  ctx.fillStyle = '#16191f';
                  ctx.fillText(label, node.x || 0, (node.y || 0) + size + fontSize);
                }
              }}
            />
          </div>
        </Container>
      ) : (
        <SpaceBetween size="l">
          <Container header={<Header variant="h3">Nodes by Group</Header>}>
            <ColumnLayout columns={4} variant="text-grid">
              {Object.entries(GROUP_COLORS).map(([g]) => {
                const count = graphData.nodes.filter(n => n.group === g).length;
                return (
                  <div key={g}>
                    <Box variant="awsui-key-label"><span style={{ textTransform: 'capitalize' }}>{g}</span></Box>
                    <Box fontSize="heading-l">{count}</Box>
                  </div>
                );
              })}
            </ColumnLayout>
          </Container>

          <Table
            {...collectionProps}
            header={<Header variant="h3" counter={`(${edgeItems.length})`}>Edges</Header>}
            columnDefinitions={[
              {
                id: 'source',
                header: 'Source',
                cell: (item: GraphEdge) => item.source,
                sortingField: 'source',
              },
              {
                id: 'target',
                header: 'Target',
                cell: (item: GraphEdge) => item.target,
                sortingField: 'target',
              },
            ]}
            items={edgeCollectionItems}
            filter={<TextFilter {...filterProps} filteringPlaceholder="Filter edges..." />}
            pagination={<Pagination {...paginationProps} />}
          />
        </SpaceBetween>
      )}
    </SpaceBetween>
  );
}
