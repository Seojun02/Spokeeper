"""캐시된 추출 결과(eval/cache/S/<model>_s<i>.json)를 제품의 후속 에이전트 단계에 순서대로 통과시킨다.

 필터 → canonicalize(인물 병합) → verify(1차 가드) → ReminderWriter(2차) → IndirectLeakageJudge(3차) → Consolidation(전체 재병합)

모든 에이전트의 모델은 UPSTAGE_CHAT_MODEL 환경변수(= 인자 model)로 정한다. 제품 코드(precompute.py)의 상태 유지 방식
(canonical_registry / global_name_map / prev_raw_names)을 오프셋 순서대로 그대로 따른다.

사용: python eval/run_pipeline.py solar-pro3 [--all]
산출: eval/cache/S/pipe-<model>_s<i>.json   (병합+1차 가드까지)
      eval/cache/S/pipeC-<model>_s<i>.json  (+ 마지막에 Consolidation 병합 규칙을 모든 오프셋에 소급 적용)
"""
import json
import os
import sys
import time
from pathlib import Path

MODEL = sys.argv[1]
LIGHT = "--light" in sys.argv
DECIDE = "--decide" in sys.argv
HYBRID = "--hybrid" in sys.argv
ALL = "--all" in sys.argv
os.environ["UPSTAGE_CHAT_MODEL"] = MODEL  # agents.config import 전에 설정
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding="utf-8")

from agents.character_entity_filter import filter_generic_role_entities  # noqa: E402
from agents.consolidation_agent import consolidate_registry  # noqa: E402
from agents.indirect_leakage_judge import judge_reminders  # noqa: E402
from agents.reminder_writer_agent import write_reminders  # noqa: E402
from agents.verifier_agent import _apply_character_name_map, canonicalize_new_characters, verify_build_result  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache" / "S"
PREFIX = "lightH" if HYBRID else ("lightD" if DECIDE else "light")
OFFSETS = list(range(1, 15)) if ALL else [2, 4, 6, 7, 9, 11, 14]


def log(msg):
    print(f"[{MODEL}] {msg}", flush=True)


def timed(label, fn, t):
    t0 = time.time()
    out = fn()
    t[label] = round(time.time() - t0, 1)
    return out


def rename_snapshot(snap, merge_map, remove_names):
    """Consolidation 결과(별칭→대표, 제거 인물)를 한 스냅샷에 적용."""
    f = lambda n: merge_map.get(n, n)
    chars, seen = [], set()
    for c in snap["characters"]:
        n = f(c.get("name", ""))
        if n in remove_names or n in seen:
            continue
        seen.add(n)
        chars.append({**c, "name": n})
    rels, seen_r = [], set()
    for r in snap["relations"]:
        a, b = f(r.get("source", "")), f(r.get("target", ""))
        if a in remove_names or b in remove_names or a == b:
            continue
        k = (a, b, r.get("relation", ""))
        if k in seen_r:
            continue
        seen_r.add(k)
        rels.append({**r, "source": a, "target": b})
    return {**snap, "characters": chars, "relations": rels}


def main():
    registry, name_map, prev_raw = [], {}, set()
    snaps = {}
    for i in OFFSETS:
        t = {}
        ext = json.loads((CACHE / f"{MODEL}_s{i}.json").read_text(encoding="utf-8"))
        result = {"characters": ext["characters"], "relations": ext["relations"], "events": []}
        n_in = (len(result["characters"]), len(result["relations"]))
        result = filter_generic_role_entities(result)
        raw = result.get("characters", [])
        new = [c for c in raw if c.get("name", "") not in prev_raw]
        prev_raw.update(c.get("name", "") for c in raw)

        if HYBRID:
            import agents.decide_canonicalizer as dcn
            timed("decide_판별", lambda: dcn.classify_generic_names(new, registry), t)
            gone = dcn.pop_dropped_names(registry)
            result = dcn.drop_entities(result, gone)
            new = [c for c in new if c.get("name") not in gone]
            new_map, rename_map = timed("canonicalize", lambda: canonicalize_new_characters(new, registry), t)
        elif DECIDE:
            import agents.decide_canonicalizer as dcn
            new_map, rename_map = timed("canonicalize", lambda: dcn.canonicalize_new_characters(new, registry), t)
            result = dcn.drop_entities(result, dcn.pop_dropped_names(registry))
        else:
            new_map, rename_map = timed("canonicalize", lambda: canonicalize_new_characters(new, registry), t)
        name_map.update(new_map)
        if rename_map:
            for raw_n, mapped in list(name_map.items()):
                if mapped in rename_map:
                    name_map[raw_n] = rename_map[mapped]
            name_map.update(rename_map)
        if name_map:
            result, _, _, _ = _apply_character_name_map(result, name_map)

        if LIGHT:
            import ground_check as gc
            rels = []
            for r in result.get("relations", []):
                ev = (r.get("evidence") or "").strip()
                if not ev:  # 근거가 비면 삭제(유일한 삭제 규칙)
                    continue
                rels.append({**r, "grounded": gc.grounded(ev, i)})  # 근거 인용 확인은 표시만
            verified = {**result, "relations": rels}
            snap = {"characters": verified.get("characters", []), "relations": rels, "events": [], "stage_seconds": t,
                    "counts": {"추출": n_in, "정리후": (len(verified.get("characters", [])), len(rels)),
                               "근거미확인표시": sum(not x["grounded"] for x in rels)}}
            snaps[i] = snap
            (CACHE / f"{PREFIX}-{MODEL}_s{i}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
            log(f"[경량] 오프셋 {i}: 인물/관계 {n_in} → {snap['counts']['정리후']} | 근거 미확인 표시 {snap['counts']['근거미확인표시']} | 초 {t}")
            continue
        verified = timed("verify", lambda: verify_build_result(result), t)
        n_ver = (len(verified.get("characters", [])), len(verified.get("relations", [])))

        written = timed("writer", lambda: write_reminders(verified), t)
        lines_w = written.get("lines", [])
        judged = timed("judge", lambda: judge_reminders(lines_w), t)

        snap = {
            "characters": verified.get("characters", []),
            "relations": verified.get("relations", []),
            "events": verified.get("events", []),
            "reminders_written": lines_w,
            "reminders_final": judged,
            "stage_seconds": t,
            "counts": {"추출": n_in, "검증후": n_ver, "리마인드 작성": len(lines_w), "판정후": len(judged)},
        }
        snaps[i] = snap
        (CACHE / f"pipe-{MODEL}_s{i}.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")
        log(f"오프셋 {i}: 인물/관계 {n_in} → 검증 후 {n_ver} | 리마인드 {len(lines_w)}→{len(judged)} | 단계별 초 {t}")

    if LIGHT:
        log("완료(경량)")
        return
    cons = timed("consolidation", lambda: consolidate_registry(registry), {})
    merge_map, remove = cons["merge_map"], cons["remove_names"]
    log(f"Consolidation: 병합 {len(merge_map)}건 {merge_map}, 제거 {sorted(remove)}")
    for i, snap in snaps.items():
        out = rename_snapshot(snap, merge_map, remove)
        (CACHE / f"pipeC-{MODEL}_s{i}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    log("완료")


if __name__ == "__main__":
    main()
