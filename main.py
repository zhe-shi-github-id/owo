# -*- coding: utf-8 -*-
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Star, register
from astrbot.api import logger
import os, json


def load_json(p, default):
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return default
    return default


def save_json(p, data):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@register("groupmgr", "owo", "群聊管理助手", "0.1.0", "https://docs.astrbot.app")
class GroupManager(Star):
    def __init__(self, context, config):
        super().__init__(context)
        self.config = config
        self.data_dir = os.path.join(self.context.root_data_dir, "plugins", "astrbot_plugin_groupmgr", "data")
        self.group_states = load_json(os.path.join(self.data_dir, "group_states.json"), {})

    async def terminate(self):
        save_json(os.path.join(self.data_dir, "group_states.json"), self.group_states)

    # =============== 共享工具方法 ===============

    def _is_admin(self, event: AstrMessageEvent) -> bool:
        """检查发送者是否为管理员。若未配置管理员列表则所有人均视为管理员。"""
        admin_list = self.config.get("admin_user_ids", [])
        return not admin_list or event.get_sender_id() in admin_list

    async def _exec_group_action(self, event: AstrMessageEvent, coro, success_msg: str, fail_prefix: str):
        """执行群操作并统一处理成功/失败响应。"""
        try:
            await coro
            yield event.plain_result(success_msg)
        except Exception as e:
            yield event.plain_result(f"{fail_prefix}：{str(e)}")

    # =============== 自动欢迎新成员 ===============
    @filter.event_notice_type(filter.EventNoticeType.GROUP_MEMBER_INCREASE)
    async def on_member_join(self, event: AstrMessageEvent):
        if not self.config.get("enable_welcome", True):
            return
        welcome_text = self.config.get("welcome_message", "欢迎 {user} 加入群聊！")
        user_name = event.message_obj.user_name or event.message_obj.user_id
        yield event.plain_result(welcome_text.replace("{user}", user_name))

    # =============== 关键词屏蔽 ===============
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        text = event.message_str.strip()
        for kw in self.config.get("blocked_keywords", []):
            if kw in text:
                logger.info(f"[关键词屏蔽] 群 {event.group_id} 检测到: {kw}")
                yield event.plain_result(f"检测到违规关键词\u201c{kw}\u201d，请注意文明发言！")
                event.stop_event()
                return

    # =============== 踢人命令 ===============
    @filter.command("kick")
    async def cmd_kick(self, event: AstrMessageEvent, target_id: str):
        """踢人命令：/kick QQ号"""
        if not self._is_admin(event):
            yield event.plain_result("你没有权限使用该命令。")
            return
        async for result in self._exec_group_action(
            event,
            self.context.kick_group_member(event.message_obj.group_id, target_id),
            f"已踢出 {target_id}",
            "踢人失败",
        ):
            yield result

    # =============== 禁言命令 ===============
    @filter.command("mute")
    async def cmd_mute(self, event: AstrMessageEvent, target_id: str, duration: int = 10):
        """禁言命令：/mute QQ号 时长(分钟)"""
        if not self._is_admin(event):
            yield event.plain_result("你没有权限使用该命令。")
            return
        async for result in self._exec_group_action(
            event,
            self.context.mute_group_member(event.message_obj.group_id, target_id, duration * 60),
            f"已禁言 {target_id} {duration} 分钟",
            "禁言失败",
        ):
            yield result

    # =============== 修改欢迎语命令 ===============
    @filter.command("welcome")
    async def cmd_welcome(self, event: AstrMessageEvent, *, msg: str):
        """修改欢迎语：/welcome 欢迎 {user} 来到群里"""
        if not self._is_admin(event):
            yield event.plain_result("你没有权限使用该命令。")
            return
        self.config["welcome_message"] = msg
        self.config.save_config()
        yield event.plain_result(f"已更新欢迎语为：{msg}")
