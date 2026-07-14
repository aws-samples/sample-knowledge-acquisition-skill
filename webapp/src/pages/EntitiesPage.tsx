import KnowledgeListPage from './KnowledgeListPage';

export default function EntitiesPage({ wikiName }: { wikiName?: string }) {
  return (
    <KnowledgeListPage
      group="entities"
      title="Entities"
      description="People, organizations, products, and systems"
      wikiName={wikiName}
    />
  );
}
