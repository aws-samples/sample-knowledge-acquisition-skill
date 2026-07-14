import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@cloudscape-design/components/box';
import Cards from '@cloudscape-design/components/cards';
import Header from '@cloudscape-design/components/header';
import SpaceBetween from '@cloudscape-design/components/space-between';
import Badge from '@cloudscape-design/components/badge';
import Spinner from '@cloudscape-design/components/spinner';
import Link from '@cloudscape-design/components/link';
import { getWikis, type Wiki } from '../api/client';

export default function WikiListPage() {
  const [wikis, setWikis] = useState<Wiki[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    async function load() {
      try {
        const data = await getWikis();
        setWikis(data);
      } catch (err) {
        console.error('Failed to load wikis:', err);
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
    <Cards
      header={
        <Header
          variant="h1"
          description="Select a knowledge base to explore"
          counter={`(${wikis.length})`}
        >
          Knowledge Wikis
        </Header>
      }
      cardDefinition={{
        header: (item: Wiki) => (
          <Link
            fontSize="heading-m"
            href={`/w/${item.name}`}
            onFollow={(e) => { e.preventDefault(); navigate(`/w/${item.name}`); }}
          >
            {item.name}
          </Link>
        ),
        sections: [
          {
            id: 'description',
            header: 'Description',
            content: (item: Wiki) => item.description || 'No description',
          },
          {
            id: 'meta',
            header: 'Details',
            content: (item: Wiki) => (
              <SpaceBetween direction="horizontal" size="s">
                <Badge color="blue">{item.owner}</Badge>
                <Box color="text-status-inactive" fontSize="body-s">
                  Created {new Date(item.createdAt).toLocaleDateString()}
                </Box>
              </SpaceBetween>
            ),
          },
        ],
      }}
      items={wikis}
      empty={
        <Box textAlign="center" padding="l">
          <SpaceBetween size="m">
            <b>No wikis found</b>
            <Box variant="p" color="inherit">
              Start the dev server with WIKI_DIRS pointing to your wiki directories.
            </Box>
          </SpaceBetween>
        </Box>
      }
      cardsPerRow={[{ cards: 1 }, { minWidth: 600, cards: 2 }, { minWidth: 1000, cards: 3 }]}
    />
  );
}
