"""
Local acceptance check for episodic memory.

Runs against a temporary buckets directory by default. It does not require a real
LLM API key and does not touch your real memory vault unless --buckets-dir is
explicitly provided.
"""

from __future__ import annotations

import argparse
import asyncio
import html
import os
import shutil
import sys
import tempfile
import webbrowser
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

    def write_html(self, report_path: Path, details: dict):
        passed = sum(1 for _, ok, _ in self.results if ok)
        total = len(self.results)
        ok_all = passed == total
        cards = []
        for name, ok, detail in self.results:
            cls = "pass" if ok else "fail"
            label = "PASS" if ok else "FAIL"
            extra = "" if ok else f"<p>{html.escape(detail)}</p>"
            cards.append(
                f'<section class="check {cls}"><strong>{label}</strong>'
                f"<span>{html.escape(name)}</span>{extra}</section>"
            )

        raw_dialogue = html.escape(details.get("raw_dialogue", ""))
        markdown_path = html.escape(str(details.get("markdown_path", "")))
        buckets_dir = html.escape(str(details.get("buckets_dir", "")))
        bucket_id = html.escape(str(details.get("bucket_id", "")))
        passphrase = html.escape(PASSPHRASE)
        status_text = "全部通过" if ok_all else "有失败项"
        status_class = "ok" if ok_all else "bad"
        body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Episode 验收报告</title>
  <style>
    body {{ margin: 0; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #f6f3ee; color: #1f2933; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 32px 20px 48px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    .sub {{ color: #657080; margin-bottom: 24px; }}
    .hero {{ background: #fff; border: 1px solid #e3ded6; border-radius: 8px; padding: 22px; margin-bottom: 18px; }}
    .badge {{ display: inline-flex; align-items: center; gap: 8px; padding: 7px 12px; border-radius: 999px; font-weight: 700; }}
    .badge.ok {{ background: #e7f7ed; color: #11683a; }}
    .badge.bad {{ background: #ffe8e6; color: #9c251d; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 10px; }}
    .check {{ background: #fff; border: 1px solid #e3ded6; border-radius: 8px; padding: 14px 15px; display: flex; flex-direction: column; gap: 6px; }}
    .check strong {{ font-size: 13px; letter-spacing: .04em; }}
    .check.pass strong {{ color: #14824d; }}
    .check.fail strong {{ color: #bd3028; }}
    .check p {{ margin: 0; color: #8a342e; line-height: 1.45; }}
    .panel {{ background: #fff; border: 1px solid #e3ded6; border-radius: 8px; padding: 18px; margin-top: 16px; }}
    .meta {{ display: grid; grid-template-columns: 130px 1fr; gap: 8px 14px; font-size: 14px; }}
    code, pre {{ font-family: Consolas, "SFMono-Regular", monospace; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #17202a; color: #edf5ff; border-radius: 8px; padding: 16px; overflow: auto; line-height: 1.55; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <h1>Episode 验收报告</h1>
    <div class="sub">本地临时记忆库测试，不连接真实前端，不需要 API key。</div>
    <div class="badge {status_class}">{status_text} · {passed}/{total}</div>
  </section>

  <section class="grid">
    {''.join(cards)}
  </section>

  <section class="panel">
    <h2>本次写入</h2>
    <div class="meta">
      <div>Bucket ID</div><div><code>{bucket_id}</code></div>
      <div>测试暗号</div><div>{passphrase}</div>
      <div>Markdown</div><div><code>{markdown_path}</code></div>
      <div>Buckets 目录</div><div><code>{buckets_dir}</code></div>
    </div>
  </section>

  <section class="panel">
    <h2>raw_dialogue 原文</h2>
    <pre>{raw_dialogue}</pre>
  </section>
</main>
</body>
</html>
"""
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(body, encoding="utf-8")


def _unwrap_tool(tool):
    return getattr(tool, "fn", tool)


def _setup_bucket_dirs(buckets_dir: Path):
    for rel in ("permanent", "dynamic", "archive", "dynamic/feel"):
        (buckets_dir / rel).mkdir(parents=True, exist_ok=True)


async def run_acceptance(buckets_dir: Path, keep: bool, report_path: Path | None, open_report: bool) -> bool:
    runner = CheckRunner()
    details = {
        "raw_dialogue": RAW_DIALOGUE,
        "buckets_dir": buckets_dir,
        "bucket_id": "",
        "markdown_path": "",
    }
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
        details["bucket_id"] = bucket_id
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
    if bucket:
        details["markdown_path"] = bucket["path"]
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

    ok = runner.print_report()
    if report_path is not None:
        runner.write_html(report_path, details)
        print(f"HTML report: {report_path}")
        if open_report:
            webbrowser.open(report_path.resolve().as_uri())
    return ok


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
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "episode_acceptance_report.html",
        help="HTML report path. Defaults to episode_acceptance_report.html in the repo root.",
    )
    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the HTML report in your default browser.",
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
        ok = asyncio.run(run_acceptance(buckets_dir, keep=keep, report_path=args.report, open_report=args.open))
        return 0 if ok else 1
    finally:
        if temp_dir is not None and args.cleanup:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
