"""Decide 를 '근거 함의 판정기'로 사용: state 는 근거 문장 모음(짧음), 질문은 '이 근거가 관계 서술을 직접 뒷받침하는가'.

본문 전체를 읽지 않으므로 빠르고 싸다. 한 오프셋의 모든 관계를 한 번의 호출(질문 N개)로 묻는다.
정답표 기준 '맞는 관계'와 '오류 관계'의 p_yes 분포로 구별력을 본다.
"""
import json
import statistics
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.argv = sys.argv[:1]
import score_scarlet as s  # noqa: E402
from agents.config import UPSTAGE_API_KEY  # noqa: E402

import os
MODE = os.environ.get("DECIDE_MODE", "support")  # support: 뒷받침되는가 / error: 명백한 오류가 있는가
OFFS = [2, 4, 6, 7, 9, 11, 14]
WRONG = {frozenset((w["a"], w["b"])) for w in s.GT["wrong"]}


def ask(rels):
    state = "근거 모음(본문 발췌):\n" + "\n".join(f"[{k + 1}] {(r.get('evidence') or '(근거 없음)')}" for k, r in enumerate(rels))
    qs = {}
    for k, r in enumerate(rels):
        if MODE == "error":
            qs[f"r{k}"] = {
                "type": "choice",
                "instructions": (
                    f"근거 [{k + 1}]에 비추어, '{r.get('source')}'와(과) '{r.get('target')}'의 관계가 '{r.get('relation')}'이라는 서술에 "
                    "명백한 오류가 있습니까? (인물이 뒤바뀜, 근거에 반하는 내용, 근거에 없는 신분·행위를 단정한 경우만 yes. "
                    "표현이 다르거나 요약일 뿐이면 no)"
                ),
                "criteria": {"yes": "명백한 오류가 있다.", "no": "큰 문제가 없다."},
            }
            continue
        qs[f"r{k}"] = {
            "type": "choice",
            "instructions": (
                f"근거 [{k + 1}]만 읽고 판단하세요. '{r.get('source')}'와(과) '{r.get('target')}'의 관계가 "
                f"'{r.get('relation')}'이라는 서술이 근거 [{k + 1}]의 내용으로 직접 뒷받침됩니까? "
                "근거에 없는 사실(직업·신분·행위)을 덧붙였거나 인물이 뒤바뀌었으면 no."
            ),
            "criteria": {"yes": "근거가 서술을 직접 뒷받침한다.", "no": "근거에 없는 내용이 더해졌거나 근거와 맞지 않는다."},
        }
    for attempt in range(7):
        resp = requests.post("https://api.upstage.ai/v1/systemone", headers={"Authorization": f"Bearer {UPSTAGE_API_KEY}"},
                             json={"model": "solar-decide", "state": state, "questions": qs}, timeout=170)
        if resp.status_code not in (429, 500, 502, 503, 504) or attempt == 6:
            break
        print(f"  HTTP {resp.status_code}, 재시도", flush=True)
        time.sleep(10 * 2 ** attempt)
    resp.raise_for_status()
    ans = resp.json()["answers"]
    return [ans[f"r{k}"]["probabilities"].get("yes", 0.0) for k in range(len(rels))]  # error 모드에서는 p_yes = 오류 확률


def main():
    rows = []
    for m in ["solar-pro3", "solar-pro4"]:
        for i in OFFS:
            snap = json.loads((s.CACHE / f"light-{m}_s{i}.json").read_text(encoding="utf-8"))
            rels = snap["relations"]
            path = s.CACHE / (f"entail-{m}_s{i}.json" if MODE == "support" else f"entailerr-{m}_s{i}.json")
            if path.exists():
                ps = json.loads(path.read_text(encoding="utf-8"))
            else:
                t0 = time.time()
                ps = ask(rels)
                path.write_text(json.dumps(ps), encoding="utf-8")
                print(f"[{m}] 오프셋 {i}: 관계 {len(rels)}개 판정 {time.time() - t0:.1f}s", flush=True)
            _, _, rel, _, _ = s.gt_upto(i)
            for r, p in zip(rels, ps):
                a, b = s.resolve(r.get("source", "")), s.resolve(r.get("target", ""))
                if not a or not b or a == b:
                    continue
                q = frozenset((a, b))
                lab = "wrong" if q in WRONG else ("right" if q in rel else None)
                if lab:
                    rows.append((m, i, lab, p, f"{a}-{b} '{r.get('relation')}'"))
    print("\n=== 근거 함의 판정(Decide) p_yes: 맞는 관계 vs 오류 관계 ===")
    for m in ["solar-pro3", "solar-pro4"]:
        R = [r for r in rows if r[0] == m and r[2] == "right"]
        W = [r for r in rows if r[0] == m and r[2] == "wrong"]
        print(f"\n{m}: 맞는 관계 {len(R)}건(중앙값 p_yes {statistics.median([r[3] for r in R]):.2f}), 오류 관계 {len(W)}건" +
              (f"(중앙값 {statistics.median([r[3] for r in W]):.2f})" if W else ""))
        print("  임계 | 오류 관계 제거율 | 맞는 관계 보존율")
        for thr in (0.3, 0.5, 0.7, 0.9):
            rm = sum(r[3] < thr for r in W) / max(1, len(W))
            keep = sum(r[3] >= thr for r in R) / max(1, len(R))
            print(f"  {thr:>4} | {rm:>12.0%}    | {keep:>10.0%}")
    def auc(pos, neg):  # pos 점수가 neg 보다 클 확률
        return sum((a > b) + 0.5 * (a == b) for a in pos for b in neg) / max(1, len(pos) * len(neg))
    print("\n구별력(AUC, 0.5=무작위, 1.0=완벽):")
    for m in ["solar-pro3", "solar-pro4"]:
        R = [r[3] for r in rows if r[0] == m and r[2] == "right"]
        W = [r[3] for r in rows if r[0] == m and r[2] == "wrong"]
        if len(W) >= 2:
            val = auc(W, R) if MODE == "error" else auc(R, W)
            print(f"  {m}: AUC {val:.2f} (오류 {len(W)}건 vs 정상 {len(R)}건)")
        else:
            print(f"  {m}: 오류 관계가 {len(W)}건뿐이라 AUC 계산 불가")
    allw = sorted([r for r in rows if r[2] == "wrong"], key=lambda r: r[3])
    print("\n가장 낮게(=잘 걸러진) 판정된 오류 관계 / 높게(=놓친) 판정된 오류 관계:")
    for r in allw[:3] + allw[-3:]:
        print(f"  {r[0][6:]} 오프셋{r[1]} p_yes={r[3]:.2f} {r[4]}")
    allr = sorted([r for r in rows if r[2] == "right"], key=lambda r: r[3])
    print("\n맞는 관계인데 낮게 판정된 것(오삭제 위험) 3건:")
    for r in allr[:3]:
        print(f"  {r[0][6:]} 오프셋{r[1]} p_yes={r[3]:.2f} {r[4]}")


if __name__ == "__main__":
    main()
