import KnowledgeListPage from './KnowledgeListPage';

export default function QueriesPage({ wikiName }: { wikiName?: string }) {
  return (
    <KnowledgeListPage
      group="queries"
      title="Queries"
      description="Filed research queries and synthesized answers"
      wikiName={wikiName}
    />
  );
}
