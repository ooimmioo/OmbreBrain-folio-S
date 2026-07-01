"""
Local acceptance check for episodic memory.

Runs against a temporary buckets directory by default. It does not require a real
LLM API key and does not touch your real memory vault unless --buckets-dir is
explicitly provided.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

import frontmatter


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASSPHRASE = "蓝色章鱼在月亮上煎饼"
RAW_DIALOGUE = f"""User: 我们来做一次情节记忆验收。
AI: 好，我会完整保存这段原始对话。
User: 测试暗号是“{PASSPHRASE}”。
AI: 已收到。也请把鸡枞菌、白蚁、蓝色章鱼这些检索词作为索引入口。
User: 重点是 raw_dialogue 不能被 summary 替代。
AI: 明白，summary 只能做索引，原文才是记忆本体。"""


class FakeEmbedding:
    async def generate_and_store(self, *args, **kwargs):
        return True

    async def search_similar(self, *args, **kwargs):
        return []


class FakeDecay:
    async def ensure_started(self):
        return None

    def calculate_score(self, meta):
        return float(meta.get("importance", 5))


class FakeDehydrator:
    def __init__(self):
        self.dehydrate_calls = 0

    async def analyze_episode(self, raw_dialogue):
        return {
            "summary": "验收用索引摘要，不是原始正文",
            "keywords": ["鸡枞菌", "白蚁", "蓝色章鱼", "情节记忆"],
            "emotion": "认真、确认边界",
            "recall_triggers": ["蓝色章鱼", "月亮上煎饼", "鸡枞菌和白蚁"],
            "domain": ["回忆", "AI"],
            "valence": 0.6,
            "arousal": 0.4,
            "importance": 8,
            "suggested_name": "情节验收",
        }

    async def dehydrate(self, *args, **kwargs):
        self.dehydrate_calls += 1
        raise AssertionError("episodic acceptance: normal dehydrate must not be used")


class CheckRunner:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, condition: bool, fail_message: str):
        self.results.append((name, bool(condition), "" if condition else fail_message))

    def fail(self, name: str, fail_message: str):
        self.results.append((name, False, fail_message))

    def print_report(self):
        print("\nEPISODIC MEMORY ACCEPTANCE")
        print("=" * 32)
        for name, ok, detail in self.results:
            if ok:
                print(f"PASS {name}")
            else:
                print(f"FAIL {name}")
                print(f"     {detail}")
        passed = sum(1 for _, ok, _ in self.results if ok)
        total = len(self.results)
        print("-" * 32)
        print(f"RESULT {passed}/{total} passed")
        return passed == total


def _unwrap_tool(tool):
    return getattr(tool, "fn", tool)


def _setup_bucket_dirs(buckets_dir: Path):
    for rel in ("permanent", "dynamic", "archive", "dynamic/feel"):
        (buckets_dir / rel).mkdir(parents=True, exist_ok=True)


async def run_acceptance(buckets_dir: Path, keep: bool) -> bool:
    runner = CheckRunner()
    _setup_bucket_dirs(buckets_dir)

    os.environ["OMBRE_BUCKETS_DIR"] = str(buckets_dir)
    os.environ["OMBRE_TRANSPORT"] = "stdio"
    os.environ.pop("OMBRE_API_KEY", None)
    os.environ.pop("OMBRE_EMBED_API_KEY", None)

    import server  # noqa: WPS433 - intentionally imported after env setup

    fake_dehydrator = FakeDehydrator()
    merge_or_create_called = {"value": False}

    async def forbidden_merge_or_create(*args, **kwargs):
        merge_or_create_called["value"] = True
        raise AssertionError("episode() must not call _merge_or_create")

    server.dehydrator = fake_dehydrator
    server.embedding_engine = FakeEmbedding()
    server.decay_engine = FakeDecay()
    server._merge_or_create = forbidden_merge_or_create

    episode = _unwrap_tool(server.episode)
    breath = _unwrap_tool(server.breath)

    bucket_id = ""
    try:
        result = await episode(raw_dialogue=RAW_DIALOGUE, importance=8)
        bucket_id = result.split("→", 1)[1].split()[0]
        runner.check(
            "episode() writes a bucket",
            bool(bucket_id),
            "episode() did not return a bucket id; write path may be broken.",
        )
    except Exception as exc:
        runner.fail("episode() writes a bucket", f"episode() raised {type(exc).__name__}: {exc}")
        runner.print_report()
        return False

    bucket = await server.bucket_mgr.get(bucket_id)
    runner.check(
        "bucket can be loaded",
        bucket is not None,
        "The returned bucket id could not be loaded from Markdown storage.",
    )

    post = frontmatter.load(bucket["path"]) if bucket else None
    runner.check(
        "Markdown body preserves full raw_dialogue",
        bool(post and post.content == RAW_DIALOGUE and PASSPHRASE in post.content),
        "Requirement 1/2 failed: Markdown body is not exactly the full raw_dialogue, or the passphrase is missing.",
    )

    if post:
        runner.check(
            "frontmatter has episodic index fields",
            post.get("type") == "episodic"
            and bool(post.get("summary"))
            and bool(post.get("keywords"))
            and bool(post.get("emotion"))
            and bool(post.get("recall_triggers")),
            "Requirement 3 failed: frontmatter must contain type=episodic plus summary, keywords, emotion, recall_triggers.",
        )

    search_ok = True
    missing_terms = []
    for term in ("鸡枞菌", "白蚁", "蓝色章鱼"):
        out = await breath(query=term, max_tokens=8000, max_results=5)
        if "raw_dialogue:" not in out or RAW_DIALOGUE not in out:
            search_ok = False
            missing_terms.append(term)
    runner.check(
        "breath search returns full raw_dialogue",
        search_ok,
        "Requirement 4 failed: breath search did not return complete raw_dialogue for: "
        + ", ".join(missing_terms),
    )

    all_buckets = await server.bucket_mgr.list_all(include_archive=True)
    feel_buckets = [b for b in all_buckets if b.get("metadata", {}).get("type") == "feel"]
    runner.check(
        "episode does not enter feel",
        not feel_buckets,
        "Requirement 5 failed: an episodic write created or moved data into feel.",
    )
    runner.check(
        "episode does not call merge_or_create",
        not merge_or_create_called["value"],
        "Requirement 5 failed: episode() called _merge_or_create, so it may merge raw dialogue into existing memories.",
    )

    dream_response = await server.dream_hook(None)
    dream_body = dream_response.body.decode("utf-8")
    runner.check(
        "dream-hook skips episodic",
        PASSPHRASE not in dream_body and "蓝色章鱼" not in dream_body,
        "Requirement 5 failed: dream-hook included episodic raw dialogue; episodic archives should be skipped by default.",
    )

    runner.check(
        "episodic path avoids normal dehydrate",
        fake_dehydrator.dehydrate_calls == 0,
        "Episodic acceptance path called normal dehydrate; raw_dialogue may be summarized.",
    )

    if keep:
        print(f"\nKept acceptance buckets at: {buckets_dir}")

    return runner.print_report()


def main() -> int:
    parser = argparse.ArgumentParser(description="Accept episodic memory locally.")
    parser.add_argument(
        "--buckets-dir",
        type=Path,
        default=None,
        help="Optional buckets dir. Defaults to a temporary isolated directory.",
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the temporary buckets directory after the run.",
    )
    args = parser.parse_args()

    temp_dir = None
    if args.buckets_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ombre-episode-accept-"))
        buckets_dir = temp_dir / "buckets"
    else:
        buckets_dir = args.buckets_dir.resolve()

    try:
        keep = not args.cleanup or args.buckets_dir is not None
        ok = asyncio.run(run_acceptance(buckets_dir, keep=keep))
        return 0 if ok else 1
    finally:
        if temp_dir is not None and args.cleanup:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
