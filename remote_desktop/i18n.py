from __future__ import annotations

from typing import Callable

SUPPORTED_LANGS = ("zh_CN", "en_US")

_STRINGS: dict[str, dict[str, str]] = {
    "zh_CN": {
        "app_title": "远程桌面 — 设备管理",
        "local_control": "本机远控",
        "local_control_hint": "开启后，其他设备可连接本机",
        "local_name": "本机名称：{name}",
        "device_code": "设备识别码（本地标识）",
        "verify_code": "验证码",
        "show": "显示",
        "port": "端口",
        "local_ip": "本机 IP：",
        "start_host": "开启远控",
        "stop_host": "停止远控",
        "refresh_local": "刷新本机信息",
        "regen_code": "重新生成验证码",
        "host_off": "远控未开启",
        "host_on": "远控已开启 · 端口 {port}",
        "host_crashed": "远控异常退出",
        "device_list": "设备列表",
        "settings": "设置",
        "quick_connect": "快速连接",
        "search": "搜索",
        "col_name": "设备名称",
        "col_address": "地址",
        "col_status": "状态",
        "col_last": "最近连接",
        "add_device": "添加设备",
        "edit": "编辑",
        "delete": "删除",
        "refresh_status": "刷新状态",
        "remote_control": "远程控制",
        "ready": "就绪",
        "online": "在线",
        "offline": "离线",
        "unknown": "未知",
        "tip": "提示",
        "error": "错误",
        "confirm": "确认",
        "cancel": "取消",
        "save": "保存",
        "ok": "确定",
        "fill_host": "请填写主机地址",
        "bad_port": "端口无效",
        "select_device": "请先选择设备",
        "delete_confirm": "删除设备「{name}」？",
        "device_deleted": "设备已删除",
        "added": "已添加：{name}",
        "updated": "已更新：{name}",
        "settings_saved": "设置已保存",
        "stop_before_regen": "请先停止远控再修改验证码",
        "code_updated": "验证码已更新",
        "empty_password": "验证码不能为空",
        "host_started": "本机远控已开启（端口 {port}）",
        "host_stopped": "本机远控已停止",
        "host_crash_msg": "本机远控异常退出，请检查端口占用或权限",
        "connecting": "正在连接 {title} ({host}:{port})",
        "status_updated": "状态已更新：在线 {online}/{total}",
        "add_title": "添加设备",
        "edit_title": "编辑设备",
        "field_name": "设备名称",
        "field_host": "主机地址",
        "field_port": "端口",
        "field_password": "验证码/密码",
        "field_notes": "备注",
        "settings_title": "设置",
        "language": "语言",
        "lang_zh": "中文",
        "lang_en": "English",
        "max_fps": "最大帧率 FPS",
        "jpeg_quality": "JPEG 质量",
        "scale": "缩放比例",
        "probe_interval": "自动探测间隔(秒)",
        "invalid_number": "请输入有效数字",
        "quick_host": "主机地址 / IP：",
        "quick_port": "端口：",
        "quick_password": "验证码/密码：",
        "quick_save": "是否同时保存到设备列表？",
        "viewer_title": "远程控制 — {name}",
        "viewer_connecting": "正在连接…",
        "viewer_reconnecting": "正在重连… ({sec}s)",
        "viewer_disconnected": "连接已断开",
        "viewer_auth_failed": "鉴权失败",
        "font_hint": "若中文显示异常，请安装 Noto CJK / 文泉驿字体",
    },
    "en_US": {
        "app_title": "Remote Desktop — Devices",
        "local_control": "This PC",
        "local_control_hint": "Allow other devices to control this PC",
        "local_name": "Name: {name}",
        "device_code": "Device ID (local label)",
        "verify_code": "Passcode",
        "show": "Show",
        "port": "Port",
        "local_ip": "Local IP:",
        "start_host": "Enable Remote",
        "stop_host": "Disable Remote",
        "refresh_local": "Refresh Local Info",
        "regen_code": "Regenerate Passcode",
        "host_off": "Remote disabled",
        "host_on": "Remote enabled · port {port}",
        "host_crashed": "Remote stopped unexpectedly",
        "device_list": "Devices",
        "settings": "Settings",
        "quick_connect": "Quick Connect",
        "search": "Search",
        "col_name": "Name",
        "col_address": "Address",
        "col_status": "Status",
        "col_last": "Last Connected",
        "add_device": "Add Device",
        "edit": "Edit",
        "delete": "Delete",
        "refresh_status": "Refresh Status",
        "remote_control": "Remote Control",
        "ready": "Ready",
        "online": "Online",
        "offline": "Offline",
        "unknown": "Unknown",
        "tip": "Notice",
        "error": "Error",
        "confirm": "Confirm",
        "cancel": "Cancel",
        "save": "Save",
        "ok": "OK",
        "fill_host": "Please enter host address",
        "bad_port": "Invalid port",
        "select_device": "Please select a device first",
        "delete_confirm": "Delete device \"{name}\"?",
        "device_deleted": "Device deleted",
        "added": "Added: {name}",
        "updated": "Updated: {name}",
        "settings_saved": "Settings saved",
        "stop_before_regen": "Stop remote before changing passcode",
        "code_updated": "Passcode updated",
        "empty_password": "Passcode cannot be empty",
        "host_started": "Remote enabled (port {port})",
        "host_stopped": "Remote disabled",
        "host_crash_msg": "Remote crashed. Check port usage or permissions.",
        "connecting": "Connecting {title} ({host}:{port})",
        "status_updated": "Status updated: online {online}/{total}",
        "add_title": "Add Device",
        "edit_title": "Edit Device",
        "field_name": "Device Name",
        "field_host": "Host",
        "field_port": "Port",
        "field_password": "Passcode",
        "field_notes": "Notes",
        "settings_title": "Settings",
        "language": "Language",
        "lang_zh": "中文",
        "lang_en": "English",
        "max_fps": "Max FPS",
        "jpeg_quality": "JPEG Quality",
        "scale": "Scale",
        "probe_interval": "Probe Interval (sec)",
        "invalid_number": "Please enter valid numbers",
        "quick_host": "Host / IP:",
        "quick_port": "Port:",
        "quick_password": "Passcode:",
        "quick_save": "Also save to device list?",
        "viewer_title": "Remote Control — {name}",
        "viewer_connecting": "Connecting…",
        "viewer_reconnecting": "Reconnecting… ({sec}s)",
        "viewer_disconnected": "Disconnected",
        "viewer_auth_failed": "Authentication failed",
        "font_hint": "If CJK glyphs are missing, install Noto CJK / WenQuanYi fonts",
    },
}


class I18n:
    def __init__(self, lang: str = "zh_CN") -> None:
        self._lang = lang if lang in _STRINGS else "zh_CN"
        self._listeners: list[Callable[[], None]] = []

    @property
    def lang(self) -> str:
        return self._lang

    def set_lang(self, lang: str) -> None:
        if lang not in _STRINGS:
            lang = "zh_CN"
        if lang == self._lang:
            return
        self._lang = lang
        for cb in list(self._listeners):
            cb()

    def on_change(self, callback: Callable[[], None]) -> None:
        self._listeners.append(callback)

    def t(self, key: str, **kwargs: object) -> str:
        table = _STRINGS.get(self._lang) or _STRINGS["zh_CN"]
        text = table.get(key) or _STRINGS["en_US"].get(key) or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except (KeyError, ValueError):
                return text
        return text


# Process-wide helper used by UI modules.
i18n = I18n()
