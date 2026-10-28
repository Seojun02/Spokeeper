import type cytoscape from 'cytoscape';

export const CATEGORY_COLOR: Record<string, string> = {
  ally: '#16a34a',
  family: '#2563eb',
  investigation: '#0284c7',
  conflict: '#dc2626',
  crime: '#991b1b',
  romance: '#db2777',
  deception: '#7c3aed',
  protection: '#0f766e',
  work: '#f97316',
  mystery: '#d97706',
  neutral: '#64748b',
};

export const edgeStyles = [
  {
    selector: 'edge',
    style: {
      width: 3,
      opacity: 'data(opacity)',
      'line-color': 'data(color)',
      'target-arrow-color': 'data(color)',
      'target-arrow-shape': (edge: cytoscape.SingularElementArgument) =>
        edge.data('directed') ? 'triangle' : 'none',
      'arrow-scale': 1.1,
      'curve-style': 'data(curveStyle)',
      'control-point-distances': 'data(controlPointDistance)',
      'control-point-weights': 0.5,
      label: 'data(visibleLabel)',
      color: '#334155',
      'font-size': 10,
      'font-weight': 800,
      'text-rotation': 'none',
      'text-margin-y': 18,
      'text-background-color': '#ffffff',
      'text-background-opacity': 1,
      'text-background-padding': 4,
      'text-background-shape': 'roundrectangle',
      'overlay-opacity': 0,
      'z-index': 4,
      'transition-property': 'opacity, width, line-color, text-opacity',
      'transition-duration': '300ms',
    },
  },
  {
    selector: 'edge[majorLabel = "true"]',
    style: {
      'text-opacity': 1,
      width: 3,
      opacity: 0.82,
    },
  },
  {
    selector: 'edge.hovered',
    style: {
      width: 4,
      opacity: 1,
      label: 'data(label)',
      'text-background-opacity': 1,
      'text-background-padding': 4,
      'font-size': 11,
      'z-index': 35,
    },
  },
  {
    selector: 'edge.focused',
    style: {
      width: 5,
      opacity: 1,
      label: 'data(label)',
      'z-index': 38,
    },
  },
  {
    selector: 'edge.faded',
    style: {
      opacity: 0.1,
    },
  },
  {
    selector: 'edge.group-highlight',
    style: {
      width: 4,
      opacity: 0.92,
    },
  },
  {
    selector: 'edge.group-muted',
    style: {
      opacity: 0.08,
    },
  },
  // has_direct_evidence=false인 약한(추측성) 관계는 기본적으로 안 그린다 — 근거
  // 없는 연결로 그래프가 뒤덮이는 걸 막기 위함. 연결된 인물을 클릭(focus)하면
  // 그 인물에 한해서만 점선으로 드러난다(applyNodeFocus가 connectedEdges에
  // 'focused' 클래스를 주므로, 아래 두 번째 규칙이 나중에 선언되어 display를
  // 다시 켠다).
  {
    selector: 'edge.weak-edge',
    style: {
      display: 'none',
    },
  },
  {
    selector: 'edge.weak-edge.focused',
    style: {
      display: 'element',
      'line-style': 'dashed',
    },
  },
  {
    selector: 'edge.new-edge',
    style: {
      opacity: 0,
      'text-opacity': 0,
      'transition-duration': '350ms',
    },
  },
  {
    selector: 'edge.faded',
    style: {
      opacity: 0.42,
      'text-opacity': 0.55,
      'transition-duration': '200ms',
    },
  },
  {
    selector: 'edge.focused',
    style: {
      width: 4,
      opacity: 0.96,
      'text-opacity': 1,
      label: 'data(label)',
      'transition-duration': '200ms',
      'z-index': 38,
    },
  },
];
