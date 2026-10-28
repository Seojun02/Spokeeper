// EPUB(압축 해제된 디렉토리)에서 챕터/문단별 CFI 인덱스를 생성한다.
//
// 사용법: node build_cfi_index.js <unpacked_epub_dir> <output.json>
// <unpacked_epub_dir> 은 content.opf가 있는 디렉토리(또는 그 상위, 재귀 탐색함)를 가리킨다.
//
// 셜록 홈즈 EPUB 전용이던 원본 스크립트를 일반화: 'div.chapter' 래퍼가 없는 EPUB도
// 처리할 수 있도록 문서 body 전체의 <p>를 대상으로 하는 폴백을 추가했다.
//
// 일부 EPUB(특히 국내 웹소설 변환본)은 실제 문단마다 <p>를 쓰지 않고, 챕터 전체를
// <p> 하나에 담고 <br/>로만 줄바꿈한다. 이런 경우 실제 <p> 개수가 항상 1이라
// "표지/목차 스킵" 휴리스틱(문단 3개 미만이면 챕터 아님)에 걸려 챕터 전체가
// 통째로 스킵되므로, 그 경우 <p> 내부 텍스트 노드를 문단 단위로 취급하는 폴백을 둔다.
const fs = require('fs');
const path = require('path');
const { JSDOM } = require('jsdom');
const CFI = require('epub-cfi-resolver');

const inputDir = process.argv[2];
const outputPath = process.argv[3];

if (!inputDir || !outputPath) {
  console.error('사용법: node build_cfi_index.js <unpacked_epub_dir> <output.json>');
  process.exit(1);
}

function findOpfPath(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const found = findOpfPath(full);
      if (found) return found;
    } else if (entry.name.toLowerCase().endsWith('.opf')) {
      return full;
    }
  }
  return null;
}

const OPF_PATH = findOpfPath(inputDir);
if (!OPF_PATH) {
  console.error(`content.opf를 찾을 수 없습니다: ${inputDir}`);
  process.exit(1);
}
const EPUB_DIR = path.dirname(OPF_PATH);

const opfXml = fs.readFileSync(OPF_PATH, 'utf-8');
const opfDom = new JSDOM(opfXml, { contentType: 'application/xml' });
const opfDoc = opfDom.window.document;

const spineEl = opfDoc.querySelector('spine');
const itemrefs = Array.from(spineEl.querySelectorAll('itemref'));
const manifestHrefById = {};
const manifestTypeById = {};
opfDoc.querySelectorAll('manifest item').forEach(item => {
  manifestHrefById[item.getAttribute('id')] = item.getAttribute('href');
  manifestTypeById[item.getAttribute('id')] = item.getAttribute('media-type');
});

function cfiToPath(cfi) {
  let inner = cfi.trim().replace(/^epubcfi\((.*)\)$/, '$1');
  inner = inner.replace(/\[[^\]]*\]/g, '');
  const bangIndex = inner.indexOf('!');
  if (bangIndex >= 0) {
    const packagePath = inner.slice(0, bangIndex + 1);
    // epub-cfi-resolver는 content path를 !/2/4/...로 생성하지만 epub.js의
    // relocated 이벤트는 같은 위치를 !/4/...로 보고한다. document-root 단계
    // /2를 제거해 런타임 CFI와 동일한 정렬 키를 저장한다.
    const contentPath = inner.slice(bangIndex + 1).replace(/^\/2(?=\/4(?:\/|$))/, '');
    inner = packagePath + contentPath;
  }
  inner = inner.replace(/!/g, '/');
  const steps = [];
  for (const token of inner.split('/')) {
    if (!token) continue;
    if (token.includes(':')) {
      const [step, offset] = token.split(':');
      steps.push(parseInt(step, 10));
      steps.push(parseInt(offset, 10));
    } else {
      steps.push(parseInt(token, 10));
      steps.push(0);
    }
  }
  return steps;
}

const allRows = [];
let chapterCounter = 0;

itemrefs.forEach((itemrefNode) => {
  const idref = itemrefNode.getAttribute('idref');
  const href = manifestHrefById[idref];
  const mediaType = manifestTypeById[idref];
  if (!href || mediaType !== 'application/xhtml+xml') return;

  const filePath = path.join(EPUB_DIR, decodeURIComponent(href));
  if (!fs.existsSync(filePath)) return;

  const html = fs.readFileSync(filePath, 'utf-8');
  const dom = new JSDOM(html, { contentType: 'application/xhtml+xml' });
  const doc = dom.window.document;

  // 원문 구조에 'div.chapter' 래퍼가 있으면 그걸, 없으면 body 전체를 대상으로 한다.
  const container = doc.querySelector('div.chapter') || doc.body;
  if (!container) return;

  // <p> 태그 자체가 문단 단위인 일반적인 경우와, <p> 하나에 <br/>로만 줄바꿈된
  // 경우를 모두 다룬다 — 각 <p>의 자식 텍스트 노드를 전부 모으면, 후자에서는
  // <br/> 사이사이의 텍스트 노드가 자연히 별도 문단으로 잡힌다.
  const paragraphTextNodes = [];
  Array.from(container.querySelectorAll('p')).forEach((p) => {
    Array.from(p.childNodes).forEach((child) => {
      if (child.nodeType === 3 && child.textContent && child.textContent.trim()) {
        paragraphTextNodes.push(child);
      }
    });
  });
  if (paragraphTextNodes.length < 3) return; // 목차/표지 등 스킵

  const heading = container.querySelector('h1, h2, h3');
  const chapterTitle = heading
    ? heading.textContent.trim().replace(/\s+/g, ' ')
    : `chapter_${chapterCounter}`;

  paragraphTextNodes.forEach((textNode, paraIdx) => {
    try {
      const cfiRaw = CFI.generate([
        { node: itemrefNode, offset: 0 },
        { node: textNode, offset: 0 }
      ]);
      const cfiPath = cfiToPath(cfiRaw);
      allRows.push({
        chapter_index: chapterCounter,
        chapter_title: chapterTitle,
        paragraph_index: paraIdx,
        cfi_raw: cfiRaw,
        cfi_path: cfiPath,
        text_preview: textNode.textContent.trim().slice(0, 60)
      });
    } catch (e) {
      console.error(`생성 실패 (chapter=${chapterCounter}, para=${paraIdx}): ${e.message}`);
    }
  });

  console.log(`챕터 ${chapterCounter} [${chapterTitle}] - 문단 ${paragraphTextNodes.length}개 처리 (spine idref=${idref})`);
  chapterCounter++;
});

console.log(`\n총 ${allRows.length}개 문단 CFI 생성 완료 (챕터 ${chapterCounter}개)`);

fs.writeFileSync(outputPath, JSON.stringify(allRows, null, 0));
console.log(`${outputPath} 작성 완료`);
