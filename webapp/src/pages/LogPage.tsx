import { useState, useEffect } from 'react';
import Box from '@cloudscape-design/components/box';
import Header from '@cloudscape-design/components/header';
import Table from '@cloudscape-design/components/table';
import TextFilter from '@cloudscape-design/components/text-filter';
import Pagination from '@cloudscape-design/components/pagination';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import ExpandableSection from '@cloudscape-design/components/expandable-section';
import { useCollection } from '@cloudscape-design/collection-hooks';
import { getWikis, getFile } from '../api/client';

interface LogEntry {
  date: string;
  action: string;
  subject: string;
  details: string[];
}

function parseLogMd(content: string): LogEntry[] {
  const entries: LogEntry[] = [];
  const lines = content.split('\n');
  let current: LogEntry | null = null;

  for (const line of lines) {
    const headerMatch = line.match(/^##\s*\[(\d{4}-\d{2}-\d{2})\]\s+([^|]+?)\s*\|\s*(.*)$/);
    if (headerMatch) {
      if (current) entries.push(current);
      current = {
        date: headerMatch[1],
        action: headerMatch[2].trim(),
        subject: headerMatch[3].trim(),
        details: [],
      };
    } else if (current && line.startsWith('- ')) {
      current.details.push(line.slice(2).trim());
    }
  }
  if (current) entries.push(current);

  return entries.reverse(); // Most recent first
}

export default function LogPage({ wikiName }: { wikiName?: string }) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const wikis = await getWikis();
        const wiki = wikiName
          ? wikis.find(w => w.name === wikiName) || wikis[0]
          : wikis[0];
        if (wiki) {
          const file = await getFile(wiki.name, 'log.md');
          setEntries(parseLogMd(file.content));
        }
      } catch (err) {
        console.error('Failed to load log:', err);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [wikiName]);

  const { items, filterProps, paginationProps, collectionProps } = useCollection(
    entries,
    {
      filtering: {
        filteringFunction: (item, text) => {
          const t = text.toLowerCase();
          return (
            item.date.includes(t) ||
            item.action.toLowerCase().includes(t) ||
            item.subject.toLowerCase().includes(t) ||
            item.details.some(d => d.toLowerCase().includes(t))
          );
        },
      },
      pagination: { pageSize: 20 },
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

  return (
    <Table
      {...collectionProps}
      header={
        <Header variant="h1" counter={`(${entries.length})`} description="Chronological record of all wiki actions">
          Activity Log
        </Header>
      }
      columnDefinitions={[
        {
          id: 'date',
          header: 'Date',
          cell: (item: LogEntry) => item.date,
          width: 130,
          sortingField: 'date',
        },
        {
          id: 'action',
          header: 'Action',
          cell: (item: LogEntry) => (
            <StatusIndicator type={
              item.action === 'create' ? 'success' :
              item.action === 'ingest' ? 'info' :
              item.action === 'query' ? 'in-progress' :
              item.action === 'lint' ? 'warning' :
              'stopped'
            }>
              {item.action}
            </StatusIndicator>
          ),
          width: 130,
        },
        {
          id: 'subject',
          header: 'Subject',
          cell: (item: LogEntry) => item.subject,
          sortingField: 'subject',
        },
        {
          id: 'details',
          header: 'Details',
          cell: (item: LogEntry) => item.details.length > 0 ? (
            <ExpandableSection headerText={`${item.details.length} item(s)`} variant="footer">
              <SpaceBetween size="xxs">
                {item.details.map((d, i) => (
                  <Box key={i} fontSize="body-s" color="text-body-secondary">{d}</Box>
                ))}
              </SpaceBetween>
            </ExpandableSection>
          ) : '—',
        },
      ]}
      items={items}
      filter={<TextFilter {...filterProps} filteringPlaceholder="Filter log entries..." />}
      pagination={<Pagination {...paginationProps} />}
      variant="full-page"
      stickyHeader={true}
      empty={
        <Box textAlign="center" color="inherit" padding="l">
          <StatusIndicator type="info">No log entries</StatusIndicator>
        </Box>
      }
    />
  );
}
