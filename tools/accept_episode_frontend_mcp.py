"""
Local front-end/MCP acceptance check for episodic memory.

The script uses a temporary buckets directory by default. It does not connect to
the real memory vault and does not require a real LLM API key.
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
RAW_DIALOGUE = f"""User: Please preserve this as one complete episodic memory.
AI: I will keep the original dialogue as the memory body.
User: The test passphrase is "{PASSPHRASE}".
AI: I will also index 鸡枞菌, 白蚁, and 蓝色章鱼 for recall.
User: The raw_dialogue must not be replaced by a summary.
AI: Understood. Summary and keywords are only indexes; the dialogue is the memory."""


class FakeRequest:
    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self):
        return self._payload


class FakeEmbedding:
    enabled = False

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
            "summary": "fallback index summary",
            "keywords": ["fallback"],
            "emotion": "focused",
            "recall_triggers": ["fallback trigger"],
            "domain": ["acceptance"],
            "valence": 0.6,
            "arousal": 0.35,
            "importance": 7,
            "suggested_name": "frontend mcp episode acceptance",
        }

    async def dehydrate(self, *args, **kwargs):
        self.dehydrate_calls += 1
        raise AssertionError("episodic memory must not use normal dehydrate")


class CheckRunner:
    def __init__(self):
        self.results: list[tuple[str, bool, str]] = []

    def check(self, name: str, condition: bool, fail_message: str):
        self.results.append((name, bool(condition), "" if condition else fail_message))

    def fail(self, name: str, fail_message: str):
        self.results.append((name, False, fail_message))

    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.results)

    def print_report(self):
        print("\nFRONTEND/MCP EPISODIC ACCEPTANCE")
        print("=" * 38)
        for name, ok, detail in self.results:
            print(("PASS " if ok else "FAIL ") + name)
            if not ok:
                print("     " + detail)
        passed = sum(1 for _, ok, _ in self.results if ok)
        total = len(self.results)
        print("-" * 38)
        print(f"RESULT {passed}/{total} passed")
        return passed == total

    def write_html(self, report_path: Path, details: dict):
        passed = sum(1 for _, ok, _ in self.results if ok)
        total = len(self.results)
        status = "PASS" if passed == total else "FAIL"
        status_class = "ok" if passed == total else "bad"
        cards = []
        for name, ok, detail in self.results:
            label = "PASS" if ok else "FAIL"
            cls = "pass" if ok else "fail"
            extra = "" if ok else f"<p>{html.escape(detail)}</p>"
            cards.append(
                f'<section class="card {cls}"><strong>{label}</strong>'
                f"<span>{html.escape(name)}</span>{extra}</section>"
            )

        prompt = html.escape(details["prompt"])
        raw_dialogue = html.escape(details["raw_dialogue"])
        bucket_id = html.escape(details.get("bucket_id", ""))
        markdown_path = html.escape(str(details.get("markdown_path", "")))
        buckets_dir = html.escape(str(details.get("buckets_dir", "")))
        tool_params = html.escape(", ".join(details.get("tool_params", [])))

        body = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Frontend MCP Episode Acceptance</title>
  <style>
    body {{ margin: 0; font-family: "Segoe UI", "Microsoft YaHei", sans-serif; background: #f7f4ef; color: #17202a; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 32px 20px 52px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; }}
    h2 {{ margin: 0 0 12px; font-size: 18px; }}
    .hero, .panel, .card {{ background: #fff; border: 1px solid #e3ddd3; border-radius: 8px; }}
    .hero {{ padding: 22px; margin-bottom: 18px; }}
    .sub {{ color: #647180; margin-bottom: 16px; }}
    .badge {{ display: inline-block; padding: 7px 12px; border-radius: 999px; font-weight: 700; }}
    .badge.ok {{ background: #e7f7ed; color: #11683a; }}
    .badge.bad {{ background: #ffe8e6; color: #9c251d; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 10px; }}
    .card {{ padding: 14px 15px; display: flex; flex-direction: column; gap: 6px; }}
    .card strong {{ font-size: 13px; }}
    .card.pass strong {{ color: #14824d; }}
    .card.fail strong {{ color: #bd3028; }}
    .card p {{ margin: 0; color: #8a342e; line-height: 1.45; }}
    .panel {{ padding: 18px; margin-top: 16px; }}
    .meta {{ display: grid; grid-template-columns: 140px 1fr; gap: 8px 14px; font-size: 14px; }}
    code, pre {{ font-family: Consolas, "SFMono-Regular", monospace; }}
    pre {{ white-space: pre-wrap; word-break: break-word; background: #17202a; color: #edf5ff; border-radius: 8px; padding: 16px; line-height: 1.55; overflow: auto; }}
  </style>
</head>
<body>
<main>
  <section class="hero">
    <h1>前端 / MCP 情节记忆联调验收</h1>
    <div class="sub">本报告只使用临时 buckets，不接入真实记忆库。</div>
    <div class="badge {status_class}">{status} · {passed}/{total}</div>
  </section>
  <section class="grid">
    {''.join(cards)}
  </section>
  <section class="panel">
    <h2>本次写入</h2>
    <div class="meta">
      <div>Bucket ID</div><div><code>{bucket_id}</code></div>
      <div>MCP 参数</div><div><code>{tool_params}</code></div>
      <div>Markdown</div><div><code>{markdown_path}</code></div>
      <div>临时 buckets</div><div><code>{buckets_dir}</code></div>
    </div>
  </section>
  <section class="panel">
    <h2>推荐前端 / 角色提示词</h2>
    <pre>{prompt}</pre>
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


PROMPT = """When deciding how to save memory:

Use episode(raw_dialogue, summary, keywords, emotion, recall_triggers, ...) when the conversation itself is the memory: important relationship moments, decisions, promises, conflicts, repair conversations, or any long exchange whose exact wording and sequence matter. raw_dialogue is the source of truth and must be copied completely. summary, keywords, emotion, and recall_triggers are only indexes.

Use hold(content, ...) for compact facts, preferences, stable observations, and short memories where a concise memory sentence is enough.

Do not use hold() to replace a long conversation with a summary. Do not turn a one-time emotion into long-term personality. If the user says "remember this conversation", "keep the original", "save the whole exchange", or the wording matters, call episode()."""


def _setup_bucket_dirs(buckets_dir: Path):
    for rel in ("permanent", "dynamic", "archive", "dynamic/feel"):
        (buckets_dir / rel).mkdir(parents=True, exist_ok=True)


def _unwrap_tool(tool):
    return getattr(tool, "fn", tool)


async def run_acceptance(buckets_dir: Path, report_path: Path | None, open_report: bool) -> bool:
    runner = CheckRunner()
    details = {
        "raw_dialogue": RAW_DIALOGUE,
        "buckets_dir": buckets_dir,
        "bucket_id": "",
        "markdown_path": "",
        "tool_params": [],
        "prompt": PROMPT,
    }

    _setup_bucket_dirs(buckets_dir)
    os.environ["OMBRE_BUCKETS_DIR"] = str(buckets_dir)
    os.environ["OMBRE_TRANSPORT"] = "stdio"
    os.environ.pop("OMBRE_API_KEY", None)
    os.environ.pop("OMBRE_EMBED_API_KEY", None)

    import server  # noqa: WPS433 - imported after env setup

    fake_dehydrator = FakeDehydrator()
    merge_or_create_called = {"value": False}

    async def forbidden_merge_or_create(*args, **kwargs):
        merge_or_create_called["value"] = True
        raise AssertionError("episode must not call merge_or_create")

    server.dehydrator = fake_dehydrator
    server.embedding_engine = FakeEmbedding()
    server.decay_engine = FakeDecay()
    server._merge_or_create = forbidden_merge_or_create

    tools = getattr(getattr(server.mcp, "_tool_manager", None), "_tools", {})
    episode_tool = tools.get("episode")
    params = list((episode_tool.parameters or {}).get("properties", {}).keys()) if episode_tool else []
    details["tool_params"] = params
    needed = {"raw_dialogue", "summary", "keywords", "emotion", "recall_triggers"}
    runner.check(
        "MCP tool list exposes episode(raw_dialogue, summary, keywords, emotion, recall_triggers, ...)",
        bool(episode_tool and needed.issubset(set(params))),
        "MCP tool list is missing episode or one of the required episodic index parameters.",
    )

    payload = {
        "raw_dialogue": RAW_DIALOGUE,
        "summary": "front-end supplied index summary",
        "keywords": ["鸡枞菌", "白蚁", "蓝色章鱼"],
        "emotion": "careful, archival",
        "recall_triggers": ["蓝色章鱼", "月亮上煎饼", "鸡枞菌和白蚁"],
        "importance": 8,
        "name": "frontend mcp episode acceptance",
        "domain": ["acceptance", "episodic"],
    }
    response = await server.api_episode_create(FakeRequest(payload))
    data = getattr(response, "body", b"{}").decode("utf-8")
    import json
    parsed = json.loads(data)
    bucket_id = parsed.get("id", "")
    details["bucket_id"] = bucket_id
    runner.check(
        "front-end API can call episode() through /api/episode",
        response.status_code == 200 and parsed.get("ok") is True and bool(bucket_id),
        f"/api/episode did not create an episodic bucket. Response: {data}",
    )

    bucket = await server.bucket_mgr.get(bucket_id) if bucket_id else None
    post = frontmatter.load(bucket["path"]) if bucket else None
    if bucket:
        details["markdown_path"] = bucket["path"]
    runner.check(
        "front-end write creates type: episodic bucket",
        bool(post and post.get("type") == "episodic"),
        "The bucket created through the front-end API is not marked type: episodic.",
    )
    runner.check(
        "Markdown body is complete raw_dialogue",
        bool(post and post.content == RAW_DIALOGUE and PASSPHRASE in post.content),
        "The Markdown body is not the complete raw_dialogue, or the passphrase is missing.",
    )
    runner.check(
        "frontmatter has summary/keywords/emotion/recall_triggers",
        bool(
            post
            and post.get("summary")
            and post.get("keywords")
            and post.get("emotion")
            and post.get("recall_triggers")
        ),
        "The episodic frontmatter is missing one or more index fields.",
    )

    breath = _unwrap_tool(server.breath)
    search_ok = True
    missing_terms = []
    for term in ("鸡枞菌", "白蚁", "蓝色章鱼"):
        out = await breath(query=term, max_tokens=8000, max_results=5)
        if "raw_dialogue:" not in out or RAW_DIALOGUE not in out:
            search_ok = False
            missing_terms.append(term)
    runner.check(
        "breath returns complete raw_dialogue for front-end-created episode",
        search_ok,
        "breath did not return full raw_dialogue for: " + ", ".join(missing_terms),
    )

    runner.check(
        "episode path does not use feel or merge_or_create",
        not merge_or_create_called["value"] and fake_dehydrator.dehydrate_calls == 0,
        "Episode write called merge_or_create or normal dehydrate; long dialogue may be merged or summarized.",
    )
    runner.check(
        "hold/grow/feel remain separate from long-dialogue episode flow",
        "hold" in tools and "grow" in tools and "episode" in tools and post and post.get("type") != "feel",
        "MCP hold/grow tools are missing, or the episode bucket was incorrectly stored as feel.",
    )

    dream_response = await server.dream_hook(None)
    dream_body = dream_response.body.decode("utf-8")
    runner.check(
        "dream-hook does not process front-end-created episodic bucket",
        PASSPHRASE not in dream_body and "raw_dialogue" not in dream_body,
        "dream-hook included episodic raw dialogue; episodic archives should be skipped by default.",
    )

    ok = runner.print_report()
    if report_path is not None:
        runner.write_html(report_path, details)
        print(f"HTML report: {report_path}")
        if open_report:
            webbrowser.open(report_path.resolve().as_uri())
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Accept episodic memory front-end/MCP integration locally.")
    parser.add_argument("--buckets-dir", type=Path, default=None)
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument(
        "--report",
        type=Path,
        default=ROOT / "episode_frontend_mcp_report.html",
    )
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()

    temp_dir = None
    if args.buckets_dir is None:
        temp_dir = Path(tempfile.mkdtemp(prefix="ombre-episode-frontend-mcp-"))
        buckets_dir = temp_dir / "buckets"
    else:
        buckets_dir = args.buckets_dir.resolve()

    try:
        ok = asyncio.run(run_acceptance(buckets_dir, report_path=args.report, open_report=args.open))
        if args.buckets_dir is None:
            print(f"Temporary buckets: {buckets_dir}")
        return 0 if ok else 1
    finally:
        if temp_dir is not None and args.cleanup:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
