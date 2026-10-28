export function nodeSize(score: number) {
  if (score >= 5) return 86;
  if (score >= 4) return 74;
  if (score >= 3) return 62;
  if (score >= 2) return 54;
  return 48;
}

export function nodeBorderWidth(score: number) {
  if (score >= 5) return 2;
  if (score >= 4) return 1.75;
  if (score >= 3) return 1.5;
  return 1.25;
}

export const nodeStyles = [
  {
    selector: 'node',
    style: {
      display: 'element',
      visibility: 'visible',
      opacity: 1,
      width: 'data(size)',
      height: 'data(size)',
      shape: 'ellipse',
      'background-color': '#ffffff',
      'background-opacity': 0.98,
      'outline-color': 'data(color)',
      'outline-width': 3,
      'outline-offset': 1,
      'outline-opacity': 1,
      'border-color': '#ffffff',
      'border-width': 3,
      'border-position': 'inside',
      'bounds-expansion': 16,
      // 이름만 원 중심에 넣는다(설명은 별도의 위성 노드로 그 위에 따로 붙는다 —
      // makeElements의 node-caption, 아래 '.node-caption' 스타일 참고). 흰 배경
      // 박스는 지웠다 — 원 색 위에 글자만 바로 얹는다.
      label: 'data(label)',
      color: '#1e293b',
      'font-size': 12,
      'font-weight': 900,
      'text-valign': 'center',
      'text-halign': 'center',
      'text-wrap': 'wrap',
      'text-max-width': 'data(size)',
      'overlay-opacity': 0,
      'shadow-blur': 10,
      'shadow-color': 'data(color)',
      'shadow-opacity': 0.18,
      'shadow-offset-x': 0,
      'shadow-offset-y': 4,
      'underlay-color': 'data(color)',
      'underlay-opacity': 0.06,
      'underlay-padding': 3,
      'underlay-shape': 'ellipse',
      'z-index': 10,
      'transition-property': 'opacity, background-opacity, border-width, border-color, width, height, underlay-opacity, underlay-padding',
      'transition-duration': '300ms',
    },
  },
  {
    selector: 'node[score >= 5]',
    style: {
      'shadow-blur': 26,
      'shadow-color': 'data(borderColor)',
      'shadow-opacity': 0.45,
      'z-index': 18,
    },
  },
  {
    selector: 'node[score <= 2]',
    style: {
      opacity: 0.72,
      'font-size': 10,
      'shadow-opacity': 0.08,
    },
  },
  // 사망이 확인된 인물(characterStatus.isDeceased) — 채움을 더 흐릿하게 하고 테두리를
  // 점선으로 바꿔서 "더 이상 이야기 안에 없는 사람"이라는 게 한눈에 보이게 한다.
  // 이름 앞에 "故"도 붙는다(makeElements 참고).
  {
    selector: 'node.deceased',
    style: {
      'background-opacity': 0.45,
      'border-style': 'dashed',
      'shadow-opacity': 0.06,
    },
  },
  {
    selector: 'node.hovered',
    style: {
      'shadow-blur': 18,
      'shadow-opacity': 0.34,
      'underlay-color': 'data(color)',
      'underlay-opacity': 0.16,
      'underlay-padding': 7,
      'underlay-shape': 'ellipse',
      'transition-duration': '200ms',
      'z-index': 30,
    },
  },
  {
    selector: 'node.focused',
    style: {
      opacity: 1,
      'z-index': 40,
      'underlay-color': 'data(color)',
      'underlay-opacity': 0.3,
      'underlay-padding': 10,
      'underlay-shape': 'ellipse',
      'shadow-opacity': 0.32,
      'shadow-offset-y': 9,
      'transition-duration': '200ms',
    },
  },
  {
    selector: 'node.neighbor',
    style: {
      opacity: 0.95,
      'z-index': 25,
      'underlay-color': 'data(color)',
      'underlay-opacity': 0.1,
      'underlay-padding': 4,
      'underlay-shape': 'ellipse',
      'transition-duration': '200ms',
    },
  },
  {
    selector: '.matched',
    style: {
      'border-color': '#f59e0b',
      'border-width': 2.5,
      'shadow-color': '#f59e0b',
      'shadow-opacity': 0.4,
    },
  },
  {
    selector: '.group-highlight',
    style: {
      opacity: 1,
      'z-index': 22,
      'border-color': 'data(borderColor)',
      'border-width': 2.25,
    },
  },
  {
    selector: '.group-muted',
    style: {
      opacity: 0.16,
    },
  },
  {
    selector: 'node.faded',
    style: {
      opacity: 0.45,
      'transition-duration': '200ms',
    },
  },
  // 설명(직업 등) 전용 위성 노드 — 원도 테두리도 그림자도 없이 텍스트만 보이는
  // 투명한 점 하나다. 본체 노드 바로 위에 위치가 계속 동기화된다
  // (FullscreenRelationshipGraph의 syncCaptionPosition 참고). 흰 배경 박스 없이
  // 캔버스 배경(연한 회색) 위에 바로 글자만 얹는다.
  {
    selector: '.node-caption',
    style: {
      width: 1,
      height: 1,
      'background-opacity': 0,
      'border-width': 0,
      'shadow-opacity': 0,
      events: 'no',
      label: 'data(label)',
      color: '#475569',
      'font-size': 10,
      'font-weight': 600,
      'text-valign': 'center',
      'text-halign': 'center',
      'text-wrap': 'wrap',
      'text-max-width': 100,
      'z-index': 3,
    },
  },
  {
    selector: 'node.new-node',
    style: {
      opacity: 0,
      'underlay-color': 'data(color)',
      'underlay-opacity': 0.18,
      'underlay-padding': 5,
      'transition-duration': '300ms',
    },
  },
];
