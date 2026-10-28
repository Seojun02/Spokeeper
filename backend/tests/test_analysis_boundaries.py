import pytest

from backend.app.precompute import build_analysis_boundaries


def _chunks(count: int) -> list[dict]:
    return [{"offset": index} for index in range(count)]


def test_default_analysis_boundary_keeps_every_chunk() -> None:
    assert build_analysis_boundaries(_chunks(6)) == [0, 1, 2, 3, 4, 5]


def test_grouped_schedule_keeps_final_partial_chunk() -> None:
    assert build_analysis_boundaries(_chunks(7), chunks_per_snapshot=5) == [4, 6]


def test_empty_and_invalid_boundary_schedule() -> None:
    assert build_analysis_boundaries([]) == []
    with pytest.raises(ValueError):
        build_analysis_boundaries(_chunks(1), chunks_per_snapshot=0)
