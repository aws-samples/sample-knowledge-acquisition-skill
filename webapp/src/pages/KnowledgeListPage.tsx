import { useState, useEffect, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import Table from '@cloudscape-design/components/table';
import Header from '@cloudscape-design/components/header';
import Box from '@cloudscape-design/components/box';
import SpaceBetween from '@cloudscape-design/components/space-between';
import TextFilter from '@cloudscape-design/components/text-filter';
import Pagination from '@cloudscape-design/components/pagination';
import Badge from '@cloudscape-design/components/badge';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import { useCollection } from '@cloudscape-design/collection-hooks';
import { getWikis } from '../api/client';
import { getSearchData, type SearchDoc } from '../api/data';

interface KnowledgeListPageProps {
  group: string;
  title: string;
  description: string;
  wikiName?: string;
}

export default function KnowledgeListPage({ group, title, description, wikiName }: KnowledgeListPageProps) {
  const [items, setItems] = useState<SearchDoc[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    async function load() {
      try {
        const wikis = await getWikis();
        const wiki = wikiName
          ? wikis.find(w => w.name === wikiName) || wikis[0]
          : wikis[0];
        if (wiki) {
          const data = await getSearchData(wiki.name);
          setItems(data.documents.filter(d => d.group === group));
        }
      } catch (err) {
        console.error(`Failed to load ${group}:`, err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [group, wikiName]);

  const columnDefinitions = useMemo(() => [
    {
      id: 'title',
      header: 'Title',
      cell: (item: SearchDoc) => item.title,
      sortingField: 'title',
      isRowHeader: true,
    },
    {
      id: 'tags',
      header: 'Tags',
      cell: (item: SearchDoc) => (
        <SpaceBetween direction="horizontal" size="xs">
          {item.tags.slice(0, 5).map(tag => (
            <Badge key={tag} color="blue">{tag}</Badge>
          ))}
        </SpaceBetween>
      ),
    },
    {
      id: 'headings',
      header: 'Sections',
      cell: (item: SearchDoc) => item.headings.length > 0
        ? item.headings.slice(0, 3).join(', ') + (item.headings.length > 3 ? '…' : '')
        : '—',
    },
  ], []);

  const { items: collectionItems, filterProps, paginationProps, collectionProps } = useCollection(
    items,
    {
      filtering: {
        empty: (
          <Box textAlign="center" color="inherit">
            <StatusIndicator type="info">No {title.toLowerCase()} found</StatusIndicator>
          </Box>
        ),
        noMatch: (
          <Box textAlign="center" color="inherit">
            <StatusIndicator type="info">No matches found</StatusIndicator>
          </Box>
        ),
        filteringFunction: (item, filteringText) => {
          const text = filteringText.toLowerCase();
          return (
            item.title.toLowerCase().includes(text) ||
            item.tags.some(t => t.toLowerCase().includes(text)) ||
            item.body.toLowerCase().includes(text)
          );
        },
      },
      pagination: { pageSize: 20 },
      sorting: {
        defaultState: {
          sortingColumn: { sortingField: 'title' },
          isDescending: false,
        },
      },
    }
  );

  return (
    <Table
      {...collectionProps}
      header={
        <Header variant="h1" counter={`(${items.length})`} description={description}>
          {title}
        </Header>
      }
      columnDefinitions={columnDefinitions}
      items={collectionItems}
      loading={loading}
      loadingText={`Loading ${title.toLowerCase()}...`}
      filter={
        <TextFilter
          {...filterProps}
          filteringPlaceholder={`Search ${title.toLowerCase()}...`}
        />
      }
      pagination={<Pagination {...paginationProps} />}
      variant="full-page"
      stickyHeader={true}
      onRowClick={({ detail }) => {
        const item = detail.item as SearchDoc;
        // item.id is like "concepts/experiment-idea-storage.md" — extract just the slug
        const slug = item.id.replace(/^[^/]+\//, '').replace(/\.md$/, '');
        const base = wikiName ? `/w/${wikiName}` : '';
        navigate(`${base}/page/${group}/${slug}`);
      }}
      empty={
        <Box textAlign="center" color="inherit" padding="l">
          <SpaceBetween size="m">
            <b>No {title.toLowerCase()}</b>
            <Box variant="p" color="inherit">
              No {title.toLowerCase()} have been added to the knowledge base yet.
            </Box>
          </SpaceBetween>
        </Box>
      }
    />
  );
}
