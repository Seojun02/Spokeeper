import { useEffect, useMemo, useRef, useState } from 'react';
import cytoscape, { type Core, type ElementDefinition, type EventObject } from 'cytoscape';
import type { Entity, Relationship } from '../api/types';
import {
  deriveCharacterGroups,
  usedGroups,
  type CharacterGroupId,
} from './RelationshipGraph/grouping/deriveCharacterGroup';
import { FIT_PADDING, runFullscreenLayout } from './RelationshipGraph/layout/fullscreen';
import { CATEGORY_COLOR, edgeStyles } from './RelationshipGraph/styles/edgeStyles';
import { nodeBorderWidth, nodeSize, nodeStyles } from './RelationshipGraph/styles/nodeStyles';
import { isDeceased } from '../utils/characterStatus';

const MIN_ZOOM = 0.35;
const MAX_ZOOM = 2.8;

const ENTITY_COLOR_PALETTE = [
  '#6b8eaa',
  '#789b7a',
  '#b18478',
  '#8b7fa8',
  '#b39462',
  '#648f8b',
  '#9a7890',
  '#7f91b2',
  '#8d9a68',
  '#b0786b',
  '#718ca0',
  '#927fa0',
] as const;

function entityColor(entityId: string): string {
  let hash = 2166136261;
  for (let index = 0; index < entityId.length; index += 1) {
    hash ^= entityId.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return ENTITY_COLOR_PALETTE[(hash >>> 0) % ENTITY_COLOR_PALETTE.length];
}

type Detail = {
  title: string;
  detail: string;
  eventName: string;
};

function scoreOf(entity: Entity) {
  return Math.max(1, Math.min(5, entity.importance_score ?? (entity.importance_level === 'major' ? 4 : 2)));
}

function relationLabel(relationship: Relationship) {
  return relationship.display_label || relationship.role_pair_label || relationship.label || '관계';
}

function relationDetail(relationship: Relationship) {
  return relationship.relationship_summary || relationship.event_summary || relationship.description || relationLabel(relationship);
}

// 연인/친구/원수/가족처럼 "관계 자체가 정체성인" 것만 기본 그래프에 보여준다.
// 목격자/조사/공범처럼 특정 사건 때문에 생긴 "행동 기반" 관계는 정보량은 있지만
// 기본 화면에 두면 계속 같은 종류의 엣지로 그래프가 채워져 정작 보고 싶은
// 인간관계가 묻힌다 — 근거가 약한 관계와 같은 방식으로 처리한다: 기본으로는
// 숨기고, 연결된 인물을 클릭하면 드러난다.
//
// relation_kind는 BuildAgent가 원본 관계를 뽑을 때 LLM이 직접 판단해서 채운
// 필드라 이걸 최우선으로 쓴다 — 카테고리 키워드 사전을 계속 늘려야 하는 방식보다
// 장르에 안 흔들린다. 이 필드가 없는 구버전 데이터(relation_kind가 비어있음,
// 예: 재분석 전 책)만 category 기반 근사치로 폴백한다.
const PERSONAL_CATEGORIES = new Set(['family', 'romance', 'ally', 'conflict']);

function isPersonalRelation(relationship: Relationship): boolean {
  if (relationship.relation_kind) return relationship.relation_kind === 'personal';
  return PERSONAL_CATEGORIES.has(relationship.relation_category ?? 'neutral');
}

function makeElements(entities: Entity[], relationships: Relationship[]) {
  const { groupByEntityId } = deriveCharacterGroups(entities, relationships);
  const nodeIds = new Set<string>();
  const usedEdgeIds = new Set<string>();
  const nodes: ElementDefinition[] = [];

  entities.forEach((entity) => {
    const id = String(entity.id ?? '').trim();
    if (!id || nodeIds.has(id)) return;
    nodeIds.add(id);
    const score = scoreOf(entity);
    const size = nodeSize(score);
    const group = groupByEntityId.get(id);
    // 파스텔(softColor)로 바꿨더니 너무 흐려 보인다는 피드백이 있어, 원래 진한
    // 그룹 색(color)으로 되돌리고 대신 nodeStyles.ts의 background-opacity를
    // 낮춰서 채도는 유지하면서 눈부심만 줄인다.
    const color = entityColor(id);
    const deceased = isDeceased(entity.description);
    const name = deceased ? `故 ${entity.name || id}` : entity.name || id;

    nodes.push({
      group: 'nodes',
      classes: deceased ? 'deceased' : undefined,
      data: {
        id,
        label: name,
        score,
        size,
        hoverSize: size + 8,
        focusSize: size + 16,
        borderWidth: nodeBorderWidth(score),
        color,
        borderColor: group?.borderColor ?? '#475569',
        groupId: group?.id ?? 'other',
        groupLabel: group?.label ?? '기타',
      },
    });

  });

  const edges: ElementDefinition[] = [];
  const pairEdgeIndexes = new Map<string, number>();
  relationships.forEach((relationship, index) => {
    const source = String(relationship.source ?? '').trim();
    const target = String(relationship.target ?? '').trim();
    if (!source || !target || !nodeIds.has(source) || !nodeIds.has(target)) return;

    const rawId = String(relationship.id || `${source}-${target}-${index}`);
    let id = rawId;
    let suffix = 2;
    while (usedEdgeIds.has(id)) {
      id = `${rawId}-${suffix}`;
      suffix += 1;
    }
    usedEdgeIds.add(id);

    const pairKey = [source, target].sort().join('::');
    const pairIndex = pairEdgeIndexes.get(pairKey) ?? 0;
    pairEdgeIndexes.set(pairKey, pairIndex + 1);
    // 한 인물 쌍의 첫 관계는 가장 짧고 자연스러운 직선으로 표시한다. 같은 쌍에
    // 관계가 더 있을 때만 두 번째 선부터 좌우 곡선으로 벌려 겹침을 피한다.
    // 기존 42px 곡률보다 완만한 28px 간격을 사용해 선이 과하게 휘지 않게 한다.
    const curvedIndex = Math.max(0, pairIndex - 1);
    const curveLevel = Math.floor(curvedIndex / 2) + 1;
    const curveDirection = curvedIndex % 2 === 0 ? 1 : -1;
    const curveStyle = pairIndex === 0 ? 'straight' : 'unbundled-bezier';

    const category = relationship.relation_category ?? 'neutral';
    const relationScore = relationship.relation_importance_score ?? (relationship.relation_importance_level === 'major' ? 4 : 2);
    const majorLabel = relationScore >= 4 || relationship.relation_importance_level === 'major';
    // 근거(원본 라벨/구조화된 사건) 없이 리마인더 공동 언급만으로 만든 약한 관계이거나,
    // 목격자/조사/공범 같은 "행동 기반" 카테고리면 기본 그래프에 안 그린다 —
    // 연결된 인물을 클릭했을 때만 점선으로 드러난다(edgeStyles.ts의 'edge.weak-edge' /
    // 'edge.weak-edge.focused' 참고).
    const isWeak = relationship.has_direct_evidence === false || !isPersonalRelation(relationship);
    edges.push({
      group: 'edges',
      classes: isWeak ? 'weak-edge' : undefined,
      data: {
        id,
        source,
        target,
        label: relationLabel(relationship),
        visibleLabel: majorLabel ? relationLabel(relationship) : '',
        majorLabel: majorLabel ? 'true' : 'false',
        category,
        color: CATEGORY_COLOR[category] ?? CATEGORY_COLOR.neutral,
        directed: relationship.directionality === 'directed',
        width: majorLabel ? 3 : 2,
        opacity: majorLabel ? 0.82 : 0.38,
        curveStyle,
        controlPointDistance: curveLevel * curveDirection * 28,
        detail: relationDetail(relationship),
        eventName: relationship.event_name ?? '',
      },
    });
  });

  return {
    elements: [...nodes, ...edges],
    nodeCount: nodes.length,
    edgeCount: edges.length,
    groups: usedGroups(groupByEntityId),
  };
}

// 설명 위성 노드를 본체 노드 바로 위에 붙여둔다. 본체가 드래그되거나 레이아웃
// 애니메이션으로 움직일 때마다 따라다니는 것처럼 보이게 매 프레임 재확인한다.
const CAPTION_GAP = 12;

function syncCaptionPosition(cy: Core, node: cytoscape.NodeSingular) {
  const caption = cy.getElementById(`${node.id()}__caption`);
  if (caption.empty()) return;
  const size = Number(node.data('size') || 48);
  const targetX = node.position('x');
  const targetY = node.position('y') - size / 2 - CAPTION_GAP;
  const current = caption.position();
  // 위치가 실제로 바뀔 때만 다시 세팅한다 — 매 렌더 프레임마다 이 함수가 불리는데,
  // 값이 그대로인데도 계속 .position()을 호출하면 그 자체가 다시 렌더를 요청해서
  // 무한 렌더 루프에 빠질 수 있다.
  if (Math.abs(current.x - targetX) < 0.5 && Math.abs(current.y - targetY) < 0.5) return;
  caption.position({ x: targetX, y: targetY });
}

function syncAllCaptionPositions(cy: Core) {
  cy.nodes(':not(.node-caption)').forEach((node) => syncCaptionPosition(cy, node));
}

function clearFocus(cy: Core) {
  cy.elements().removeClass('faded focused neighbor matched');
}

function applyNodeFocus(cy: Core, node: cytoscape.NodeSingular) {
  cy.elements().removeClass('focused neighbor matched').addClass('faded');
  node.removeClass('faded').addClass('focused');
  node.connectedEdges().removeClass('faded').addClass('focused');
  const neighbors = node.neighborhood('node');
  neighbors.removeClass('faded').addClass('neighbor');
  // 위성 노드는 본체와 별개 element라 위 removeClass가 안 닿는다 — 포커스된
  // 인물과 그 이웃의 설명도 같이 안 흐려지게 직접 챙긴다.
  cy.getElementById(`${node.id()}__caption`).removeClass('faded');
  neighbors.forEach((neighbor) => {
    cy.getElementById(`${neighbor.id()}__caption`).removeClass('faded');
  });
}

function arrangeAroundFocusedNode(cy: Core, focusedNode: cytoscape.NodeSingular) {
  const focusedId = focusedNode.id();
  const neighborIds = new Set(focusedNode.neighborhood('node').map((node) => node.id()));
  const layoutTargets = cy.elements().not('.node-caption');
  const layout = layoutTargets.layout({
    name: 'concentric',
    fit: false,
    animate: true,
    animationDuration: 420,
    minNodeSpacing: 72,
    avoidOverlap: true,
    startAngle: -Math.PI / 2,
    clockwise: true,
    concentric: (node: cytoscape.NodeSingular) => {
      if (node.id() === focusedId) return 100;
      if (neighborIds.has(node.id())) return 50;
      return 0;
    },
    levelWidth: () => 1,
  });

  layout.one('layoutstop', () => {
    syncAllCaptionPositions(cy);
    const focusElements = focusedNode.union(focusedNode.neighborhood());
    if (focusElements.length === 0) return;
    // 이웃이 많을 때 fit만 사용하면 모든 이웃을 화면에 넣으려고 오히려 크게
    // 축소된다. fit으로 계산한 배율을 참고하되 최소 1.55배는 보장하고, 화면의
    // 중심도 선택 노드 자체에 맞춰 클릭한 인물과 연결선이 확실히 보이게 한다.
    const bounds = focusElements.boundingBox();
    const fitZoom = bounds.w > 0 && bounds.h > 0
      ? Math.min(
          Math.max(1, cy.width() - 144) / bounds.w,
          Math.max(1, cy.height() - 144) / bounds.h,
        )
      : cy.zoom();
    // 레이아웃 애니메이션 직후 또 다른 viewport 애니메이션을 실행하면 Cytoscape가
    // 앞선 fit/zoom 상태를 유지하는 경우가 있다. 여기서는 뷰포트를 직접 설정해
    // 전체 인물이 떠 있어도 선택 노드가 반드시 크게 보이도록 보장한다.
    const focusedZoom = Math.min(MAX_ZOOM, Math.max(1.55, fitZoom));
    cy.stop();
    cy.zoom(focusedZoom);
    cy.center(focusedNode);
  });
  layout.run();
}

export function FullscreenRelationshipGraph({
  open,
  onClose,
  entities,
  relationships,
}: {
  open: boolean;
  onClose: () => void;
  entities: Entity[];
  relationships: Relationship[];
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<Core | null>(null);
  const seenNodeIdsRef = useRef(new Set<string>());
  const seenEdgeIdsRef = useRef(new Set<string>());
  const [search, setSearch] = useState('');
  const [detail, setDetail] = useState<Detail | null>(null);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [activeGroup, setActiveGroup] = useState<CharacterGroupId | 'all'>('all');
  const [showMinorCharacters, setShowMinorCharacters] = useState(false);
  const { visibleEntities, visibleRelationships, minorCharacterCount } = useMemo(() => {
    const majorEntities = entities.filter(
      (entity) => entity.importance_level === 'major' || scoreOf(entity) >= 3,
    );
    // 책의 아주 초반처럼 아직 major 판정을 받은 인물이 없으면 인물 선택 목록과
    // 동일하게 중요도 상위 4명을 기본 그래프에 보여 빈 화면이 되지 않게 한다.
    const defaultEntities = majorEntities.length > 0
      ? majorEntities
      : [...entities]
          .sort((a, b) => scoreOf(b) - scoreOf(a) || a.name.localeCompare(b.name))
          .slice(0, 4);
    const shownEntities = showMinorCharacters ? entities : defaultEntities;
    const shownIds = new Set(shownEntities.map((entity) => entity.id));

    return {
      visibleEntities: shownEntities,
      // 양 끝 인물이 모두 현재 표시 대상일 때만 관계선을 만든다.
      visibleRelationships: relationships.filter(
        (relationship) => shownIds.has(relationship.source) && shownIds.has(relationship.target),
      ),
      minorCharacterCount: Math.max(0, entities.length - defaultEntities.length),
    };
  }, [entities, relationships, showMinorCharacters]);
  const { elements, nodeCount, edgeCount, groups } = useMemo(
    () => makeElements(visibleEntities, visibleRelationships),
    [visibleEntities, visibleRelationships],
  );

  const fitVisibleNodes = () => {
    const cy = cyRef.current;
    if (!cy || cy.destroyed()) return;
    const visibleNodes = cy.nodes(':visible');
    if (visibleNodes.length > 0) {
      cy.resize();
      cy.fit(visibleNodes, FIT_PADDING);
      cy.center(visibleNodes);
    }
  };

  const runCoseLayout = () => {
    const cy = cyRef.current;
    if (!cy || cy.destroyed()) return;
    // cose 레이아웃은 애니메이션 도중에 매 프레임마다 'position' 이벤트를 안 쏴줄 수
    // 있어서(내부적으로 배치 처리), 위성 노드 동기화를 'position' 리스너 하나에만
    // 맡기면 레이아웃이 끝난 뒤에도 예전 위치(추가 직후의 기본 좌표, 보통 한 구석)에
    // 몰려있는 채로 남을 수 있다. 레이아웃이 완전히 멈춘 시점(layoutstop)에 한 번
    // 더 확실히 동기화해서 최종 위치는 항상 맞도록 보장한다.
    runFullscreenLayout(cy, () => {
      syncAllCaptionPositions(cy);
      fitVisibleNodes();
    });
  };

  useEffect(() => {
    if (!open || !containerRef.current || cyRef.current) return;

    const cy = cytoscape({
      container: containerRef.current,
      elements: [],
      minZoom: MIN_ZOOM,
      maxZoom: MAX_ZOOM,
      wheelSensitivity: 0.18,
      userPanningEnabled: true,
      userZoomingEnabled: true,
      boxSelectionEnabled: false,
      style: [...nodeStyles, ...edgeStyles] as unknown as cytoscape.StylesheetCSS[],
    });

    cyRef.current = cy;

    cy.on('mouseover', 'edge', (event: EventObject) => event.target.addClass('hovered'));
    cy.on('mouseout', 'edge', (event: EventObject) => event.target.removeClass('hovered'));
    cy.on('mouseover', 'node', (event: EventObject) => {
      if (!event.target.hasClass('node-caption')) event.target.addClass('hovered');
    });
    cy.on('mouseout', 'node', (event: EventObject) => event.target.removeClass('hovered'));

    // 위성 노드는 스타일에서 이벤트를 꺼뒀지만(events:'no'), 혹시 몰라 한 번 더 막는다.
    cy.on('tap', 'node', (event: EventObject) => {
      if (event.target.hasClass('node-caption')) return;
      applyNodeFocus(cy, event.target);
      arrangeAroundFocusedNode(cy, event.target);
      setDetail(null);
      setSelectedEntityId(event.target.id());
    });
    // 본체 노드가 움직일 때마다(드래그) 설명 위성 노드를 바로 위로 따라가게 한다.
    cy.on('position', 'node', (event: EventObject) => {
      const node = event.target as cytoscape.NodeSingular;
      if (node.hasClass('node-caption')) return;
      syncCaptionPosition(cy, node);
    });
    // cose 레이아웃 애니메이션 중에는 'position' 이벤트가 매 프레임 안 쏴질 수 있어서,
    // 화면이 실제로 다시 그려질 때마다(매 프레임) 한 번씩 전체를 다시 맞춰서 애니메이션
    // 중에도 위성 노드가 본체를 눈에 띄게 벗어나 있지 않게 한다.
    cy.on('render', () => syncAllCaptionPositions(cy));
    cy.on('tap', 'edge', (event: EventObject) => {
      const edge = event.target;
      cy.elements().removeClass('focused neighbor matched').addClass('faded');
      edge.removeClass('faded').addClass('focused');
      const connected = edge.connectedNodes();
      connected.removeClass('faded').addClass('neighbor');
      connected.forEach((node: cytoscape.NodeSingular) => {
        cy.getElementById(`${node.id()}__caption`).removeClass('faded');
      });
      setDetail({
        title: edge.data('label'),
        detail: edge.data('detail'),
        eventName: edge.data('eventName'),
      });
      setSelectedEntityId(null);
    });
    cy.on('tap', (event: EventObject) => {
      if (event.target === cy) {
        clearFocus(cy);
        setDetail(null);
        setSelectedEntityId(null);
        runFullscreenLayout(cy, () => {
          syncAllCaptionPositions(cy);
          fitVisibleNodes();
        });
      }
    });

    return () => {
      cy.destroy();
      cyRef.current = null;
    };
  }, [open]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!open || !cy || cy.destroyed()) return;
    cy.batch(() => {
      cy.elements().remove();
      cy.add(elements);
    });

    const newNodes = cy.nodes(':not(.node-caption)').filter(
      (node) => !seenNodeIdsRef.current.has(node.id()),
    );
    const newEdges = cy.edges().filter(
      (edge) => !seenEdgeIdsRef.current.has(edge.id()),
    );
    cy.nodes(':not(.node-caption)').forEach((node) => {
      seenNodeIdsRef.current.add(node.id());
    });
    cy.edges().forEach((edge) => {
      seenEdgeIdsRef.current.add(edge.id());
    });

    if (newNodes.length > 0) {
      newNodes.addClass('new-node');
      window.setTimeout(() => newNodes.removeClass('new-node'), 30);
    }
    if (newEdges.length > 0) {
      newEdges.addClass('new-edge');
      window.setTimeout(() => newEdges.removeClass('new-edge'), 30);
    }
    syncAllCaptionPositions(cy);
    clearFocus(cy);
    setDetail(null);
    setSelectedEntityId(null);
    runCoseLayout();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, elements]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!open || !cy || cy.destroyed()) return;
    cy.nodes().removeClass('matched');
    const query = search.trim().toLowerCase();
    if (!query) return;
    cy.nodes(':not(.node-caption)').forEach((node) => {
      if (String(node.data('label')).toLowerCase().includes(query)) node.addClass('matched');
    });
  }, [open, search]);

  useEffect(() => {
    const cy = cyRef.current;
    if (!open || !cy || cy.destroyed()) return;
    cy.elements().removeClass('group-muted group-highlight');
    if (activeGroup === 'all') return;
    cy.nodes(':not(.node-caption)').forEach((node) => {
      if (node.data('groupId') === activeGroup) {
        node.addClass('group-highlight');
      } else {
        node.addClass('group-muted');
      }
    });
    cy.edges().forEach((edge) => {
      const inGroup = edge.connectedNodes().some((node) => node.data('groupId') === activeGroup);
      edge.addClass(inGroup ? 'group-highlight' : 'group-muted');
    });
  }, [activeGroup, open, elements]);

  useEffect(() => {
    if (!open) {
      setShowMinorCharacters(false);
      setActiveGroup('all');
    }
  }, [open]);

  if (!open) return null;

  const selectedEntity = visibleEntities.find((entity) => entity.id === selectedEntityId) ?? null;
  const selectedRelationships = selectedEntity
    ? visibleRelationships.filter(
        (relationship) =>
          relationship.source === selectedEntity.id || relationship.target === selectedEntity.id,
      )
    : [];
  const entityNames = new Map(visibleEntities.map((entity) => [entity.id, entity.name]));

  const zoom = (factor: number) => {
    const cy = cyRef.current;
    if (!cy || cy.destroyed()) return;
    cy.zoom({
      level: Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, cy.zoom() * factor)),
      renderedPosition: { x: cy.width() / 2, y: cy.height() / 2 },
    });
  };

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-[#1a1512]/40 p-4" role="dialog" aria-modal="true">
      <div className="flex h-[88vh] w-[min(1180px,96vw)] flex-col overflow-hidden border border-[#283126] bg-[#fffdf8] shadow-2xl">
        <header className="flex h-[60px] shrink-0 items-center justify-between border-b border-[#d8d8ca] bg-[#fbfaf5] px-6">
          <h2 className="font-serif text-lg font-bold text-[#283126]">관계도 탐색</h2>
          <button type="button" onClick={onClose} className="grid h-9 w-9 place-items-center border border-transparent bg-transparent text-xl leading-none text-[#4d574b] transition hover:border-[#283126] hover:text-[#283126]" aria-label="관계도 닫기">
            ×
          </button>
        </header>
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-[#dedbd1] px-6 py-3">
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="인물 검색"
            className="h-10 w-72 border-x-0 border-t-0 border-b border-[#d8d8ca] bg-transparent px-1 text-sm font-semibold text-[#4d574b] outline-none transition focus:border-[#283126]"
          />
          <div className="flex flex-wrap justify-end gap-2">
            {minorCharacterCount > 0 && (
              <button
                type="button"
                onClick={() => setShowMinorCharacters((value) => !value)}
                className={`h-9 border px-3 text-xs font-bold transition ${
                  showMinorCharacters
                    ? 'border-[#283126] bg-[#283126] text-white'
                    : 'border-[#d8d8ca] bg-transparent text-[#4d574b] hover:border-[#283126]'
                }`}
              >
                기타 등장인물 {showMinorCharacters ? '접기' : '보기'} ({minorCharacterCount})
              </button>
            )}
            <button type="button" onClick={() => zoom(1 / 1.18)} className="h-9 w-9 border border-[#d8d8ca] bg-transparent text-sm font-bold text-[#4d574b]">-</button>
            <button type="button" onClick={() => zoom(1.18)} className="h-9 w-9 border border-[#d8d8ca] bg-transparent text-sm font-bold text-[#4d574b]">+</button>
            <button type="button" onClick={fitVisibleNodes} className="h-9 border border-[#d8d8ca] bg-transparent px-3 text-xs font-bold text-[#4d574b]">Fit</button>
            <button type="button" onClick={() => cyRef.current?.center()} className="h-9 border border-[#d8d8ca] bg-transparent px-3 text-xs font-bold text-[#4d574b]">Center</button>
            <button type="button" onClick={runCoseLayout} className="h-9 border border-[#d8d8ca] bg-transparent px-3 text-xs font-bold text-[#4d574b]">Reset Layout</button>
          </div>
        </div>
        <div className="grid h-[calc(90vh-120px)] min-h-[600px] grid-cols-[minmax(0,1fr)_320px]">
          <div className="relative min-w-0">
          <div ref={containerRef} className="absolute inset-0 h-full w-full bg-[radial-gradient(circle,#d2d6c8_1px,transparent_1px)] bg-[length:24px_24px] bg-[#fbfaf5]" />
          {visibleEntities.length === 0 && (
            <div className="absolute inset-0 grid place-items-center bg-slate-50 text-sm font-semibold text-slate-400">
              현재 위치까지 표시할 인물이 없습니다.
            </div>
          )}
          {visibleEntities.length > 0 && nodeCount === 0 && (
            <div className="absolute inset-0 grid place-items-center bg-slate-50 text-sm font-semibold text-slate-400">
              표시 가능한 인물 정보가 없습니다.
            </div>
          )}
          <div className="absolute left-4 top-4 max-w-[280px] rounded-lg border border-slate-200 bg-white/92 p-3 text-xs font-bold text-slate-600 shadow-sm">
            <div className="mb-2 text-[11px] uppercase tracking-[0.08em] text-slate-400">Groups</div>
            <div className="flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => setActiveGroup('all')}
                className={`rounded-full border px-2 py-1 text-[11px] font-extrabold transition ${activeGroup === 'all' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'}`}
              >
                전체
              </button>
              {groups.map((group) => (
                <button
                  key={group.id}
                  type="button"
                  onClick={() => setActiveGroup(group.id)}
                  className={`rounded-full border px-2 py-1 text-[11px] font-extrabold transition ${activeGroup === group.id ? 'text-white' : 'bg-white text-slate-600 hover:border-slate-300'}`}
                  style={{
                    borderColor: activeGroup === group.id ? group.borderColor : '#e2e8f0',
                    backgroundColor: activeGroup === group.id ? group.color : '#ffffff',
                  }}
                >
                  <span className="mr-1 inline-block h-2 w-2 rounded-full" style={{ backgroundColor: group.color }} />
                  {group.label}
                </button>
              ))}
            </div>
            <div className="mt-2 text-[11px] text-slate-400">nodes {nodeCount} · edges {edgeCount}</div>
          </div>
          {detail && (
            <div className="absolute bottom-4 left-4 max-w-xl rounded-lg border border-slate-200 bg-white/95 p-3 text-xs font-semibold leading-5 text-slate-600 shadow-xl">
              <div className="mb-1 text-sm font-extrabold text-slate-800">{detail.title}</div>
              {detail.eventName && <div className="mb-1 text-slate-400">대표 사건: {detail.eventName}</div>}
              <p>{detail.detail}</p>
            </div>
          )}
          </div>
          <aside className="overflow-y-auto border-l border-[#d8d8ca] bg-[#fbfaf5] p-5" aria-live="polite">
            {!selectedEntity && (
              <p className="rounded-xl border border-dashed border-slate-300 bg-white p-5 text-sm leading-6 text-slate-500 shadow-sm">
                관계도에서 인물을 선택하면 상세 정보가 표시됩니다.
              </p>
            )}
            {selectedEntity && (
              <div className="space-y-6">
                <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                  <div className="flex items-start gap-3">
                    <span className="mt-1 h-3 w-3 shrink-0 rounded-full ring-4 ring-slate-100" style={{ backgroundColor: entityColor(selectedEntity.id) }} />
                    <div className="min-w-0">
                      <h3 className="break-words text-xl font-extrabold leading-tight text-slate-900">{selectedEntity.name}</h3>
                      <span className="mt-2 inline-flex rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] font-bold text-slate-500">
                        {selectedEntity.type === 'person' ? '인물' : selectedEntity.type}
                      </span>
                    </div>
                  </div>
                {selectedEntity.aliases && selectedEntity.aliases.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5 border-t border-slate-100 pt-3">
                    {selectedEntity.aliases.map((alias) => (
                      <span key={alias} className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">별칭 · {alias}</span>
                    ))}
                  </div>
                )}
                </section>

                <section>
                  <h4 className="text-xs font-extrabold uppercase tracking-[0.08em] text-slate-400">설명</h4>
                  <p className="mt-2 whitespace-pre-wrap break-words rounded-xl border border-slate-200 bg-white p-4 text-sm leading-6 text-slate-600 shadow-sm">
                    {selectedEntity.description || '표시할 인물 설명이 없습니다.'}
                  </p>
                </section>

                <section>
                  <div className="flex items-center justify-between">
                    <h4 className="text-xs font-extrabold uppercase tracking-[0.08em] text-slate-400">관계 목록</h4>
                    <span className="rounded-full bg-slate-200/70 px-2 py-0.5 text-[11px] font-bold text-slate-500">{selectedRelationships.length}</span>
                  </div>
                <div className="mt-2 space-y-3">
                  {selectedRelationships.length === 0 && <p className="text-sm text-slate-400">표시할 관계가 없습니다.</p>}
                  {selectedRelationships.map((relationship) => {
                    const counterpartId = relationship.source === selectedEntity.id
                      ? relationship.target
                      : relationship.source;
                    return (
                      <div
                        key={relationship.id}
                        className="rounded-xl border border-slate-200 border-l-4 bg-white p-3 shadow-sm transition-colors duration-200 hover:bg-slate-50"
                        style={{ borderLeftColor: entityColor(counterpartId) }}
                      >
                        <div className="flex items-center gap-2">
                          <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ backgroundColor: entityColor(counterpartId) }} />
                          <div className="break-words text-sm font-extrabold text-slate-800">{entityNames.get(counterpartId) ?? counterpartId}</div>
                        </div>
                        <span className="mt-2 inline-flex rounded-full bg-slate-100 px-2 py-1 text-[11px] font-bold text-slate-600">{relationLabel(relationship)}</span>
                        <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-5 text-slate-500">{relationDetail(relationship)}</p>
                        <p className="mt-2 text-[11px] font-medium text-slate-400">revision {relationship.revision_offset}</p>
                      </div>
                    );
                  })}
                </div>
                </section>
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
