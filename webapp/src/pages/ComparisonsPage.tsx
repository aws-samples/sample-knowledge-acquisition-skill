import KnowledgeListPage from './KnowledgeListPage';

export default function ComparisonsPage({ wikiName }: { wikiName?: string }) {
  return (
    <KnowledgeListPage
      group="comparisons"
      title="Comparisons"
      description="Side-by-side analyses and competitive landscapes"
      wikiName={wikiName}
    />
  );
}
