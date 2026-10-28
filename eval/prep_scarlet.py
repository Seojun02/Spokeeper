"""주홍색 연구(CP949 txt) → 14챕터 JSON. 하드랩 해제, 부 구분선·번역자 잡담 제거.

사용: python eval/prep_scarlet.py "<원본 txt 경로>"
"""
import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
OUT = Path(__file__).resolve().parent / "data" / "scarlet_chapters.json"
HEAD = re.compile(r"^\s*(?:\.\.\s*)?(\d{1,2})\.\s*(.+?)\s*\.*\s*$")
PART = re.compile(r"^\s*제\s*\d\s*부")
NOISE_FROM = "으아아아아"  # 번역자 끝인사 시작


def main(path: str):
    raw = Path(path).read_bytes().decode("cp949", errors="replace")
    cut = raw.find(NOISE_FROM)
    if cut != -1:
        raw = raw[:cut]
    lines = raw.splitlines()

    chapters, cur, expect = [], None, 1
    for ln in lines:
        m = HEAD.match(ln)
        if m and int(m.group(1)) == expect and len(m.group(2)) <= 30:
            cur = {"chapter_index": expect, "title": m.group(2).strip(), "lines": []}
            chapters.append(cur)
            expect += 1
            continue
        if cur is None or PART.match(ln):
            continue
        cur["lines"].append(ln)

    for ch in chapters:
        paras, buf = [], []
        for ln in ch.pop("lines"):
            if ln.strip():
                buf.append(ln.strip())
            elif buf:
                paras.append(" ".join(buf))
                buf = []
        if buf:
            paras.append(" ".join(buf))
        ch["text"] = "\n\n".join(paras).replace("�", "")

    assert len(chapters) == 14, f"챕터 {len(chapters)}개 (14 기대)"
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps({"title": "주홍색의 연구", "chapters": chapters}, ensure_ascii=False, indent=1), encoding="utf-8")
    tot = 0
    for ch in chapters:
        tot += len(ch["text"])
        print(f"{ch['chapter_index']:>2} {ch['title']:<16} {len(ch['text']):>6}자  누적 {tot}")


if __name__ == "__main__":
    main(sys.argv[1])
