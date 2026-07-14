import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Table from '@cloudscape-design/components/table';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import Link from '@cloudscape-design/components/link';
import Spinner from '@cloudscape-design/components/spinner';
import { getWikis, getCommits, type Wiki, type Commit } from '../api/client';
import { getGraphData, getSearchData, type GraphData } from '../api/data';

interface Stats {
  entities: number;
  concepts: number;
  comparisons: number;
  queries: number;
  totalNodes: number;
  totalEdges: number;
}

export default function DashboardPage({ wikiName }: { wikiName?: string }) {
  const [wikis, setWikis] = useState<Wiki[]>([]);
  const [commits, setCommits] = useState<Commit[]>([]);
  const [stats, setStats] = useState<Stats | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    async function load() {
      try {
        const wikiList = await getWikis();
        setWikis(wikiList);

        const wiki = wikiName
          ? wikiList.find(w => w.name === wikiName) || wikiList[0]
          : wikiList[0];

        if (wiki) {
          const [commitData, graphData, searchData] = await Promise.all([
            getCommits(wiki.name, 10).catch(() => ({ commits: [] })),
            getGraphData(wiki.name).catch(() => null),
            getSearchData(wiki.name).catch(() => ({ documents: [] })),
          ]);

          setCommits(commitData.commits);

          const docs = searchData.documents;
          setStats({
            entities: docs.filter(d => d.group === 'entities').length,
            concepts: docs.filter(d => d.group === 'concepts').length,
            comparisons: docs.filter(d => d.group === 'comparisons').length,
            queries: docs.filter(d => d.group === 'queries').length,
            totalNodes: (graphData as GraphData)?.metadata?.totalNodes || 0,
            totalEdges: (graphData as GraphData)?.metadata?.totalEdges || 0,
          });
        }
      } catch (err) {
        console.error('Failed to load dashboard data:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, []);

  if (loading) {
    return (
      <Box textAlign="center" padding="xxxl">
        <Spinner size="large" />
      </Box>
    );
  }

  return (
    <SpaceBetween size="l">
      <Header variant="h1" description="Knowledge base overview and recent activity">
        Dashboard
      </Header>

      {wikis.length > 0 && (
        <Container header={<Header variant="h2">Wiki: {wikis[0].name}</Header>}>
          <ColumnLayout columns={2} variant="text-grid">
            <div>
              <Box variant="awsui-key-label">Description</Box>
              <div>{wikis[0].description || 'No description'}</div>
            </div>
            <div>
              <Box variant="awsui-key-label">Owner</Box>
              <div>{wikis[0].owner}</div>
            </div>
            <div>
              <Box variant="awsui-key-label">Created</Box>
              <div>{new Date(wikis[0].createdAt).toLocaleDateString()}</div>
            </div>
            <div>
              <Box variant="awsui-key-label">Repository</Box>
              <div>{wikis[0].repositoryName}</div>
            </div>
          </ColumnLayout>
        </Container>
      )}

      {stats && (
        <Container header={<Header variant="h2">Knowledge Base Statistics</Header>}>
          <ColumnLayout columns={4} variant="text-grid">
            <div>
              <Box variant="awsui-key-label">Entities</Box>
              <Link
                fontSize="display-l"
                href={wikiName ? `/w/${wikiName}/entities` : '/entities'}
                onFollow={(e) => { e.preventDefault(); navigate(wikiName ? `/w/${wikiName}/entities` : '/entities'); }}
              >
                {stats.entities}
              </Link>
            </div>
            <div>
              <Box variant="awsui-key-label">Concepts</Box>
              <Link
                fontSize="display-l"
                href={wikiName ? `/w/${wikiName}/concepts` : '/concepts'}
                onFollow={(e) => { e.preventDefault(); navigate(wikiName ? `/w/${wikiName}/concepts` : '/concepts'); }}
              >
                {stats.concepts}
              </Link>
            </div>
            <div>
              <Box variant="awsui-key-label">Comparisons</Box>
              <Link
                fontSize="display-l"
                href={wikiName ? `/w/${wikiName}/comparisons` : '/comparisons'}
                onFollow={(e) => { e.preventDefault(); navigate(wikiName ? `/w/${wikiName}/comparisons` : '/comparisons'); }}
              >
                {stats.comparisons}
              </Link>
            </div>
            <div>
              <Box variant="awsui-key-label">Queries</Box>
              <Link
                fontSize="display-l"
                href={wikiName ? `/w/${wikiName}/queries` : '/queries'}
                onFollow={(e) => { e.preventDefault(); navigate(wikiName ? `/w/${wikiName}/queries` : '/queries'); }}
              >
                {stats.queries}
              </Link>
            </div>
          </ColumnLayout>
          <Box margin={{ top: 'l' }}>
            <ColumnLayout columns={2} variant="text-grid">
              <div>
                <Box variant="awsui-key-label">Graph Nodes</Box>
                <Box fontSize="heading-m">{stats.totalNodes}</Box>
              </div>
              <div>
                <Box variant="awsui-key-label">Graph Edges</Box>
                <Box fontSize="heading-m">{stats.totalEdges}</Box>
              </div>
            </ColumnLayout>
          </Box>
        </Container>
      )}

      <Table
        header={<Header variant="h2">Recent Activity</Header>}
        columnDefinitions={[
          {
            id: 'date',
            header: 'Date',
            cell: (item: Commit) => new Date(item.date).toLocaleString(),
            sortingField: 'date',
            width: 200,
          },
          {
            id: 'commit',
            header: 'Commit',
            cell: (item: Commit) => (
              <Box fontWeight="bold" variant="code">
                {item.commitId.slice(0, 7)}
              </Box>
            ),
            width: 100,
          },
          {
            id: 'message',
            header: 'Message',
            cell: (item: Commit) => item.message.length > 100
              ? item.message.slice(0, 100) + '…'
              : item.message,
          },
          {
            id: 'author',
            header: 'Author',
            cell: (item: Commit) => item.author,
            width: 150,
          },
        ]}
        items={commits}
        loading={loading}
        loadingText="Loading activity..."
        empty={
          <Box textAlign="center" color="inherit">
            <StatusIndicator type="info">No recent activity</StatusIndicator>
          </Box>
        }
        variant="container"
      />
    </SpaceBetween>
  );
}
