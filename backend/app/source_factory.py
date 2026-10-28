from __future__ import annotations

import os
from pathlib import Path

from .content_source import AgentResultSource, ContentSource, FixtureSource
from .precompute import STORE_DIR


def load_local_precomputed_store(store_dir: Path = STORE_DIR) -> dict:
    """Load only backend/data/precomputed/*.json snapshots.

    This is intentionally DB-free so SPO_SOURCE=local can validate newly
    generated local snapshots without touching Supabase.
    """
    combined_store: dict = {}
    for path in sorted(store_dir.glob("*.json")):
        file_store = AgentResultSource.from_json_file(path)._store
        combined_store.update(file_store)
    return combined_store


def make_content_source(source_name: str | None = None, store_dir: Path = STORE_DIR) -> ContentSource:
    source = (source_name or os.environ.get("SPO_SOURCE", "fixture")).lower()

    if source == "local":
        local_store = load_local_precomputed_store(store_dir)
        if local_store:
            return AgentResultSource(local_store)
        print(f"[SPO_SOURCE=local] precompute 파일 없음: {store_dir} → FixtureSource 폴백")
        return FixtureSource()

    if source == "agent":
        combined_store: dict = dict(AgentResultSource.from_supabase()._store)
        for key, value in load_local_precomputed_store(store_dir).items():
            combined_store.setdefault(key, value)
        if combined_store:
            return AgentResultSource(combined_store)
        print(f"[SPO_SOURCE=agent] precompute 파일 없음: {store_dir} → FixtureSource 폴백")

    return FixtureSource()
