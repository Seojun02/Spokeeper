"""긴 문맥(주홍색, 최대 10만 자)에서 solar-decide가 맞는 관계와 틀린 관계를 구별하는지 검증.

각 모델(pro3/pro4)이 낸 관계를 오프셋별 누적 본문(state)과 함께 Decide에 yes/no로 물어 p_yes를 저장하고,
정답표 기준 '맞는 관계(rel)' vs '오류 판정 관계(wrong)'의 p_yes 분포를 비교한다.
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.argv = sys.argv[:1]
import compare_models as c  # noqa: E402
import score_scarlet as s  # noqa: E402

CH = c.get_chapters("S")
WRONG = {frozenset((w["a"], w["b"])) for w in s.GT["wrong"]}


def main():
    rows = []  # (model, offset, label, p_yes, relation text)
    for m in ["solar-pro3", "solar-pro4"]:
        for i in range(1, 15):
            e = json.loads((s.CACHE / f"{m}_s{i}.json").read_text(encoding="utf-8"))
            rels = e["relations"]
            path = s.CACHE / f"decide_{m}_s{i}.json"
            if path.exists():
                dec = json.loads(path.read_text(encoding="utf-8"))
            else:
                dec = c.decide_relations(c.cumulative_text(CH, i), rels)
                dec.pop("raw", None)
                path.write_text(json.dumps(dec, ensure_ascii=False), encoding="utf-8")
            _, _, rel, _, future = s.gt_upto(i)
            for k, x in enumerate(rels):
                a, b = s.resolve(x.get("source", "")), s.resolve(x.get("target", ""))
                if not a or not b or a == b:
                    continue
                q = frozenset((a, b))
                label = "wrong" if q in WRONG else ("right" if q in rel else None)
                if label:
                    rows.append((m, i, label, dec["answers"][str(k)]["p_yes"], x.get("relation")))
            print(f"[{m}] offset {i} 완료", flush=True)

    print("\n=== Decide p_yes 분포: 맞는 관계 vs 틀린 관계 ===")
    for m in ["solar-pro3", "solar-pro4"]:
        for lab in ["right", "wrong"]:
            ps = [r[3] for r in rows if r[0] == m and r[2] == lab]
            if ps:
                print(f"{m} {lab:5}: n={len(ps):>3}  평균 {statistics.mean(ps):.2f}  중앙값 {statistics.median(ps):.2f}  p<0.5 비율 {sum(p < .5 for p in ps) / len(ps):.0%}")
    allr = [r for r in rows if r[2] == "right"]
    allw = [r for r in rows if r[2] == "wrong"]
    print("\n임계값별 (전체: 맞는 관계 %d건, 틀린 관계 %d건)" % (len(allr), len(allw)))
    print("임계 | 틀린 관계 제거율 | 맞는 관계 보존율")
    for thr in [0.3, 0.5, 0.7, 0.9]:
        rm = sum(r[3] < thr for r in allw) / max(1, len(allw))
        keep = sum(r[3] >= thr for r in allr) / max(1, len(allr))
        print(f"{thr:>4} | {rm:>14.0%}   | {keep:>12.0%}")
    print("\n틀린 관계 중 Decide가 yes(>=0.5)로 통과시킨 것:")
    for r in sorted(allw, key=lambda r: -r[3])[:8]:
        print(f"  {r[0][6:]} 오프셋{r[1]} p_yes={r[3]:.2f} | {r[4]}")


if __name__ == "__main__":
    main()
