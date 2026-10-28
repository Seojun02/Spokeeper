"""주홍색 정답표(eval/data/scarlet_gt.json)로 오프셋별 채점. 정답은 '챕터 i까지 드러난 항목' 누적.

사용: python eval/score_scarlet.py [--models solar-pro3,solar-pro4]
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
GT = json.loads((HERE / "data" / "scarlet_gt.json").read_text(encoding="utf-8"))
CACHE = HERE / "cache" / "S"
P = {p["name"]: p for p in GT["persons"]}


def resolve(raw: str) -> str | None:
    """예측 이름 → 정답 인물명. 겹치는 이름(페리어 부녀, 샤르팡티에 가족)은 규칙으로 구분."""
    n = (raw or "").strip()
    if not n:
        return None
    if "루시" in n:
        return "루시"
    if "샤르팡티" in n:
        if "부인" in n or "여사" in n:
            return "샤르팡티에 부인"
        if "앨리스" in n or "엘리스" in n:
            return "앨리스"
        return "아서 샤르팡티에"
    if n == "영" or "브리검" in n or "브리감" in n or "예언자" in n:
        return "브리검 영"
    for p in GT["persons"]:
        for a in p["aliases"]:
            if a in ("영", "샤르팡티에", "아서"):
                continue
            if a in n:
                return p["name"]
    if "아서" in n:
        return "아서 샤르팡티에"
    if "앨리스" in n or "엘리스" in n:
        return "앨리스"
    return None


def gt_upto(i):
    pers = {p["name"] for p in GT["persons"] if p["ch"] <= i}
    core_p = {p["name"] for p in GT["persons"] if p["ch"] <= i and p["core"]}
    rel = {frozenset((r["a"], r["b"])) for r in GT["relations"] if r["ch"] <= i}
    core_r = {frozenset((r["a"], r["b"])) for r in GT["relations"] if r["ch"] <= i and r["core"]}
    future = {frozenset((r["a"], r["b"])) for r in GT["relations"] if r["ch"] > i}
    return pers, core_p, rel, core_r, future


def score(model, i):
    e = json.loads((CACHE / f"{model}_s{i}.json").read_text(encoding="utf-8"))
    pers, core_p, rel, core_r, future = gt_upto(i)
    names = {resolve(c.get("name", "")) for c in e["characters"]}
    unmatched_p = sorted({c.get("name", "") for c in e["characters"] if resolve(c.get("name", "")) is None})
    got = {n for n in names if n}
    pred = set()
    unmapped_r = 0
    for x in e["relations"]:
        a, b = resolve(x.get("source", "")), resolve(x.get("target", ""))
        if not a or not b:
            unmapped_r += 1
        elif a != b:
            pred.add(frozenset((a, b)))
    ok = pred & rel
    leak = {q for q in pred if q in future and q not in rel}
    wrongset = {frozenset((w['a'], w['b'])) for w in GT.get('wrong', [])}
    wrong = pred & wrongset  # 본문과 대조해 오류로 판정된 쌍
    outside = pred - rel - leak - wrongset  # 아직 미판정
    return dict(
        p_rec=len(got & core_p) / max(1, len(core_p)), p_core=len(core_p), p_hit=len(got & core_p),
        p_miss=sorted(core_p - got), p_extra_gt=len(got - pers), un_p=unmatched_p,
        r_rec=len(pred & core_r) / max(1, len(core_r)), r_core=len(core_r), r_hit=len(pred & core_r),
        r_prec=len(ok) / max(1, len(pred)), r_pred=len(pred), r_ok=len(ok),
        leak=len(leak), wrong=len(wrong), outside=outside, unmapped_r=unmapped_r, r_miss=core_r - pred,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="solar-pro3,solar-pro4")
    ap.add_argument("--offsets", default="1-14", help="예: 1-14 또는 2,4,6,7,9,11,14")
    a = ap.parse_args()
    models = a.models.split(",")
    offs = [int(x) for x in (range(int(a.offsets.split("-")[0]), int(a.offsets.split("-")[1]) + 1) if "-" in a.offsets else a.offsets.split(","))]
    tot = {m: dict(wr=0, ph=0, pc=0, rh=0, rc=0, ok=0, pred=0, leak=0, out=0, unp=0) for m in models}
    print(f"{'오프셋':>5} | " + " | ".join(f"{m[-12:]:^46}" for m in models))
    print(f"{'':>5} | " + " | ".join(f"{'인물R':>6}{'관계R':>8}{'관계P':>8}{'누출':>5}{'정답밖쌍':>8}{'GT밖인물':>8}" for _ in models))
    for i in offs:
        row = []
        for m in models:
            s = score(m, i)
            t = tot[m]
            t["ph"] += s["p_hit"]; t["pc"] += s["p_core"]; t["rh"] += s["r_hit"]; t["rc"] += s["r_core"]
            t["ok"] += s["r_ok"]; t["pred"] += s["r_pred"]; t["leak"] += s["leak"]; t["wr"] += s["wrong"]; t["out"] += len(s["outside"]); t["unp"] += len(s["un_p"])
            row.append(f"{s['p_hit']}/{s['p_core']:<2} {s['p_rec']:>3.0%}  {s['r_hit']:>2}/{s['r_core']:<2}{s['r_rec']:>4.0%} {s['r_ok']:>3}/{s['r_pred']:<3}{s['r_prec']:>3.0%}{s['leak']:>5}{len(s['outside']):>8}{len(s['un_p']):>8}")
        print(f"{i:>5} | " + " | ".join(row))
    print("\n=== 전체 합산 (14개 오프셋) ===")
    for m, t in tot.items():
        print(f"{m}: 핵심인물 Recall {t['ph']}/{t['pc']}={t['ph']/t['pc']:.1%} | 핵심관계 Recall {t['rh']}/{t['rc']}={t['rh']/t['rc']:.1%} | "
              f"관계 Precision(허용 포함) {t['ok']}/{t['pred']}={t['ok']/max(1,t['pred']):.1%} | 스포일러 누출 {t['leak']} | 오류 판정 관계 {t['wr']} | 정답표 밖 쌍 {t['out']} | GT밖 인물이름 {t['unp']}")


if __name__ == "__main__":
    main()
