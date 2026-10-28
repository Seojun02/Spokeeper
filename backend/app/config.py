import os
from pathlib import Path

from dotenv import load_dotenv

# uvicorn을 루트·backend 중 어느 경로에서 실행해도 같은 설정을 읽도록
# 현재 작업 디렉터리가 아닌 이 파일의 위치를 기준으로 backend/.env를 로드한다.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL", "")
DEFAULT_BOOK_ID = os.getenv("SPO_BOOK_ID", "")

# cfi_db의 chapter_index(0=서문, 1~15=본문 챕터)와 agents.parsers.epub_parser의
# chapter_index(표지·목차 등 앞부분 문서까지 포함해 1부터 순서대로 매김) 사이의 오프셋.
# 셜록 홈즈 EPUB 기준으로 실측한 고정값 — 다른 책을 붙일 땐 재검증 필요.
PARSER_CHAPTER_OFFSET = 2
