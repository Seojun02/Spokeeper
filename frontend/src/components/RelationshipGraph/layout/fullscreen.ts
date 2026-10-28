import cytoscape from 'cytoscape';
import type { Core, LayoutOptions } from 'cytoscape';
import fcose from 'cytoscape-fcose';

// fCoSE: CoSE(Compound Spring Embedder)의 개선판 — 같은 force-directed 계열이지만
// 스펙트럴 레이아웃으로 초기 배치를 먼저 잡고 그 위에서 힘 시뮬레이션을 돌려서,
// CoSE보다 최대 2배 빠르면서 겹침/뭉침이 덜한 결과를 낸다. 확장 등록은 한 번만
// 하면 되므로 모듈 로드 시점에 해둔다(cytoscape가 이미 등록된 경우 재등록은
// no-op이라 안전).
cytoscape.use(fcose);

export const FIT_PADDING = 38;

export function gridLayoutOptions(): LayoutOptions {
  return {
    name: 'grid',
    fit: true,
    padding: FIT_PADDING,
    animate: false,
  } as LayoutOptions;
}

export function fcoseLayoutOptions(): LayoutOptions {
  return {
    name: 'fcose',
    quality: 'proof',
    fit: true,
    padding: FIT_PADDING,
    animate: true,
    animationDuration: 300,
    randomize: false,
    // 기존 위치를 초기값으로 유지하면서 연결된 노드가 한 덩어리로 보이도록
    // 거리와 반발력을 약 25% 줄인다.
    nodeRepulsion: 2000,
    nodeSeparation: 120,
    idealEdgeLength: 88,
    edgeElasticity: 0.6,
    nestingFactor: 0.1,
    gravity: 0.45,
    componentSpacing: 46,
    numIter: 2500,
    tile: true,
    packComponents: true,
  } as LayoutOptions;
}

export function seedGroupedPositions(cy: Core) {
  // 설명 위성 노드(node-caption)는 레이아웃 물리 연산 대상이 아니다 — 본체 노드
  // 위치가 정해지면 그 아래로 따로 동기화된다(FullscreenRelationshipGraph 참고).
  const nodes = cy.nodes(':not(.node-caption)');
  if (nodes.length === 0) return;

  const groups = Array.from(new Set(nodes.map((node) => String(node.data('groupId') || 'other'))));
  const centerX = Math.max(cy.width() / 2, 400);
  const centerY = Math.max(cy.height() / 2, 300);
  const radius = Math.max(180, Math.min(cy.width(), cy.height()) * 0.28);
  const grouped = new Map<string, typeof nodes>();

  groups.forEach((groupId) => {
    grouped.set(groupId, nodes.filter((node) => node.data('groupId') === groupId));
  });

  groups.forEach((groupId, groupIndex) => {
    const angle = (Math.PI * 2 * groupIndex) / Math.max(groups.length, 1);
    const groupNodes = grouped.get(groupId);
    if (!groupNodes) return;
    const groupCenter = {
      x: centerX + Math.cos(angle) * radius,
      y: centerY + Math.sin(angle) * radius,
    };

    groupNodes.forEach((node, nodeIndex) => {
      const score = Number(node.data('score') || 1);
      const nodeRadius = score >= 5 ? radius * 0.12 : score >= 4 ? radius * 0.34 : radius * 0.62;
      const nodeAngle = angle + (Math.PI * 2 * nodeIndex) / Math.max(groupNodes.length, 1);
      node.position({
        x: score >= 5 ? centerX : groupCenter.x + Math.cos(nodeAngle) * nodeRadius,
        y: score >= 5 ? centerY : groupCenter.y + Math.sin(nodeAngle) * nodeRadius,
      });
    });
  });
}

export function runFullscreenLayout(cy: Core, onStop?: () => void) {
  cy.resize();
  seedGroupedPositions(cy);

  // 설명 위성 노드는 레이아웃 물리력(반발력 등) 계산에서 빼서, 실제 인물 노드
  // 배치가 눈에 안 보이는 라벨용 노드 때문에 왜곡되지 않게 한다.
  const layoutTargets = cy.elements().not('.node-caption');

  try {
    const layout = layoutTargets.layout(fcoseLayoutOptions());
    layout.one('layoutstop', () => {
      onStop?.();
    });
    layout.run();
  } catch (error) {
    console.error('Relationship graph fcose layout failed; using grid fallback.', error);
    const fallback = layoutTargets.layout(gridLayoutOptions());
    fallback.one('layoutstop', () => {
      onStop?.();
    });
    fallback.run();
  }
}
