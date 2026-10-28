import os
from dotenv import load_dotenv

load_dotenv()

UPSTAGE_API_KEY = os.getenv("UPSTAGE_API_KEY", "")

# 모든 에이전트가 쓰는 채팅 모델. 환경변수 UPSTAGE_CHAT_MODEL 로 한곳에서 교체(기본값은 기존 동작 유지).
CHAT_MODEL = os.getenv("UPSTAGE_CHAT_MODEL", "solar-pro2")

# 인물 정리 방식: "llm"(기존: 필터+LLM 병합) / "hybrid"(일반 지칭 판별=solar-decide, 병합=LLM) / "decide"(판별·병합 모두 solar-decide). 기본값은 기존 동작 유지.
CANONICALIZER = os.getenv("CANONICALIZER", "llm")

# 리마인드 간접 누출 판정(IndirectLeakageJudge) 사용 여부. 기본 꺼짐(solar-pro4 기준); 1로 켜면 기존 3차 가드 복원.
LEAK_JUDGE = os.getenv("LEAK_JUDGE", "0") == "1"
