import KnowledgeListPage from './KnowledgeListPage';

export default function ConceptsPage({ wikiName }: { wikiName?: string }) {
  return (
    <KnowledgeListPage
      group="concepts"
      title="Concepts"
      description="Abstract ideas, methods, patterns, and principles"
      wikiName={wikiName}
    />
  );
}
