from agents import entity_screener as es


def _fake_post(probs_by_name):
    """이름별 {질문: yes 확률}을 돌려주는 solar-decide 대역. 질문 id 는 '<질문><순번>' 이다."""

    def post(state, questions):
        names = [line[2:].split(":", 1)[0] for line in state.splitlines()[1:]]
        return {
            qid: {"probabilities": {"yes": probs_by_name[names[int(qid[len(key):])]].get(key, 1.0)}}
            for qid in questions
            for key in es.QUESTIONS
            if qid.startswith(key)
        }

    return post


def _result():
    return {
        "characters": [
            {"name": "셜록 홈즈", "description": "탐정"},
            {"name": "순찰 경관", "description": "현장을 지킨 경관"},
            {"name": "뒤팽", "description": "다른 소설의 탐정"},
        ],
        "relations": [
            {"source": "셜록 홈즈", "target": "순찰 경관", "relation": "대화"},
            {"source": "셜록 홈즈", "target": "뒤팽", "relation": "비교"},
            {"source": "셜록 홈즈", "target": "행상", "relation": "관찰"},
        ],
        "events": [{"summary": "조사", "participants": ["셜록 홈즈", "순찰 경관", "행상"]}],
    }


def test_screen_removes_flagged_names_everywhere(monkeypatch):
    monkeypatch.setattr(es, "_post", _fake_post({
        "셜록 홈즈": {}, "순찰 경관": {"person": 0.1}, "뒤팽": {"inplot": 0.05}, "행상": {"person": 0.0},
    }))
    registry: list[dict] = []
    out, _ = es.screen_result(_result(), registry)
    assert [c["name"] for c in out["characters"]] == ["셜록 홈즈"]
    assert out["relations"] == []
    assert out["events"][0]["participants"] == ["셜록 홈즈"]


def test_screen_does_not_ask_again_and_keeps_dropping(monkeypatch):
    calls = []
    post = _fake_post({"셜록 홈즈": {}, "순찰 경관": {"person": 0.1}, "뒤팽": {}, "행상": {}})

    def counting(state, questions):
        calls.append(len(questions))
        return post(state, questions)

    monkeypatch.setattr(es, "_post", counting)
    registry: list[dict] = []
    es.screen_result(_result(), registry)
    out, _ = es.screen_result(_result(), registry)  # 다음 경계선: 같은 이름이 누적 결과에 다시 나온다
    assert len(calls) == 1
    assert "순찰 경관" not in [c["name"] for c in out["characters"]]


def test_screen_failure_removes_nothing_and_retries_next_time(monkeypatch):
    def boom(state, questions):
        raise RuntimeError("429")

    monkeypatch.setattr(es, "_post", boom)
    registry: list[dict] = []
    out, _ = es.screen_result(_result(), registry)
    assert len(out["characters"]) == 3

    monkeypatch.setattr(es, "_post", _fake_post({
        "셜록 홈즈": {}, "순찰 경관": {"person": 0.1}, "뒤팽": {}, "행상": {},
    }))
    out, _ = es.screen_result(_result(), registry)
    assert "순찰 경관" not in [c["name"] for c in out["characters"]]


def test_screener_off(monkeypatch):
    monkeypatch.setattr(es, "ENABLED", False)
    assert es.screen_result(_result(), []) == (_result(), {})


def _stub_ranker(monkeypatch, ranked):
    from agents import role_alias_resolver as ra

    monkeypatch.setattr(ra, "rank_candidates", lambda roles, pool: {r: c for r, c in ranked.items() if r in roles})
    return ra


def test_role_alias_is_linked_when_the_text_confirms(monkeypatch):
    monkeypatch.setattr(es, "_post", _fake_post({
        "셜록 홈즈": {}, "순찰 경관": {"person": 0.1}, "뒤팽": {}, "행상": {},
    }))
    ra = _stub_ranker(monkeypatch, {"순찰 경관": [("셜록 홈즈", 0.3)]})
    monkeypatch.setattr(ra, "ask_identity", lambda *a, **k: {"match_to": "셜록 홈즈", "quote": "순찰 경관은 곧 셜록 홈즈였다"})
    registry: list[dict] = []
    out, aliases = es.screen_result(_result(), registry, passages_for=lambda n: ["…순찰 경관은 곧 셜록 홈즈였다…"])
    assert aliases == {"순찰 경관": "셜록 홈즈"}
    assert "순찰 경관" in [c["name"] for c in out["characters"]]  # 이름 치환은 호출부(global_name_map)가 한다


def test_role_alias_needs_a_quote_that_is_really_in_the_passages(monkeypatch):
    monkeypatch.setattr(es, "_post", _fake_post({
        "셜록 홈즈": {}, "순찰 경관": {"person": 0.1}, "뒤팽": {}, "행상": {},
    }))
    ra = _stub_ranker(monkeypatch, {"순찰 경관": [("셜록 홈즈", 0.3)]})
    monkeypatch.setattr(ra, "ask_identity", lambda *a, **k: {"match_to": "셜록 홈즈", "quote": "본문에 없는 문장"})
    registry: list[dict] = []
    out, aliases = es.screen_result(_result(), registry, passages_for=lambda n: ["전혀 다른 본문"])
    assert aliases == {}
    assert "순찰 경관" not in [c["name"] for c in out["characters"]]  # 연결 못하면 제거


def test_role_alias_without_passages_is_not_linked(monkeypatch):
    monkeypatch.setattr(es, "_post", _fake_post({
        "셜록 홈즈": {}, "순찰 경관": {"person": 0.1}, "뒤팽": {}, "행상": {},
    }))
    ra = _stub_ranker(monkeypatch, {"순찰 경관": [("셜록 홈즈", 0.3)]})
    monkeypatch.setattr(ra, "ask_identity", lambda *a, **k: {"match_to": "셜록 홈즈", "quote": "x"})
    out, aliases = es.screen_result(_result(), [], passages_for=None)
    assert aliases == {}


def test_groups_and_words_are_never_alias_candidates(monkeypatch):
    monkeypatch.setattr(es, "_post", _fake_post({
        "셜록 홈즈": {}, "순찰 경관": {}, "뒤팽": {"inplot": 0.0}, "행상": {"person": 0.0, "single": 0.0},
    }))
    called = []
    from agents import role_alias_resolver as ra

    monkeypatch.setattr(ra, "rank_candidates", lambda roles, pool: called.append(list(roles)) or {})
    es.screen_result(_result(), [])
    assert called == []


def test_role_alias_quote_must_contain_the_candidate_name(monkeypatch):
    """같은 역할의 다른 사람(예: 하숙집 주인 둘)처럼, 인용이 본문에 있어도 후보 이름이 없으면 연결하지 않는다."""
    monkeypatch.setattr(es, "_post", _fake_post({
        "셜록 홈즈": {}, "순찰 경관": {"person": 0.1}, "뒤팽": {}, "행상": {},
    }))
    ra = _stub_ranker(monkeypatch, {"순찰 경관": [("셜록 홈즈", 0.6)]})
    monkeypatch.setattr(ra, "ask_identity", lambda *a, **k: {"match_to": "셜록 홈즈", "quote": "순찰 경관이 문을 열었다"})
    _, aliases = es.screen_result(_result(), [], passages_for=lambda n: ["순찰 경관이 문을 열었다"])
    assert aliases == {}
