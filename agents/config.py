import os
from dotenv import load_dotenv

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")

# 모든 에이전트가 쓰는 채팅 모델. 환경변수 UPSTAGE_CHAT_MODEL 로 한곳에서 교체. 기본값은 비교 실험(docs/model-comparison.md) 결과로 solar-pro4.
CHAT_MODEL = os.getenv("UPSTAGE_CHAT_MODEL", "solar-pro4")

# 동일 인물 병합 방식: "llm"(기본, LLM 병합) / "decide"(solar-decide 분류 병합). 인물이 아닌 항목 검사는 SCREENER(agents/entity_screener.py)가 따로 맡는다.
CANONICALIZER = os.getenv("CANONICALIZER", "llm")
