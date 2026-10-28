import json
from langchain_upstage import ChatUpstage
from langchain_core.messages import SystemMessage, HumanMessage

from agents.config import UPSTAGE_API_KEY
from agents.build_agent import extract_json_from_text
from agents.llm_utils import invoke_with_retry


INDIRECT_LEAKAGE_JUDGE_SYSTEM_PROMPT = """
당신은 SpoKeeper의 IndirectLeakageJudge입니다 (최종 가드).

역할:
- ReminderWriterAgent가 작성한 리마인드 문장 각각을 검사해서, 직접적인 스포일러는
  아니더라도 다음을 포함하는지 판단합니다.
  - 암시(implication)
  - 복선(foreshadowing)
  - 앞으로 벌어질 일을 연상시키는 표현
- 각 문장에 대해 다음 중 하나로 판정합니다.
  - PASS: 문제 없음, 그대로 사용
  - REWRITE: 암시/복선 소지가 있어 더 중립적인 문장으로 다시 씀 (원 사실관계는 유지)
  - SUPPRESS: 위험이 커서 아예 노출하지 않음 (제거)
- REWRITE인 경우 rewritten_text에 다시 쓴 문장을 반드시 채웁니다.

출력은 반드시 아래 JSON 형식으로만 작성하세요.

{
  "judgements": [
    {"text": "원문", "verdict": "PASS|REWRITE|SUPPRESS", "rewritten_text": "REWRITE일 때만"}
  ]
}
"""


def judge_reminders(lines: list[dict]) -> list[dict]:
    """
    ReminderWriterAgent가 만든 lines(text, entity_names)를 검사해서
    PASS/REWRITE/SUPPRESS 판정 후, 최종 노출할 lines만 반환한다.
    """
    if not UPSTAGE_API_KEY:
        raise ValueError("UPSTAGE_API_KEY가 설정되지 않았습니다.")

    if not lines:
        return []

    llm_factory = lambda: ChatUpstage(
        model="solar-pro2",
        api_key=UPSTAGE_API_KEY,
        temperature=0,
        timeout=120,
    )

    response = invoke_with_retry(
        llm_factory,
        [
            SystemMessage(content=INDIRECT_LEAKAGE_JUDGE_SYSTEM_PROMPT),
            HumanMessage(
                content=f"""
다음 리마인드 문장들을 검사하세요.

{json.dumps([l.get("text", "") for l in lines], ensure_ascii=False, indent=2)}
"""
            ),
        ],
    )

    result = extract_json_from_text(response.content)
    judgements = result.get("judgements", [])

    # 파싱 실패 시 안전한 쪽(과도한 억제 방지)으로 전부 통과시킨다.
    if result.get("parse_error") or not judgements:
        return lines

    judgement_by_text = {j.get("text", ""): j for j in judgements}

    final_lines = []
    for line in lines:
        text = line.get("text", "")
        j = judgement_by_text.get(text)
        if j is None or j.get("verdict") == "PASS":
            final_lines.append(line)
        elif j.get("verdict") == "REWRITE" and j.get("rewritten_text"):
            final_lines.append({**line, "text": j["rewritten_text"]})
        # SUPPRESS는 결과에서 제외

    return final_lines
