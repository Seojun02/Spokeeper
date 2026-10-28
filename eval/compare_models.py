"""인물관계 추출 모델 비교 하니스.

변형(variant):
  pro2         : solar-pro2 단독           (기존 버전, 기준선)
  pro4         : solar-pro4 단독
  pro4_decide  : solar-pro4 추출 → solar-decide 가 누적 본문 전체를 보고 각 관계의 근거 여부를 판정, 부정이면 제거

solar-decide 는 텍스트를 생성하지 않는 분류 모델(POST /v1/systemone)이라 추출기가 아니라
"검증기"로만 쓸 수 있다. 입력 state 에는 해당 구간(챕터 1..i) 누적 본문만 넣으므로 스포일러 누출은 없다.

모든 LLM 응답은 eval/cache 에 저장되어 `score` 는 API 호출 없이 재실행/임계값 조정이 가능하다.

사용:
  python eval/compare_models.py gt
  python eval/compare_models.py run   --books 6,9 --variants pro2,pro4,pro4_decide
  python eval/compare_models.py score --books 6,9 --variants pro2,pro4,pro4_decide [--thr 0.5]
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from agents.parsers.epub_parser import parse_epub  # noqa: E402

DATA = ROOT / "backend" / "data"
CACHE = Path(__file__).resolve().parent / "cache"
BOOKS = {
    "6": ("6_봉인된_도서관의_열세_번째_열쇠_본문.epub", "6_봉인된_도서관의_열세_번째_열쇠_정답지.epub"),
    "9": ("9_설원_호텔의_마지막_투숙객_본문.epub", "9_설원_호텔의_마지막_투숙객_정답지.epub"),
}
SCARLET = Path(__file__).resolve().parent / "data" / "scarlet_chapters.json"
# 긴 책은 구간(오프셋)을 줄여 평가한다. S = 주홍색의 연구: 1부 끝(7장)·2부 도입(9장) 전후를 포함.
CHECKPOINTS = {"S": list(range(1, 15))}  # 14챕터 전부


def get_chapters(bid: str) -> list[dict]:
    if bid == "S":
        return json.loads(SCARLET.read_text(encoding="utf-8"))["chapters"]
    return parse_epub(DATA / BOOKS[bid][0])["chapters"]


def checkpoints(bid: str, n: int) -> list[int]:
    return CHECKPOINTS.get(bid, list(range(1, n + 1)))


EXTRACT_MODEL = {"pro2": "solar-pro2", "pro3": "solar-pro3", "pro4": "solar-pro4", "pro4_decide": "solar-pro4"}
ROLE_SUFFIX = ("형사", "기자", "관장", "사서", "경비원", "박사", "씨", "님")


# ───────────────────────── 정답지 파싱 ─────────────────────────
def parse_gt(path: Path) -> list[dict]:
    """[{page, chars:[{name, names:set}], rels:[(a, b, label)]}] — 구간별 누적."""
    text = parse_epub(path)["chapters"][0]["text"]
    sections, cur, mode = [], None, None
    for line in (l.strip() for l in text.splitlines() if l.strip()):
        m = re.match(r"1~(\d+)p 관계도", line)
        if m:
            cur = {"page": int(m.group(1)), "chars": [], "rels": []}
            sections.append(cur)
            continue
        if cur is None:
            continue
        if line.startswith("1)"):
            mode = "chars"
        elif line.startswith("2)"):
            mode = "rels"
        elif mode == "chars":
            m = re.match(r"^([^()]+?)\s*(?:\((.*)\))?$", line)
            name = m.group(1).strip()
            names = {name}
            for alias in (m.group(2) or "").split(","):
                alias = alias.strip()
                names.add(alias)
                names.update(t for t in alias.split() if len(t) >= 2)
            cur["chars"].append({"name": name, "names": {n for n in names if len(n) >= 2}})
        elif mode == "rels" and " - " in line and ":" in line:
            pair, label = line.split(":", 1)
            a, b = (x.strip() for x in pair.split(" - ", 1))
            cur["rels"].append((a, b, label.strip()))
    return sections


def check_gt():
    for bid, (body, gt) in BOOKS.items():
        secs = parse_gt(DATA / gt)
        chapters = parse_epub(DATA / body)["chapters"]
        assert len(secs) == len(chapters) == 10, (bid, len(secs), len(chapters))
        known = {c["name"] for c in secs[-1]["chars"]}
        for s in secs:
            for a, b, _ in s["rels"]:
                assert a in known and b in known, (bid, s["page"], a, b)
        print(f"[{bid}] 구간 {len(secs)} · 챕터 {len(chapters)} · 인물 {len(known)} · "
              f"관계(구간별) {[len(s['rels']) for s in secs]}")


# ───────────────────────── 추출 ─────────────────────────
def cumulative_text(chapters: list[dict], upto: int) -> str:
    return "\n\n".join(f"[chapter={c['chapter_index']}] {c['title']}\n{c['text']}" for c in chapters[:upto])


def extract(model: str, text: str, offset: int) -> dict:
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_upstage import ChatUpstage

    from agents.build_agent import BUILD_AGENT_SYSTEM_PROMPT, extract_json_from_text
    from agents.character_entity_filter import filter_generic_role_entities
    from agents.config import UPSTAGE_API_KEY
    from agents.llm_utils import invoke_with_retry

    factory = lambda: ChatUpstage(model=model, api_key=UPSTAGE_API_KEY, temperature=0, timeout=170)
    t0 = time.time()
    human = f"다음은 사용자가 현재까지 읽은 소설 본문입니다.\n\n현재 offset: {offset}\n\n본문:\n{text}\n\n" \
            "위 본문에서 확인된 인물, 관계, 사건만 추출하세요."
    for attempt in range(3):  # JSON 파싱 실패(parse_error)는 모델 출력 형식 불량이므로 최대 3회 재시도
        resp = invoke_with_retry(factory, [SystemMessage(content=BUILD_AGENT_SYSTEM_PROMPT), HumanMessage(content=human)])
        parsed = extract_json_from_text(resp.content)
        if not parsed.get("parse_error"):
            break
        print(f"[extract] {model} JSON 파싱 실패 ({attempt + 1}/3), 재시도", flush=True)
    out = filter_generic_role_entities({
        "characters": parsed.get("characters", []),
        "relations": parsed.get("relations", []),
        "events": [],
    })
    out["parse_error"] = parsed.get("parse_error", False)
    out["attempts"] = attempt + 1
    out["elapsed_sec"] = round(time.time() - t0, 1)
    if out["parse_error"]:
        out["raw_head"] = resp.content[:1500]
        out["raw_tail"] = resp.content[-1500:]
    out["usage"] = getattr(resp, "usage_metadata", None)
    return out


# ───────────────────────── solar-decide 검증 ─────────────────────────
def decide_relations(text: str, relations: list[dict]) -> dict:
    """관계마다 yes/no 질문을 만들어 한 번의 호출로 판정. {index: {p_yes, choice}} 반환."""
    import requests

    from agents.config import UPSTAGE_API_KEY

    if not relations:
        return {"answers": {}, "raw": None}
    questions = {}
    for i, r in enumerate(relations):
        questions[f"r{i}"] = {
            "type": "choice",
            "instructions": (
                f"본문에서 '{r.get('source')}'와(과) '{r.get('target')}' 사이에 "
                f"'{r.get('relation')}' 관계가 본문에 근거해 성립하는가? "
                "본문에 명시되거나 직접 확인되는 경우만 yes, 추측·과장·다른 인물과의 혼동이면 no."
            ),
            "criteria": {
                "yes": "본문 근거로 두 인물 사이에 해당 관계가 성립한다.",
                "no": "본문 근거가 없거나 관계가 틀렸다.",
            },
        }
    for attempt in range(7):  # 429/일시 오류는 지수 백오프로 재시도
        resp = requests.post(
            "https://api.upstage.ai/v1/systemone",
            headers={"Authorization": f"Bearer {UPSTAGE_API_KEY}"},
            json={"model": "solar-decide", "state": text, "questions": questions},
            timeout=170,
        )
        if resp.status_code not in (429, 500, 502, 503, 504) or attempt == 6:
            break
        wait = 10 * 2**attempt
        print(f"[decide] HTTP {resp.status_code}, {wait}s 대기 후 재시도 ({attempt + 1}/7)", flush=True)
        time.sleep(wait)
    resp.raise_for_status()
    raw = resp.json()
    answers = {}
    for i in range(len(relations)):
        a = raw["answers"][f"r{i}"]
        probs = a.get("probabilities") or {}
        choice = a.get("choice")
        p_yes = probs.get("yes", 1.0 if choice == "yes" else 0.0)
        answers[str(i)] = {"p_yes": p_yes, "choice": choice}
    return {"answers": answers, "raw": raw}


# ───────────────────────── 실행(캐시) ─────────────────────────
def cached(path: Path, fn):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    val = fn()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(val, ensure_ascii=False, indent=1), encoding="utf-8")
    return val


def run(books: list[str], variants: list[str]):
    from agents.llm_utils import get_usage_summary, reset_usage

    for bid in books:
        chapters = get_chapters(bid)
        for v in variants:
            reset_usage()
            for i in checkpoints(bid, len(chapters)):
                text = cumulative_text(chapters, i)
                ext = cached(CACHE / bid / f"{EXTRACT_MODEL[v]}_s{i}.json", lambda: extract(EXTRACT_MODEL[v], text, i))
                if v == "pro4_decide":
                    cached(CACHE / bid / f"decide_s{i}.json", lambda: decide_relations(text, ext["relations"]))
                print(f"[{bid}] {v} s{i}: 인물 {len(ext['characters'])} 관계 {len(ext['relations'])}"
                      f"{' PARSE_ERROR' if ext['parse_error'] else ''}")
            print(f"[{bid}] {v} 이번 실행 토큰/비용(solar-pro2 단가 기준 추정, 캐시 히트는 제외):", get_usage_summary())


# ───────────────────────── 채점 ─────────────────────────
def norm(s: str) -> str:
    s = re.sub(r"\s+", "", s)
    for suf in ROLE_SUFFIX:
        if s.endswith(suf) and len(s) > len(suf) + 1:
            s = s[: -len(suf)]
    return s


def match_char(pred: str, chars: list[dict]) -> str | None:
    p = norm(pred)
    exact = [c["name"] for c in chars if p in {norm(n) for n in c["names"]}]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return None
    loose = [c["name"] for c in chars if len(p) >= 2 and any(len(n) >= 3 and (norm(n) in p or p in norm(c["name"])) for n in c["names"])]
    return loose[0] if len(set(loose)) == 1 else None


def prf(tp, pred, gt):
    p = tp / pred if pred else 0.0
    r = tp / gt if gt else 0.0
    return round(p, 3), round(r, 3), round(2 * p * r / (p + r), 3) if p + r else 0.0


def score(books: list[str], variants: list[str], thr: float):
    rows = {v: {"c_tp": 0, "c_pred": 0, "c_gt": 0, "r_tp": 0, "r_pred": 0, "r_gt": 0, "leak": 0, "hall": 0,
                "unmatched": 0, "fin_tp": 0, "fin_gt": 0, "fin_pred": 0, "dropped": 0, "dropped_correct": 0}
            for v in variants}
    for bid in books:
        gt = parse_gt(DATA / BOOKS[bid][1])
        all_gt_pairs = [{frozenset((a, b)) for a, b, _ in s["rels"]} for s in gt]
        for v in variants:
            R = rows[v]
            for i, sec in enumerate(gt, start=1):
                ext = json.loads((CACHE / bid / f"{EXTRACT_MODEL[v]}_s{i}.json").read_text(encoding="utf-8"))
                rels = ext["relations"]
                if v == "pro4_decide":
                    dec = json.loads((CACHE / bid / f"decide_s{i}.json").read_text(encoding="utf-8"))["answers"]
                    kept = [r for k, r in enumerate(rels) if dec[str(k)]["p_yes"] >= thr]
                    R["dropped"] += len(rels) - len(kept)
                    rels = kept
                gt_names = {c["name"] for c in sec["chars"]}
                pred_names = {m for c in ext["characters"] if (m := match_char(c.get("name", ""), sec["chars"]))}
                R["c_tp"] += len(pred_names & gt_names)
                R["c_pred"] += len(ext["characters"])
                R["c_gt"] += len(gt_names)

                cur = all_gt_pairs[i - 1]
                future = set().union(*all_gt_pairs[i:]) if i < len(gt) else set()
                everything = set().union(*all_gt_pairs)
                matched = set()
                for r in rels:
                    a, b = match_char(r.get("source", ""), sec["chars"]), match_char(r.get("target", ""), sec["chars"])
                    if not a or not b or a == b:
                        R["unmatched"] += 1
                        continue
                    pair = frozenset((a, b))
                    if pair in matched:  # 같은 쌍의 중복 예측은 한 번만 센다
                        continue
                    matched.add(pair)
                    R["r_pred"] += 1
                    R["r_tp"] += pair in cur
                    R["leak"] += pair in future and pair not in cur
                    R["hall"] += pair not in everything
                R["r_gt"] += len(cur)
                if i == len(gt):
                    R["fin_tp"] += len(matched & cur)
                    R["fin_gt"] += len(cur)
                    R["fin_pred"] += len(matched)
    print(f"\n=== 결과 (책 {books}, decide 임계 p_yes≥{thr}) — 전 구간 micro / 최종구간 ===")
    hdr = f"{'variant':<13}{'인물P':>7}{'인물R':>7}{'관계P':>7}{'관계R':>7}{'관계F1':>7} | {'최종P':>6}{'최종R':>6}{'최종F1':>7} | {'누출':>5}{'환각':>5}{'미매칭':>6}{'제거':>5}"
    print(hdr)
    for v, R in rows.items():
        cp, cr, _ = prf(R["c_tp"], R["c_pred"], R["c_gt"])
        rp, rr, rf = prf(R["r_tp"], R["r_pred"], R["r_gt"])
        fp, fr, ff = prf(R["fin_tp"], R["fin_pred"], R["fin_gt"])
        print(f"{v:<13}{cp:>7}{cr:>7}{rp:>7}{rr:>7}{rf:>7} | {fp:>6}{fr:>6}{ff:>7} | "
              f"{R['leak']:>5}{R['hall']:>5}{R['unmatched']:>6}{R['dropped']:>5}")
    print("\n관계 P/R/F1 은 무방향 인물쌍 기준(라벨 문구는 자유서술이라 비교 제외). 누출=미래 구간 정답 관계를 미리 낸 수, 환각=어느 구간 정답에도 없음.")


HONORIFIC = re.compile(r"(씨|박사|경감|님|경|양|군)$")


def canon(name: str) -> str:
    """표기 흔들림 완화: 호칭 제거 후 마지막 토큰(성명의 이름 쪽)만 사용. 예) '제퍼슨 호프'→'호프'."""
    toks = HONORIFIC.sub("", re.sub(r"\s+", " ", (name or "").strip())).split()
    return toks[-1] if toks else ""


def diff(bid: str, a: str, b: str):
    """정답지 없이 두 모델의 오프셋별 추출 결과를 직접 비교(인물·관계쌍 집합)."""
    ma, mb = EXTRACT_MODEL[a], EXTRACT_MODEL[b]
    n = len(get_chapters(bid))
    print(f"\n=== {a} vs {b} · 책 {bid} · 구간(챕터까지 읽은 시점) ===")
    print(f"{'구간':>4} | {'인물 a':>6}{'b':>4}{'공통':>5}{'Jacc':>6} | {'관계 a':>6}{'b':>4}{'공통':>5}{'Jacc':>6} | {'시간(s) a':>9}{'b':>7} | {'파싱실패':>6}")
    last = None
    tot = {a: 0.0, b: 0.0}
    for i in checkpoints(bid, n):
        try:
            ea = json.loads((CACHE / bid / f"{ma}_s{i}.json").read_text(encoding="utf-8"))
            eb = json.loads((CACHE / bid / f"{mb}_s{i}.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue

        def sets(e):
            p = {canon(c.get("name", "")) for c in e["characters"]} - {""}
            r = set()
            for x in e["relations"]:
                s, t = canon(x.get("source", "")), canon(x.get("target", ""))
                if s and t and s != t:
                    r.add(frozenset((s, t)))
            return p, r

        pa, ra = sets(ea)
        pb, rb = sets(eb)
        jp = len(pa & pb) / max(1, len(pa | pb))
        jr = len(ra & rb) / max(1, len(ra | rb))
        tot[a] += ea.get("elapsed_sec", 0)
        tot[b] += eb.get("elapsed_sec", 0)
        err = f"{int(ea['parse_error'])}/{int(eb['parse_error'])}"
        print(f"{i:>4} | {len(pa):>6}{len(pb):>4}{len(pa & pb):>5}{jp:>6.2f} | {len(ra):>6}{len(rb):>4}{len(ra & rb):>5}{jr:>6.2f} | "
              f"{ea.get('elapsed_sec', 0):>9}{eb.get('elapsed_sec', 0):>7} | {err:>6}")
        last = (i, pa, pb, ra, rb)
    print(f"총 소요시간(초): {a} {tot[a]:.0f} · {b} {tot[b]:.0f}")
    if last:
        i, pa, pb, ra, rb = last
        fmt = lambda s: ", ".join(sorted("-".join(sorted(x)) for x in s))
        print(f"\n[최종 구간 {i}] {a}에만 있는 인물: {sorted(pa - pb)}\n[최종 구간 {i}] {b}에만 있는 인물: {sorted(pb - pa)}")
        print(f"[최종 구간 {i}] {a}에만 있는 관계쌍: {fmt(ra - rb)}\n[최종 구간 {i}] {b}에만 있는 관계쌍: {fmt(rb - ra)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gt", "run", "score", "diff"])
    ap.add_argument("--a", default="pro3")
    ap.add_argument("--b", default="pro4")
    ap.add_argument("--books", default="6,9")
    ap.add_argument("--variants", default="pro2,pro4,pro4_decide")
    ap.add_argument("--thr", type=float, default=0.5)
    a = ap.parse_args()
    books, variants = a.books.split(","), a.variants.split(",")
    {"gt": check_gt, "run": lambda: run(books, variants), "score": lambda: score(books, variants, a.thr),
     "diff": lambda: [diff(bk, a.a, a.b) for bk in books]}[a.cmd]()
