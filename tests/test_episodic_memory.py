import json

import frontmatter
import pytest


class _FakeEmbedding:
    async def generate_and_store(self, *args, **kwargs):
        return True

    async def search_similar(self, *args, **kwargs):
        return []


class _FakeDecay:
    async def ensure_started(self):
        return None

    def calculate_score(self, meta):
        return float(meta.get("importance", 5))


class _FakeDehydrator:
    def __init__(self):
        self.dehydrate_called = False

    async def analyze_episode(self, raw_dialogue):
        return {
            "summary": "索引摘要，不是正文",
            "keywords": ["完整对话", "情节记忆"],
            "emotion": "认真确认",
            "recall_triggers": ["那次聊 raw_dialogue", "完整保存"],
            "domain": ["回忆"],
            "valence": 0.6,
            "arousal": 0.4,
            "importance": 7,
            "suggested_name": "情节测试",
        }

    async def dehydrate(self, *args, **kwargs):
        self.dehydrate_called = True
        raise AssertionError("episodic memory must not use normal dehydrate")


@pytest.fixture
async def episodic_server(monkeypatch, bucket_mgr):
    import server

    fake_dehydrator = _FakeDehydrator()
    monkeypatch.setattr(server, "bucket_mgr", bucket_mgr)
    monkeypatch.setattr(server, "dehydrator", fake_dehydrator)
    monkeypatch.setattr(server, "embedding_engine", _FakeEmbedding())
    monkeypatch.setattr(server, "decay_engine", _FakeDecay())
    monkeypatch.setattr(server.random, "random", lambda: 1.0)

    return server, bucket_mgr, fake_dehydrator


@pytest.mark.asyncio
async def test_episode_write_preserves_raw_dialogue_and_frontmatter(episodic_server):
    server, bucket_mgr, _fake_dehydrator = episodic_server
    episode = getattr(server.episode, "fn", server.episode)
    raw_dialogue = "User: 请完整记住这段。\nAI: 好，我会保存原文。\nUser: 不要只存摘要。"

    result = await episode(raw_dialogue=raw_dialogue, importance=5)
    bucket_id = result.split("→", 1)[1].split()[0]
    bucket = await bucket_mgr.get(bucket_id)
    post = frontmatter.load(bucket["path"])

    assert post.content == raw_dialogue
    assert post["type"] == "episodic"
    assert post["summary"] == "索引摘要，不是正文"
    assert post["keywords"] == ["完整对话", "情节记忆"]
    assert post["emotion"] == "认真确认"
    assert post["recall_triggers"] == ["那次聊 raw_dialogue", "完整保存"]


@pytest.mark.asyncio
async def test_breath_search_returns_raw_dialogue_field_for_episodic(episodic_server):
    server, bucket_mgr, _fake_dehydrator = episodic_server
    breath = getattr(server.breath, "fn", server.breath)
    raw_dialogue = "User: 以后搜索完整保存时，要看到这一整段。\nAI: 明白。"
    await bucket_mgr.create(
        content=raw_dialogue,
        tags=["完整保存"],
        importance=6,
        domain=["回忆"],
        valence=0.5,
        arousal=0.3,
        name="检索情节",
        bucket_type="episodic",
        summary="检索摘要",
        keywords=["完整保存"],
        emotion="平静",
        recall_triggers=["看到这一整段"],
    )

    out = await breath(query="完整保存", max_tokens=2000, max_results=5)

    assert "[episodic]" in out
    assert "raw_dialogue:" in out
    assert raw_dialogue in out


@pytest.mark.asyncio
async def test_breath_hook_episodic_does_not_dehydrate(episodic_server):
    server, bucket_mgr, fake_dehydrator = episodic_server
    raw_dialogue = "User: hook 浮现时也要完整。\nAI: 不走普通脱水。"
    await bucket_mgr.create(
        content=raw_dialogue,
        tags=["hook"],
        importance=9,
        domain=["回忆"],
        valence=0.5,
        arousal=0.3,
        name="hook情节",
        bucket_type="episodic",
        summary="hook 摘要",
        keywords=["hook"],
        emotion="确认",
        recall_triggers=["hook 浮现"],
    )

    response = await server.breath_hook(None)
    body = response.body.decode("utf-8")

    assert "raw_dialogue:" in body
    assert raw_dialogue in body
    assert not fake_dehydrator.dehydrate_called


@pytest.mark.asyncio
async def test_breath_hook_marks_truncated_episodic(monkeypatch, episodic_server):
    server, bucket_mgr, _fake_dehydrator = episodic_server
    raw_dialogue = "User: " + ("很长的原文 " * 12000)
    await bucket_mgr.create(
        content=raw_dialogue,
        tags=["超长"],
        importance=9,
        domain=["回忆"],
        valence=0.5,
        arousal=0.3,
        name="超长情节",
        bucket_type="episodic",
        summary="超长摘要",
        keywords=["超长"],
        emotion="密集",
        recall_triggers=["很长"],
    )
    monkeypatch.setattr(server, "count_tokens_approx", lambda text: max(1, len(text) // 4))

    response = await server.breath_hook(None)
    body = response.body.decode("utf-8")

    assert "[truncated]" in body
    assert "raw_dialogue:" in body


@pytest.mark.asyncio
async def test_dream_hook_skips_episodic_by_default(episodic_server):
    server, bucket_mgr, _fake_dehydrator = episodic_server
    raw_dialogue = "User: dream 不应该消化我。\nAI: 我会被跳过。"
    await bucket_mgr.create(
        content=raw_dialogue,
        tags=["dream"],
        importance=8,
        domain=["回忆"],
        valence=0.5,
        arousal=0.3,
        name="dream情节",
        bucket_type="episodic",
        summary="dream 摘要",
        keywords=["dream"],
        emotion="安静",
        recall_triggers=["dream 不处理"],
    )

    hook_response = await server.dream_hook(None)
    dream = getattr(server.dream, "fn", server.dream)
    dream_response = await dream()

    assert raw_dialogue not in hook_response.body.decode("utf-8")
    assert raw_dialogue not in dream_response
    assert "没有需要消化的新记忆" in dream_response


@pytest.mark.asyncio
async def test_analyze_episode_uses_head_and_tail_for_long_dialogue(test_config):
    from dehydrator import Dehydrator

    captured = {}

    class _Message:
        content = json.dumps({
            "summary": "ok",
            "keywords": [],
            "emotion": "",
            "recall_triggers": [],
            "domain": ["回忆"],
            "valence": 0.5,
            "arousal": 0.3,
            "importance": 5,
            "suggested_name": "ok",
        })

    class _Choice:
        message = _Message()

    class _Completions:
        async def create(self, **kwargs):
            captured["user_content"] = kwargs["messages"][1]["content"]
            return type("Response", (), {"choices": [_Choice()]})()

    class _Chat:
        completions = _Completions()

    class _Client:
        chat = _Chat()

    cfg = test_config | {"dehydration": test_config["dehydration"] | {"api_key": "test-key"}}
    dehydrator = Dehydrator(cfg)
    dehydrator.client = _Client()
    dehydrator.api_available = True

    raw_dialogue = "H" * 3500 + "MIDDLE_SHOULD_NOT_BE_SENT" + "T" * 3500
    await dehydrator.analyze_episode(raw_dialogue)

    user_content = captured["user_content"]
    assert user_content.startswith("H" * 3000)
    assert "...[middle omitted for indexing only]..." in user_content
    assert user_content.endswith("T" * 3000)
    assert "MIDDLE_SHOULD_NOT_BE_SENT" not in user_content
