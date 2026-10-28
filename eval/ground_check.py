"""근거 인용 검증(LLM 호출 없음): 관계의 evidence 가 '그 오프셋까지의 본문'에 실제로 있는지 조각 단위 퍼지 매칭으로 확인.

- evidence 를 '...' '/' 줄바꿈으로 조각내고, 10자 이상 조각마다 본문과 비교
- 완전 일치(공백·문장부호 무시) 또는 글자 4-gram 이 85% 이상 본문에 존재하면 '근거 있음'
- 관계는 '근거 조각이 하나도 확인되지 않거나 근거가 비면' 근거 없음(의심)으로 분류
※ 인용이 진짜인지만 본다. 인용을 과하게 해석한 경우(예: '비서')는 걸리지 않는다.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.argv = sys.argv[:1]
import compare_models as c  # noqa: E402
import score_scarlet as s  # noqa: E402

NORM = lambda t: re.sub(r"[\s\W_]+", "", t)
CH = [NORM(x["text"]) for x in c.get_chapters("S")]
GRAMS = []  # 챕터 누적 4-gram 집합
_acc = set()
for t in CH:
    _acc = _acc | {t[k:k + 4] for k in range(len(t) - 3)}
    GRAMS.append(_acc)
BODY = ["".join(CH[:i]) for i in range(1, len(CH) + 1)]


def fragments(evidence: str):
    return [NORM(f) for f in re.split(r"\.\.\.|…|/|\n", evidence or "") if len(NORM(f)) >= 10]


def grounded(evidence: str, upto: int, thr: float = 0.85) -> bool:
    frags = fragments(evidence)
    if not frags:
        return False
    for f in frags:
        if f in BODY[upto - 1]:
            return True
        grams = [f[k:k + 4] for k in range(len(f) - 3)]
        if grams and sum(g in GRAMS[upto - 1] for g in grams) / len(grams) >= thr:
            return True
    return False


def main(offsets=(2, 4, 6, 7, 9, 11, 14)):
    wrong = {frozenset((w["a"], w["b"])) for w in s.GT["wrong"]}
    for m in ["solar-pro3", "solar-pro4"]:
        for thr in (0.85, 0.7):
            tp = fn = fp = tn = 0
            miss_ex = []
            for i in offsets:
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
                    flagged = not grounded(x.get("evidence") or "", i, thr)
                    if lab == "wrong":
                        tp += flagged
                        fn += not flagged
                        if not flagged and len(miss_ex) < 2:
                            miss_ex.append(f"오프셋{i} {a}-{b} '{x.get('relation')}'")
                    else:
                        fp += flagged
                        tn += not flagged
            print(f"{m} (4-gram 임계 {thr}): 오류 관계 {tp + fn}건 중 적발 {tp}건({tp / max(1, tp + fn):.0%}) | 맞는 관계 {fp + tn}건 중 오탐 {fp}건({fp / max(1, fp + tn):.0%})")
            if thr == 0.85:
                for ex in miss_ex:
                    print("    놓친 오류 예:", ex)


if __name__ == "__main__":
    main()
