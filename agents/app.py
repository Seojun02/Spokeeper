import streamlit as st

from pathlib import Path
from agents.build_agent import build_agent
from agents.parsers.epub_parser import parse_epub
from agents.tools.chunk_tool import make_chunks


st.set_page_config(
    page_title="SpoKeeper",
    page_icon="🍀",
    layout="wide",
)

st.title("🍀 SpoKeeper")
st.caption("스포일러-세이프 인물 관계도 & 맥락 리마인드 서비스")

st.sidebar.header("1. EPUB 업로드")

uploaded_file = st.sidebar.file_uploader(
    "소설 EPUB 파일을 업로드하세요.",
    type=["epub"],
)

if "chunks" not in st.session_state:
    st.session_state.chunks = []

if "book_title" not in st.session_state:
    st.session_state.book_title = ""

if uploaded_file is not None:
    save_dir = Path("data/books")
    save_dir.mkdir(parents=True, exist_ok=True)

    epub_path = save_dir / uploaded_file.name

    with open(epub_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    st.sidebar.success(f"업로드 완료: {uploaded_file.name}")

    if st.sidebar.button("EPUB 파싱 및 Chunk 생성"):
        with st.spinner("EPUB를 분석하는 중입니다..."):
            parsed_book = parse_epub(epub_path)
            chunks = make_chunks(parsed_book["chapters"])

            st.session_state.book_title = parsed_book["title"]
            st.session_state.chunks = chunks

        st.sidebar.success("본문 분석 완료")


if not st.session_state.chunks:
    st.info("왼쪽 사이드바에서 EPUB 파일을 업로드하고 분석을 시작하세요.")
    st.stop()


chunks = st.session_state.chunks

st.sidebar.header("2. 현재 읽기 위치 선택")

current_chunk_index = st.sidebar.slider(
    "현재 읽은 Chunk 위치",
    min_value=0,
    max_value=len(chunks) - 1,
    value=min(3, len(chunks) - 1),
)

current_chunk = chunks[current_chunk_index]
st.sidebar.caption(current_chunk.get("preview", ""))
current_offset = current_chunk["offset"]

st.sidebar.write(f"현재 offset: `{current_offset}`")
st.sidebar.write(f"전체 chunk 수: `{len(chunks)}`")

left, right = st.columns([2, 1])

with left:
    st.subheader("📖 간이 EPUB 뷰어")

    st.markdown(f"### {st.session_state.book_title}")
    st.caption(
    f"Chapter {current_chunk['chapter_index']} - {current_chunk.get('chapter_title', '')} / "
    f"Chunk {current_chunk['chunk_id']} / "
    f"Offset {current_chunk['offset']}"
    )

    st.text_area(
        "현재 위치 본문",
        current_chunk["text"],
        height=500,
    )

with right:
    st.subheader("🧠 SpoKeeper Panel")

    st.write("현재 읽기 위치 기준으로 Agent Workflow를 실행합니다.")

    if st.button("현재 위치까지 분석"):
        with st.spinner("BuildAgent가 현재 위치까지의 인물, 관계, 사건을 추출하는 중입니다..."):
            result = build_agent(
                chunks=chunks,
                current_offset=current_offset,
        )

        st.success("BuildAgent 실행 완료")

        st.subheader("👤 추출된 인물")
        st.json(result["characters"])

        st.subheader("🔗 추출된 관계")
        st.json(result["relations"])

        st.subheader("📌 추출된 사건")
        st.json(result["events"])

        st.subheader("📝 BuildAgent 로그")
        st.json(
            {
                "current_offset": result["current_offset"],
                "used_chunk_count": result["used_chunk_count"],
                "character_count": len(result["characters"]),
                "relation_count": len(result["relations"]),
                "event_count": len(result["events"]),
                "parse_error": result.get("parse_error", False),
            }
        )
