import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import Badge from '@cloudscape-design/components/badge';
import BreadcrumbGroup from '@cloudscape-design/components/breadcrumb-group';
import ColumnLayout from '@cloudscape-design/components/column-layout';
import Container from '@cloudscape-design/components/container';
import Header from '@cloudscape-design/components/header';
import Link from '@cloudscape-design/components/link';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Spinner from '@cloudscape-design/components/spinner';
import StatusIndicator from '@cloudscape-design/components/status-indicator';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { getWikis, getFile } from '../api/client';
import { getWikiIndex, getGraphData, type GraphData } from '../api/data';

interface Frontmatter {
  title?: string;
  tags?: string[];
  aliases?: string[];
  created?: string;
  updated?: string;
  sources?: string[];
  [key: string]: unknown;
}

function parseFrontmatter(content: string): { frontmatter: Frontmatter; body: string } {
  const fmRegex = /^---\n([\s\S]*?)\n---\n?([\s\S]*)$/;
  const match = content.match(fmRegex);
  if (!match) return { frontmatter: {}, body: content };

  const fmLines = match[1].split('\n');
  const fm: Frontmatter = {};
  let currentKey = '';

  for (const line of fmLines) {
    const kvMatch = line.match(/^(\w+):\s*(.*)$/);
    if (kvMatch) {
      currentKey = kvMatch[1];
      const value = kvMatch[2].trim();
      if (value.startsWith('[') && value.endsWith(']')) {
        fm[currentKey] = value.slice(1, -1).split(',').map(s => s.trim().replace(/^["']|["']$/g, ''));
      } else if (value === '') {
        fm[currentKey] = [];
      } else {
        fm[currentKey] = value.replace(/^["']|["']$/g, '');
      }
    } else if (line.match(/^\s*-\s+(.*)$/) && currentKey) {
      const itemMatch = line.match(/^\s*-\s+(.*)$/);
      if (itemMatch) {
        if (!Array.isArray(fm[currentKey])) fm[currentKey] = [];
        (fm[currentKey] as string[]).push(itemMatch[1].trim().replace(/^["']|["']$/g, ''));
      }
    }
  }

  return { frontmatter: fm, body: match[2] };
}

function resolveWikilinks(body: string, index: Record<string, string>, group: string, wikiBase: string): string {
  return body.replace(/\[\[([^\]]+)\]\]/g, (_match, linkText: string) => {
    const slug = linkText.toLowerCase().replace(/\s+/g, '-');
    const path = index[slug];
    if (path) {
      const linkGroup = path.split('/')[0] || group;
      return `[${linkText}](${wikiBase}/page/${linkGroup}/${slug})`;
    }
    return `<span style="color: #d13212; text-decoration: underline dashed;">${linkText}</span>`;
  });
}

export default function DetailPage({ wikiName }: { wikiName?: string }) {
  const { group, slug } = useParams<{ group: string; slug: string }>();
  const navigate = useNavigate();
  const [content, setContent] = useState('');
  const [frontmatter, setFrontmatter] = useState<Frontmatter>({});
  const [backlinks, setBacklinks] = useState<{ id: string; group: string; label: string }[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    async function load() {
      if (!group || !slug) return;
      setLoading(true);
      setError('');

      // Strip .md extension if present in the URL
      const cleanSlug = slug.replace(/\.md$/, '');

      try {
        const wikis = await getWikis();
        if (wikis.length === 0) {
          setError('No wikis available');
          return;
        }

        const wiki = wikiName
          ? wikis.find(w => w.name === wikiName)?.name || wikis[0].name
          : wikis[0].name;
        const wikiIndex = await getWikiIndex(wiki);
        const graphData = await getGraphData(wiki).catch((): GraphData => ({
          nodes: [], edges: [], metadata: { totalNodes: 0, totalEdges: 0, orphans: [], generatedAt: '' }
        }));

        const filePath = wikiIndex[cleanSlug] || `${group}/${cleanSlug}.md`;
        const fileResult = await getFile(wiki, filePath);
        const { frontmatter: fm, body } = parseFrontmatter(fileResult.content);
        setFrontmatter(fm);

        const resolvedBody = resolveWikilinks(body, wikiIndex, group, wikiName ? `/w/${wikiName}` : '');
        setContent(resolvedBody);

        // Match backlinks by comparing against the file path in the graph
        const currentNodeId = filePath;
        const incomingLinks = graphData.edges
          .filter(e => e.target === currentNodeId || e.target === cleanSlug)
          .map(e => {
            const node = graphData.nodes.find(n => n.id === e.source);
            const sourceSlug = e.source.replace(/^[^/]+\//, '').replace(/\.md$/, '');
            const sourceGroup = e.source.includes('/') ? e.source.split('/')[0] : group;
            return { id: sourceSlug, group: sourceGroup, label: node?.label || sourceSlug };
          });
        setBacklinks(incomingLinks);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load page');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [group, slug]);

  const groupLabel = useMemo(() => {
    const labels: Record<string, string> = {
      entities: 'Entities',
      concepts: 'Concepts',
      comparisons: 'Comparisons',
      queries: 'Queries',
    };
    return labels[group || ''] || group || '';
  }, [group]);

  const handleLinkClick = useCallback((href: string) => {
    if (href.startsWith('/w/') || href.startsWith('/wiki/')) {
      navigate(href);
      return true;
    }
    return false;
  }, [navigate]);

  if (loading) {
    return (
      <Box textAlign="center" padding="xxxl">
        <Spinner size="large" />
      </Box>
    );
  }

  if (error) {
    return (
      <Box textAlign="center" padding="xxxl">
        <StatusIndicator type="error">{error}</StatusIndicator>
      </Box>
    );
  }

  const title = (frontmatter.title as string) || slug || 'Untitled';
  const tags = Array.isArray(frontmatter.tags) ? frontmatter.tags : [];
  const aliases = Array.isArray(frontmatter.aliases) ? frontmatter.aliases : [];
  const sources = Array.isArray(frontmatter.sources) ? frontmatter.sources : [];

  return (
    <SpaceBetween size="l">
      <BreadcrumbGroup
        items={[
          { text: 'All Wikis', href: '/' },
          { text: wikiName || 'Wiki', href: wikiName ? `/w/${wikiName}` : '/' },
          { text: groupLabel, href: wikiName ? `/w/${wikiName}/${group}` : `/${group}` },
          { text: title, href: '#' },
        ]}
        onFollow={(e) => {
          e.preventDefault();
          if (e.detail.href !== '#') navigate(e.detail.href);
        }}
      />

      <Container
        header={
          <Header variant="h1" description={aliases.length > 0 ? `Also known as: ${aliases.join(', ')}` : undefined}>
            {title}
          </Header>
        }
      >
        <SpaceBetween size="l">
          {(tags.length > 0 || frontmatter.created || frontmatter.updated) && (
            <ColumnLayout columns={3} variant="text-grid">
              {tags.length > 0 && (
                <div>
                  <Box variant="awsui-key-label">Tags</Box>
                  <SpaceBetween direction="horizontal" size="xs">
                    {tags.map(tag => <Badge key={tag} color="blue">{tag}</Badge>)}
                  </SpaceBetween>
                </div>
              )}
              {frontmatter.created && (
                <div>
                  <Box variant="awsui-key-label">Created</Box>
                  <div>{String(frontmatter.created)}</div>
                </div>
              )}
              {frontmatter.updated && (
                <div>
                  <Box variant="awsui-key-label">Updated</Box>
                  <div>{String(frontmatter.updated)}</div>
                </div>
              )}
            </ColumnLayout>
          )}

          <div className="markdown-body">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                a: ({ href, children }) => {
                  if (href && (href.startsWith('/w/') || href.startsWith('/wiki/'))) {
                    return (
                      <Link
                        href={href}
                        onFollow={(e) => {
                          e.preventDefault();
                          handleLinkClick(href);
                        }}
                      >
                        {children}
                      </Link>
                    );
                  }
                  return <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>;
                },
              }}
            >
              {content}
            </ReactMarkdown>
          </div>

          {sources.length > 0 && (
            <Container header={<Header variant="h3">Sources</Header>}>
              <SpaceBetween size="xs">
                {sources.map((src, i) => (
                  <div key={i}>
                    {src.startsWith('http') ? (
                      <Link href={src} external>{src}</Link>
                    ) : (
                      <Box>{src}</Box>
                    )}
                  </div>
                ))}
              </SpaceBetween>
            </Container>
          )}

          {backlinks.length > 0 && (
            <Container header={<Header variant="h3">Backlinks ({backlinks.length})</Header>}>
              <SpaceBetween size="xs">
                {backlinks.map(bl => {
                  const base = wikiName ? `/w/${wikiName}` : '';
                  return (
                    <Link
                      key={bl.id}
                      href={`${base}/page/${bl.group}/${bl.id}`}
                      onFollow={(e) => {
                        e.preventDefault();
                        navigate(`${base}/page/${bl.group}/${bl.id}`);
                      }}
                    >
                      {bl.label}
                    </Link>
                  );
                })}
              </SpaceBetween>
            </Container>
          )}
        </SpaceBetween>
      </Container>
    </SpaceBetween>
  );
}
