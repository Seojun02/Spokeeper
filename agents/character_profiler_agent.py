import json
from langchain_upstage import ChatUpstage
from langchain_core.messages import SystemMessage, HumanMessage

from agents.config import UPSTAGE_API_KEY
from agents.build_agent import extract_json_from_text


CHARACTER_PROFILER_PROMPT = """
당신은 SpoKeeper의 CharacterProfilerAgent입니다.

역할:
- BuildAgent가 추출한 인물 설명을 바탕으로 인물의 시각적 프로필을 생성합니다.
- 현재까지 확인된 정보만 사용합니다.
- 확실하지 않은 정보는 unknown으로 둡니다.
- 스포일러가 될 수 있는 미래 정보는 절대 추측하지 않습니다.

출력은 반드시 JSON 형식으로만 작성하세요.

{
  "profiles": [
    {
      "name": "인물명",
      "gender": "male/female/unknown",
      "age": "child/teen/20s/30s/40s/elderly/unknown",
      "profession": "직업 또는 역할",
      "clothes": "복장",
      "mood": "분위기",
      "era": "시대 배경",
      "visual_keywords": ["키워드1", "키워드2", "키워드3"]
    }
  ]
}
"""


def profile_characters(characters: list[dict]) -> dict:
    """
    BuildAgent가 추출한 characters를 기반으로
    이미지 생성에 사용할 인물별 시각 프로필을 생성한다.
    """
    if not UPSTAGE_API_KEY:
        raise ValueError("UPSTAGE_API_KEY가 설정되지 않았습니다.")

    if not characters:
        return {"profiles": []}

    llm = ChatUpstage(
        model="solar-pro2",
        api_key=UPSTAGE_API_KEY,
        temperature=0,
    )

    response = llm.invoke(
        [
            SystemMessage(content=CHARACTER_PROFILER_PROMPT),
            HumanMessage(
                content=f"""
다음은 현재 읽은 위치까지 확인된 인물 목록입니다.

characters:
{json.dumps(characters, ensure_ascii=False, indent=2)}

각 인물의 시각적 프로필을 생성하세요.
"""
            ),
        ]
    )

    result = extract_json_from_text(response.content)

    return {
        "profiles": result.get("profiles", []),
        "raw_response": response.content,
    }


def make_avatar_prompt(profile: dict) -> str:
    """
    인물 프로필을 이미지 생성용 영어 프롬프트로 변환한다.
    """
    name = profile.get("name", "unknown character")
    gender = profile.get("gender", "unknown")
    age = profile.get("age", "unknown")
    profession = profile.get("profession", "unknown role")
    clothes = profile.get("clothes", "simple clothes")
    mood = profile.get("mood", "neutral expression")
    era = profile.get("era", "novel setting")
    visual_keywords = ", ".join(profile.get("visual_keywords", []))

    prompt = f"""
Stylized character portrait for a novel relationship graph.
Character name: {name}.
Gender: {gender}.
Age: {age}.
Role or profession: {profession}.
Clothes: {clothes}.
Mood: {mood}.
Era or setting: {era}.
Visual keywords: {visual_keywords}.
Style: clean digital illustration, book character portrait, neutral background, upper body, readable face, non-photorealistic.
Do not include text, letters, logos, or spoilers.
"""

    return " ".join(prompt.split())


def make_avatar_prompts(profiles: list[dict]) -> list[dict]:
    """
    profile 목록을 avatar prompt 목록으로 변환한다.
    """
    avatar_prompts = []

    for profile in profiles:
        avatar_prompts.append(
            {
                "name": profile.get("name", "unknown"),
                "avatar_prompt": make_avatar_prompt(profile),
                "profile": profile,
            }
        )

    return avatar_prompts