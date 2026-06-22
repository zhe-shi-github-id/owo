# -*- coding: utf-8 -*-
import os
import json
import sys
import types
import tempfile
import shutil
import pytest

# ---------------------------------------------------------------------------
# Stub the external ``astrbot`` package so we can import main.py without it
# being installed.
# ---------------------------------------------------------------------------

# astrbot.api.event
event_module = types.ModuleType("astrbot.api.event")

class _EventNoticeType:
    GROUP_MEMBER_INCREASE = "GROUP_MEMBER_INCREASE"

class _EventMessageType:
    GROUP_MESSAGE = "GROUP_MESSAGE"

class _Filter:
    EventNoticeType = _EventNoticeType
    EventMessageType = _EventMessageType

    @staticmethod
    def event_notice_type(notice_type):
        def decorator(func):
            func._notice_type = notice_type
            return func
        return decorator

    @staticmethod
    def event_message_type(msg_type):
        def decorator(func):
            func._message_type = msg_type
            return func
        return decorator

    @staticmethod
    def command(name):
        def decorator(func):
            func._command = name
            return func
        return decorator

_filter_instance = _Filter()
event_module.filter = _filter_instance
event_module.AstrMessageEvent = object  # placeholder type

# astrbot.api.star
star_module = types.ModuleType("astrbot.api.star")

class Star:
    def __init__(self, context):
        self.context = context

def register(*args, **kwargs):
    def decorator(cls):
        return cls
    return decorator

star_module.Star = Star
star_module.register = register

# astrbot.api (logger)
api_module = types.ModuleType("astrbot.api")

class _Logger:
    messages = []
    def info(self, msg):
        self.messages.append(msg)
    def debug(self, msg):
        self.messages.append(msg)
    def warning(self, msg):
        self.messages.append(msg)
    def error(self, msg):
        self.messages.append(msg)

api_module.logger = _Logger()

# Wire the package hierarchy
astrbot = types.ModuleType("astrbot")
astrbot_api = api_module
astrbot.api = astrbot_api
astrbot_api.event = event_module
astrbot_api.star = star_module

sys.modules["astrbot"] = astrbot
sys.modules["astrbot.api"] = astrbot_api
sys.modules["astrbot.api.event"] = event_module
sys.modules["astrbot.api.star"] = star_module

# Now we can import main
from main import load_json, save_json, GroupManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class FakeMessageObj:
    def __init__(self, user_name=None, user_id="u123", group_id="g456"):
        self.user_name = user_name
        self.user_id = user_id
        self.group_id = group_id


class FakeEvent:
    def __init__(self, message_str="", user_name=None, user_id="u123",
                 group_id="g456", sender_id="sender1"):
        self.message_str = message_str
        self.message_obj = FakeMessageObj(user_name, user_id, group_id)
        self._sender_id = sender_id
        self._stopped = False

    def get_sender_id(self):
        return self._sender_id

    def plain_result(self, text):
        return text

    def stop_event(self):
        self._stopped = True

    @property
    def group_id(self):
        return self.message_obj.group_id


class FakeContext:
    def __init__(self, root_data_dir):
        self.root_data_dir = root_data_dir

    async def kick_group_member(self, group_id, target_id):
        pass

    async def mute_group_member(self, group_id, target_id, duration_seconds):
        pass


class FakeConfig(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved = False

    def save_config(self):
        self._saved = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d)


@pytest.fixture
def manager(tmp_dir):
    ctx = FakeContext(root_data_dir=tmp_dir)
    cfg = FakeConfig(enable_welcome=True,
                     welcome_message="欢迎 {user} 加入群聊！",
                     blocked_keywords=["spam", "广告"],
                     admin_user_ids=["admin1"])
    return GroupManager(ctx, cfg)


# ====================================================================
# Tests for load_json / save_json
# ====================================================================

class TestLoadJson:
    def test_returns_default_when_file_missing(self, tmp_dir):
        result = load_json(os.path.join(tmp_dir, "nope.json"), {"key": "default"})
        assert result == {"key": "default"}

    def test_loads_valid_json(self, tmp_dir):
        path = os.path.join(tmp_dir, "data.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"a": 1}, f)
        assert load_json(path, {}) == {"a": 1}

    def test_returns_default_on_invalid_json(self, tmp_dir):
        path = os.path.join(tmp_dir, "bad.json")
        with open(path, "w") as f:
            f.write("{invalid json}")
        assert load_json(path, []) == []

    def test_returns_default_on_empty_file(self, tmp_dir):
        path = os.path.join(tmp_dir, "empty.json")
        with open(path, "w") as f:
            f.write("")
        assert load_json(path, "fallback") == "fallback"

    def test_loads_list(self, tmp_dir):
        path = os.path.join(tmp_dir, "list.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump([1, 2, 3], f)
        assert load_json(path, []) == [1, 2, 3]

    def test_loads_unicode(self, tmp_dir):
        path = os.path.join(tmp_dir, "uni.json")
        data = {"msg": "你好世界"}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        assert load_json(path, {}) == data


class TestSaveJson:
    def test_creates_file_and_dirs(self, tmp_dir):
        path = os.path.join(tmp_dir, "sub", "dir", "out.json")
        save_json(path, {"x": 42})
        with open(path, "r", encoding="utf-8") as f:
            assert json.load(f) == {"x": 42}

    def test_overwrites_existing(self, tmp_dir):
        path = os.path.join(tmp_dir, "out.json")
        save_json(path, {"old": True})
        save_json(path, {"new": True})
        with open(path, "r", encoding="utf-8") as f:
            assert json.load(f) == {"new": True}

    def test_saves_unicode(self, tmp_dir):
        path = os.path.join(tmp_dir, "uni.json")
        data = {"greeting": "こんにちは"}
        save_json(path, data)
        with open(path, "r", encoding="utf-8") as f:
            assert json.load(f) == data

    def test_roundtrip_with_load(self, tmp_dir):
        path = os.path.join(tmp_dir, "rt.json")
        original = {"nested": {"list": [1, "two", None]}}
        save_json(path, original)
        assert load_json(path, {}) == original


# ====================================================================
# Tests for GroupManager.__init__
# ====================================================================

class TestGroupManagerInit:
    def test_data_dir_set(self, manager, tmp_dir):
        expected = os.path.join(tmp_dir, "plugins", "astrbot_plugin_groupmgr", "data")
        assert manager.data_dir == expected

    def test_group_states_default_empty(self, manager):
        assert manager.group_states == {}

    def test_group_states_loaded_from_file(self, tmp_dir):
        data_dir = os.path.join(tmp_dir, "plugins", "astrbot_plugin_groupmgr", "data")
        os.makedirs(data_dir, exist_ok=True)
        with open(os.path.join(data_dir, "group_states.json"), "w") as f:
            json.dump({"g1": "active"}, f)
        ctx = FakeContext(root_data_dir=tmp_dir)
        cfg = FakeConfig()
        gm = GroupManager(ctx, cfg)
        assert gm.group_states == {"g1": "active"}


# ====================================================================
# Tests for GroupManager.terminate
# ====================================================================

class TestTerminate:
    @pytest.mark.asyncio
    async def test_saves_group_states(self, manager):
        manager.group_states = {"g1": "saved"}
        await manager.terminate()
        path = os.path.join(manager.data_dir, "group_states.json")
        with open(path, "r", encoding="utf-8") as f:
            assert json.load(f) == {"g1": "saved"}


# ====================================================================
# Tests for on_member_join
# ====================================================================

class TestOnMemberJoin:
    @pytest.mark.asyncio
    async def test_welcome_with_username(self, manager):
        event = FakeEvent(user_name="Alice")
        results = [r async for r in manager.on_member_join(event)]
        assert len(results) == 1
        assert "Alice" in results[0]

    @pytest.mark.asyncio
    async def test_welcome_falls_back_to_user_id(self, manager):
        event = FakeEvent(user_name=None, user_id="uid999")
        results = [r async for r in manager.on_member_join(event)]
        assert len(results) == 1
        assert "uid999" in results[0]

    @pytest.mark.asyncio
    async def test_welcome_disabled(self, manager):
        manager.config["enable_welcome"] = False
        event = FakeEvent(user_name="Bob")
        results = [r async for r in manager.on_member_join(event)]
        assert results == []

    @pytest.mark.asyncio
    async def test_custom_welcome_message(self, manager):
        manager.config["welcome_message"] = "Hello {user}!"
        event = FakeEvent(user_name="Eve")
        results = [r async for r in manager.on_member_join(event)]
        assert results == ["Hello Eve!"]

    @pytest.mark.asyncio
    async def test_welcome_default_when_key_missing(self, tmp_dir):
        ctx = FakeContext(root_data_dir=tmp_dir)
        cfg = FakeConfig()
        gm = GroupManager(ctx, cfg)
        event = FakeEvent(user_name="Zoe")
        results = [r async for r in gm.on_member_join(event)]
        assert len(results) == 1
        assert "Zoe" in results[0]


# ====================================================================
# Tests for on_group_message (keyword blocking)
# ====================================================================

class TestOnGroupMessage:
    @pytest.mark.asyncio
    async def test_blocks_keyword(self, manager):
        event = FakeEvent(message_str="this is spam content")
        results = [r async for r in manager.on_group_message(event)]
        assert len(results) == 1
        assert "spam" in results[0]
        assert event._stopped is True

    @pytest.mark.asyncio
    async def test_blocks_second_keyword(self, manager):
        event = FakeEvent(message_str="发送广告")
        results = [r async for r in manager.on_group_message(event)]
        assert len(results) == 1
        assert "广告" in results[0]
        assert event._stopped is True

    @pytest.mark.asyncio
    async def test_no_block_on_clean_message(self, manager):
        event = FakeEvent(message_str="hello everyone")
        results = [r async for r in manager.on_group_message(event)]
        assert results == []
        assert event._stopped is False

    @pytest.mark.asyncio
    async def test_no_block_when_no_keywords_configured(self, tmp_dir):
        ctx = FakeContext(root_data_dir=tmp_dir)
        cfg = FakeConfig(blocked_keywords=[])
        gm = GroupManager(ctx, cfg)
        event = FakeEvent(message_str="spam spam spam")
        results = [r async for r in gm.on_group_message(event)]
        assert results == []

    @pytest.mark.asyncio
    async def test_strips_whitespace(self, manager):
        event = FakeEvent(message_str="  spam  ")
        results = [r async for r in manager.on_group_message(event)]
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_first_matching_keyword_wins(self, manager):
        manager.config["blocked_keywords"] = ["ab", "abc"]
        event = FakeEvent(message_str="xabcx")
        results = [r async for r in manager.on_group_message(event)]
        assert len(results) == 1
        assert "ab" in results[0]


# ====================================================================
# Tests for cmd_kick
# ====================================================================

class TestCmdKick:
    @pytest.mark.asyncio
    async def test_kick_success(self, manager):
        event = FakeEvent(sender_id="admin1")
        results = [r async for r in manager.cmd_kick(event, "target1")]
        assert len(results) == 1
        assert "target1" in results[0]

    @pytest.mark.asyncio
    async def test_kick_denied_non_admin(self, manager):
        event = FakeEvent(sender_id="nobody")
        results = [r async for r in manager.cmd_kick(event, "target1")]
        assert len(results) == 1
        assert "没有权限" in results[0]

    @pytest.mark.asyncio
    async def test_kick_allowed_when_admin_list_empty(self, manager):
        manager.config["admin_user_ids"] = []
        event = FakeEvent(sender_id="anyone")
        results = [r async for r in manager.cmd_kick(event, "target1")]
        assert len(results) == 1
        assert "已踢出" in results[0]

    @pytest.mark.asyncio
    async def test_kick_failure(self, manager):
        async def failing_kick(group_id, target_id):
            raise RuntimeError("bot not admin")
        manager.context.kick_group_member = failing_kick
        event = FakeEvent(sender_id="admin1")
        results = [r async for r in manager.cmd_kick(event, "target1")]
        assert len(results) == 1
        assert "失败" in results[0]
        assert "bot not admin" in results[0]


# ====================================================================
# Tests for cmd_mute
# ====================================================================

class TestCmdMute:
    @pytest.mark.asyncio
    async def test_mute_success_default_duration(self, manager):
        event = FakeEvent(sender_id="admin1")
        results = [r async for r in manager.cmd_mute(event, "target1")]
        assert len(results) == 1
        assert "10 分钟" in results[0]

    @pytest.mark.asyncio
    async def test_mute_custom_duration(self, manager):
        event = FakeEvent(sender_id="admin1")
        results = [r async for r in manager.cmd_mute(event, "target1", 30)]
        assert len(results) == 1
        assert "30 分钟" in results[0]

    @pytest.mark.asyncio
    async def test_mute_denied_non_admin(self, manager):
        event = FakeEvent(sender_id="nobody")
        results = [r async for r in manager.cmd_mute(event, "target1", 5)]
        assert len(results) == 1
        assert "没有权限" in results[0]

    @pytest.mark.asyncio
    async def test_mute_allowed_when_admin_list_empty(self, manager):
        manager.config["admin_user_ids"] = []
        event = FakeEvent(sender_id="anyone")
        results = [r async for r in manager.cmd_mute(event, "target1")]
        assert len(results) == 1
        assert "已禁言" in results[0]

    @pytest.mark.asyncio
    async def test_mute_passes_seconds_to_context(self, manager):
        captured = {}
        async def capture_mute(group_id, target_id, duration_seconds):
            captured["duration"] = duration_seconds
        manager.context.mute_group_member = capture_mute
        event = FakeEvent(sender_id="admin1")
        _ = [r async for r in manager.cmd_mute(event, "target1", 5)]
        assert captured["duration"] == 300  # 5 minutes * 60

    @pytest.mark.asyncio
    async def test_mute_failure(self, manager):
        async def failing_mute(group_id, target_id, dur):
            raise RuntimeError("insufficient perms")
        manager.context.mute_group_member = failing_mute
        event = FakeEvent(sender_id="admin1")
        results = [r async for r in manager.cmd_mute(event, "target1")]
        assert len(results) == 1
        assert "失败" in results[0]


# ====================================================================
# Tests for cmd_welcome
# ====================================================================

class TestCmdWelcome:
    @pytest.mark.asyncio
    async def test_update_welcome_message(self, manager):
        event = FakeEvent(sender_id="admin1")
        results = [r async for r in manager.cmd_welcome(event, msg="Hi {user}!")]
        assert len(results) == 1
        assert "Hi {user}!" in results[0]
        assert manager.config["welcome_message"] == "Hi {user}!"
        assert manager.config._saved is True

    @pytest.mark.asyncio
    async def test_welcome_denied_non_admin(self, manager):
        event = FakeEvent(sender_id="nobody")
        results = [r async for r in manager.cmd_welcome(event, msg="Hi")]
        assert "没有权限" in results[0]
        assert manager.config._saved is False

    @pytest.mark.asyncio
    async def test_welcome_allowed_when_admin_list_empty(self, manager):
        manager.config["admin_user_ids"] = []
        event = FakeEvent(sender_id="anyone")
        results = [r async for r in manager.cmd_welcome(event, msg="Welcome {user}")]
        assert "Welcome {user}" in results[0]
        assert manager.config["welcome_message"] == "Welcome {user}"
