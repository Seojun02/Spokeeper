"""시점·근거 자동 점검: 관계 설명의 핵심 단어와 근거 문장이 '그 시점까지의 본문'에 실제로 있는지 검사한다.

- 시점 오류(anachronism): 설명에 쓴 단어가 해당 챕터 이후에야 처음 본문에 나옴  (예: 3장 항목에 '비서')
- 근거 없음: 단어가 본문 어디에도 없음(환각·의역), 또는 근거 문장이 비었거나 본문에 없음
어휘 일치 기반이라 동의어 의역은 오탐일 수 있으므로 '자동 확정'이 아니라 '사람이 볼 후보 추림'용이다.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.argv = sys.argv[:1]
import compare_models as c  # noqa: E402
import score_scarlet as s  # noqa: E402

CH = c.get_chapters("S")
NORM = lambda t: re.sub(r"\s+", "", t)
TXT = [NORM(x["text"]) for x in CH]
STOP = set("관계 사이 인물 처음 명시 아직 미명시 핵심 시점 허용 정도 대상 관련 연결 등장 본문 사건 현장 와의 에서 으로 하는 하게 되는 있는 없는 이다 및 그리고 후에 이후 먼저 함께 같은 다른 대한 위한 통해 때문".split())
PART = "은는이가을를과와의에로도만에서으로"


def tokens(label: str):
    out = []
    for w in re.findall(r"[가-힣]{2,}", label or ""):
        while len(w) > 2 and w[-1] in PART:
            w = w[:-1]
        if w not in STOP and len(w) >= 2:
            out.append(w)
    return out


def first_chapter(word: str):
    for i, t in enumerate(TXT, 1):
        if word in t:
            return i
    return None


def check(label: str, upto: int, evidence: str = ""):
    """반환: (시점오류 단어들, 본문에 전혀 없는 단어들, 근거문장 문제)"""
    ana, absent = [], []
    for w in tokens(label):
        fc = first_chapter(w)
        if fc is None:
            absent.append(w)
        elif fc > upto:
            ana.append(f"{w}(첫 등장 {fc}장)")
    ev_bad = ""
    if evidence is not None:
        if not evidence.strip():
            ev_bad = "근거 비어 있음"
        else:
            frags = [NORM(f) for f in re.split(r"\.\.\.|/|\n", evidence) if len(NORM(f)) >= 10]
            body = "".join(TXT[:upto])
            if frags and not any(f[:40] in body for f in frags):
                ev_bad = "근거 문장이 본문에 없음"
    return ana, absent, ev_bad


def main():
    print("=== 1) 정답표 라벨 점검 (각 항목의 ch 시점 기준) ===")
    n = 0
    for r in s.GT["relations"]:
        ana, absent, _ = check(r["label"], r["ch"], evidence=None)
        if ana:
            n += 1
            print(f"  [시점 의심] ch{r['ch']} {r['a']}-{r['b']} '{r['label']}' → {', '.join(ana)}")
    print(f"  → 시점 의심 {n}건 (정답표 {len(s.GT['relations'])}건 중)\n")

    print("=== 2) 모델 출력 점검: 자동 점검이 '오류 판정 관계'를 얼마나 잡아내는가 ===")
    wrong = {frozenset((w["a"], w["b"])) for w in s.GT["wrong"]}
    for m in ["solar-pro3", "solar-pro4"]:
        tp = fn = fp = tn = 0
        examples = []
        for i in range(1, 15):
            e = json.loads((s.CACHE / f"{m}_s{i}.json").read_text(encoding="utf-8"))
            _, _, rel, _, _ = s.gt_upto(i)
            for x in e["relations"]:
                a, b = s.resolve(x.get("source", "")), s.resolve(x.get("target", ""))
                if not a or not b or a == b:
                    continue
                q = frozenset((a, b))
                lab = "wrong" if q in wrong else ("right" if q in rel else None)
                if not lab:
                    continue
                ana, absent, ev = check(x.get("relation", ""), i, x.get("evidence") or "")
                flagged = bool(ana or ev)
                if lab == "wrong":
                    tp += flagged; fn += (not flagged)
                    if flagged and len(examples) < 3:
                        examples.append(f"오프셋{i} {a}-{b} '{x.get('relation')}' → {ev or ana}")
                else:
                    fp += flagged; tn += (not flagged)
        print(f"{m}: 오류 관계 {tp + fn}건 중 자동 적발 {tp}건 ({tp / max(1, tp + fn):.0%}) | 맞는 관계 {fp + tn}건 중 오탐 {fp}건 ({fp / max(1, fp + tn):.0%})")
        for ex in examples:
            print("    예:", ex)


if __name__ == "__main__":
    main()
