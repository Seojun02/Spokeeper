"""동일 인물 판정 비교: 기존 LLM(JSON 생성, solar-pro4) vs Decide(분류, 임계값 0.5/0.7/0.9).

입력: 각 모델(pro3/pro4)의 오프셋별 추출 결과에서 나온 인물 이름·설명(캐시)을 오프셋 순서대로 흘려 넣는다(제품과 같은 증분 방식).
정답: 이름이 같은 정답표 인물로 해석되는 원본 표기끼리는 '같은 인물'(score_scarlet.resolve, 해석 불가·일반명사는 제외).
지표: 원본 표기 쌍 단위의 병합 정밀도/재현율/F1, 호출 수, 소요 시간.
"""
import itertools
import json
import os
import sys
import time
from pathlib import Path

os.environ["UPSTAGE_CHAT_MODEL"] = "solar-pro4"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.argv = sys.argv[:1]

import agents.decide_canonicalizer as dc  # noqa: E402
import agents.verifier_agent as va  # noqa: E402
import score_scarlet as s  # noqa: E402
from agents.character_entity_filter import filter_generic_role_entities  # noqa: E402

OFFS = [2, 4, 6, 7, 9, 11, 14]
LLM = {"calls": 0, "seconds": 0.0}
_orig = va.invoke_with_retry


def _counted(*a, **k):
    t0 = time.time()
    try:
        return _orig(*a, **k)
    finally:
        LLM["calls"] += 1
        LLM["seconds"] += time.time() - t0


va.invoke_with_retry = _counted
dc._CACHE = {}


def run(model, fn):
    registry, name_map, prev_raw, raws = [], {}, set(), []
    for i in OFFS:
        ext = json.loads((s.CACHE / f"{model}_s{i}.json").read_text(encoding="utf-8"))
        res = filter_generic_role_entities({"characters": ext["characters"], "relations": [], "events": []})
        raw = res.get("characters", [])
        new = [c for c in raw if c.get("name", "") not in prev_raw]
        prev_raw.update(c.get("name", "") for c in raw)
        raws += [c["name"] for c in new]
        new_map, rename_map = fn(new, registry)
        name_map.update(new_map)
        if rename_map:
            for r, m in list(name_map.items()):
                if m in rename_map:
                    name_map[r] = rename_map[m]
            name_map.update(rename_map)
    return name_map, raws


def evaluate(name_map, raws):
    names = [n for n in dict.fromkeys(raws) if s.resolve(n)]
    tp = fp = fn = 0
    errs_fp, errs_fn = [], []
    for a, b in itertools.combinations(names, 2):
        true = s.resolve(a) == s.resolve(b)
        pred = name_map.get(a, a) == name_map.get(b, b)
        if true and pred:
            tp += 1
        elif pred and not true:
            fp += 1
            errs_fp.append(f"{a} = {b}")
        elif true and not pred:
            fn += 1
            errs_fn.append(f"{a} ≠ {b}")
    P = tp / max(1, tp + fp)
    R = tp / max(1, tp + fn)
    return P, R, 2 * P * R / max(1e-9, P + R), len(names), errs_fp, errs_fn


def main():
    for model in ["solar-pro4", "solar-pro3"]:
        print(f"\n===== 입력: {model} 추출 결과의 인물 이름 =====")
        print(f"{'방식':<22}{'병합 정밀도':>10}{'재현율':>8}{'F1':>7}{'호출':>6}{'시간(s)':>9}")
        rows = []
        LLM.update(calls=0, seconds=0.0)
        nm, raws = run(model, lambda n, r: va.canonicalize_new_characters(n, r))
        rows.append(("기존 LLM(pro4)", evaluate(nm, raws), LLM["calls"], LLM["seconds"]))
        for thr in (0.5, 0.7, 0.9):
            dc.SAME_THRESHOLD = thr
            dc.STATS.update(calls=0, seconds=0.0)
            nm, raws = run(model, lambda n, r: dc.canonicalize_new_characters(n, r))
            rows.append((f"Decide(임계 {thr})", evaluate(nm, raws), dc.STATS["calls"], dc.STATS["seconds"]))
        for name, (P, R, F, n, efp, efn), calls, sec in rows:
            print(f"{name:<22}{P:>10.0%}{R:>8.0%}{F:>7.2f}{calls:>6}{sec:>9.1f}")
        print(f"  (정답표로 해석되는 원본 표기 {rows[0][1][3]}개 → 쌍 {rows[0][1][3] * (rows[0][1][3] - 1) // 2}개 비교)")
        for name, (P, R, F, n, efp, efn), _, _ in (rows[0], rows[2]):
            print(f"  [{name}] 잘못 합친 쌍: {efp[:5] or '없음'} | 못 합친 쌍: {efn[:5] or '없음'}")


if __name__ == "__main__":
    main()
