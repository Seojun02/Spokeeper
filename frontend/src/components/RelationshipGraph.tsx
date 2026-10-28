import { useState } from 'react';
import type { GraphJson } from '../api/types';
import { FullscreenRelationshipGraph } from './FullscreenRelationshipGraph';

export function RelationshipGraph({ graph }: { graph: GraphJson }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className="h-9 shrink-0 border border-[#d8d8ca] bg-transparent px-3 text-xs font-bold text-[#4d574b] transition hover:border-[#283126] hover:text-[#283126]"
        aria-label="관계도 보기"
      >
        관계도 보기
      </button>
      <FullscreenRelationshipGraph
        open={expanded}
        onClose={() => setExpanded(false)}
        entities={graph.entities}
        relationships={graph.relationships}
      />
    </>
  );
}
