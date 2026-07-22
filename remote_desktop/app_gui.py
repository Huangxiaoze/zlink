from __future__ import annotations

import logging
import subprocess
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any

from .config import HostConfig, NetConfig, StreamConfig
from .devices import Device, DeviceStore, list_local_ipv4, make_verify_code, probe_online
from .host import RemoteHost

MAIN_SCRIPT = Path(__file__).resolve().parents[1] / "main.py"

log = logging.getLogger(__name__)

# Restrained green accent (remote-tool style), avoid purple/cream AI defaults.
COLOR_BG = "#F3F5F7"
COLOR_SIDE = "#1F2A30"
COLOR_SIDE_TEXT = "#E8EEF2"
COLOR_ACCENT = "#2F9E5E"
COLOR_ACCENT_DARK = "#247A49"
COLOR_CARD = "#FFFFFF"
COLOR_MUTED = "#6B7780"
COLOR_ONLINE = "#1B8A4A"
COLOR_OFFLINE = "#A33B3B"
COLOR_UNKNOWN = "#8A8F96"


class DeviceDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, title: str, device: Device | None = None) -> None:
        super().__init__(master)
        self.title(title)
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.result: Device | None = None
        self._device = device

        body = ttk.Frame(self, padding=16)
        body.grid(row=0, column=0, sticky="nsew")

        self.var_name = tk.StringVar(value=device.name if device else "")
        self.var_host = tk.StringVar(value=device.host if device else "")
        self.var_port = tk.StringVar(value=str(device.port if device else 5959))
        self.var_password = tk.StringVar(value=device.password if device else "")
        self.var_notes = tk.StringVar(value=device.notes if device else "")

        rows = [
            ("设备名称", self.var_name),
            ("主机地址", self.var_host),
            ("端口", self.var_port),
            ("验证码/密码", self.var_password),
            ("备注", self.var_notes),
        ]
        for i, (label, var) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", pady=4)
            show = "*" if "密码" in label or "验证码" in label else None
            ttk.Entry(body, textvariable=var, width=36, show=show).grid(row=i, column=1, sticky="ew", pady=4)

        btns = ttk.Frame(body)
        btns.grid(row=len(rows), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btns, text="保存", command=self._on_ok).pack(side=tk.RIGHT)

        self.bind("<Return>", lambda _e: self._on_ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.after(50, lambda: self.focus_force())

    def _on_ok(self) -> None:
        name = self.var_name.get().strip()
        host = self.var_host.get().strip()
        if not host:
            messagebox.showwarning("提示", "请填写主机地址", parent=self)
            return
        try:
            port = int(self.var_port.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "端口无效", parent=self)
            return
        if self._device:
            device = Device(
                id=self._device.id,
                name=name or host,
                host=host,
                port=port,
                password=self.var_password.get(),
                notes=self.var_notes.get().strip(),
                last_connected=self._device.last_connected,
                created_at=self._device.created_at,
            )
        else:
            device = Device.create(
                name=name or host,
                host=host,
                port=port,
                password=self.var_password.get(),
                notes=self.var_notes.get().strip(),
            )
        self.result = device
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, store: DeviceStore) -> None:
        super().__init__(master)
        self.title("画质与探测设置")
        self.resizable(False, False)
        self.transient(master)
        self.grab_set()
        self.store = store
        s = store.settings

        body = ttk.Frame(self, padding=16)
        body.grid(row=0, column=0)
        self.var_fps = tk.StringVar(value=str(s.max_fps))
        self.var_quality = tk.StringVar(value=str(s.jpeg_quality))
        self.var_scale = tk.StringVar(value=str(s.scale))
        self.var_probe = tk.StringVar(value=str(s.auto_probe_s))

        fields = [
            ("最大帧率 FPS", self.var_fps),
            ("JPEG 质量", self.var_quality),
            ("缩放比例", self.var_scale),
            ("自动探测间隔(秒)", self.var_probe),
        ]
        for i, (label, var) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=i, column=0, sticky="w", pady=4)
            ttk.Entry(body, textvariable=var, width=18).grid(row=i, column=1, sticky="ew", pady=4)

        btns = ttk.Frame(body)
        btns.grid(row=len(fields), column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(btns, text="取消", command=self.destroy).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(btns, text="保存", command=self._save).pack(side=tk.RIGHT)

    def _save(self) -> None:
        try:
            self.store.settings.max_fps = float(self.var_fps.get())
            self.store.settings.jpeg_quality = int(self.var_quality.get())
            self.store.settings.scale = float(self.var_scale.get())
            self.store.settings.auto_probe_s = max(3.0, float(self.var_probe.get()))
        except ValueError:
            messagebox.showwarning("提示", "请输入有效数字", parent=self)
            return
        self.store.save()
        self.destroy()


class RemoteDesktopApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.store = DeviceStore()
        self._status: dict[str, str] = {}
        self._host: RemoteHost | None = None
        self._host_thread: threading.Thread | None = None
        self._probe_stop = threading.Event()
        self._client_procs: list[subprocess.Popen[Any]] = []
        self._filter = tk.StringVar()
        self._show_password = tk.BooleanVar(value=False)

        self._setup_style()
        self._build_ui()
        self._refresh_local_info()
        self._reload_tree()
        self._start_probe_loop()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self) -> None:
        self.root.title("Remote Desktop — 设备管理")
        self.root.geometry("980x620")
        self.root.minsize(860, 520)
        self.root.configure(bg=COLOR_BG)
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=COLOR_BG)
        style.configure("Card.TFrame", background=COLOR_CARD)
        style.configure("Side.TFrame", background=COLOR_SIDE)
        style.configure("Side.TLabel", background=COLOR_SIDE, foreground=COLOR_SIDE_TEXT)
        style.configure("Muted.TLabel", background=COLOR_BG, foreground=COLOR_MUTED)
        style.configure("Title.TLabel", background=COLOR_BG, foreground="#1B2429", font=("Segoe UI", 16, "bold"))
        style.configure("CardTitle.TLabel", background=COLOR_CARD, foreground="#1B2429", font=("Segoe UI", 11, "bold"))
        style.configure("Treeview", rowheight=28, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"))
        style.map(
            "Accent.TButton",
            background=[("!disabled", COLOR_ACCENT), ("pressed", COLOR_ACCENT_DARK), ("active", COLOR_ACCENT_DARK)],
            foreground=[("!disabled", "white")],
        )

    def _build_ui(self) -> None:
        shell = ttk.Frame(self.root)
        shell.pack(fill=tk.BOTH, expand=True)

        side = tk.Frame(shell, bg=COLOR_SIDE, width=280)
        side.pack(side=tk.LEFT, fill=tk.Y)
        side.pack_propagate(False)

        tk.Label(
            side,
            text="本机远控",
            bg=COLOR_SIDE,
            fg="white",
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w", padx=20, pady=(22, 4))
        tk.Label(
            side,
            text="开启后，其他设备可连接本机",
            bg=COLOR_SIDE,
            fg="#9AA7B0",
            font=("Segoe UI", 9),
        ).pack(anchor="w", padx=20, pady=(0, 16))

        self.lbl_local_name = tk.Label(side, text="", bg=COLOR_SIDE, fg=COLOR_SIDE_TEXT, font=("Segoe UI", 11))
        self.lbl_local_name.pack(anchor="w", padx=20, pady=2)
        self.lbl_code = tk.Label(side, text="", bg=COLOR_SIDE, fg="white", font=("Consolas", 18, "bold"))
        self.lbl_code.pack(anchor="w", padx=20, pady=(10, 2))
        tk.Label(side, text="设备识别码（本地标识）", bg=COLOR_SIDE, fg="#9AA7B0", font=("Segoe UI", 8)).pack(
            anchor="w", padx=20
        )

        verify_row = tk.Frame(side, bg=COLOR_SIDE)
        verify_row.pack(fill=tk.X, padx=20, pady=(16, 0))
        tk.Label(verify_row, text="验证码", bg=COLOR_SIDE, fg="#9AA7B0", font=("Segoe UI", 9)).pack(anchor="w")
        self.lbl_verify = tk.Label(verify_row, text="", bg=COLOR_SIDE, fg="white", font=("Consolas", 16, "bold"))
        self.lbl_verify.pack(anchor="w")
        tk.Checkbutton(
            verify_row,
            text="显示",
            variable=self._show_password,
            command=self._refresh_local_info,
            bg=COLOR_SIDE,
            fg="#9AA7B0",
            selectcolor=COLOR_SIDE,
            activebackground=COLOR_SIDE,
            activeforeground="white",
            highlightthickness=0,
        ).pack(anchor="w", pady=(4, 0))

        port_row = tk.Frame(side, bg=COLOR_SIDE)
        port_row.pack(fill=tk.X, padx=20, pady=(14, 0))
        tk.Label(port_row, text="端口", bg=COLOR_SIDE, fg="#9AA7B0", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        self.var_host_port = tk.StringVar(value=str(self.store.settings.host_port))
        tk.Entry(port_row, textvariable=self.var_host_port, width=8, font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=8)

        self.lbl_ips = tk.Label(
            side,
            text="",
            bg=COLOR_SIDE,
            fg="#C5D0D7",
            font=("Segoe UI", 9),
            justify=tk.LEFT,
            wraplength=240,
        )
        self.lbl_ips.pack(anchor="w", padx=20, pady=(14, 0))

        self.btn_host = tk.Button(
            side,
            text="开启远控",
            command=self._toggle_host,
            bg=COLOR_ACCENT,
            fg="white",
            activebackground=COLOR_ACCENT_DARK,
            activeforeground="white",
            relief=tk.FLAT,
            font=("Segoe UI", 11, "bold"),
            cursor="hand2",
            padx=12,
            pady=8,
        )
        self.btn_host.pack(fill=tk.X, padx=20, pady=(22, 8))

        tk.Button(
            side,
            text="刷新本机信息",
            command=self._refresh_local_info,
            bg="#2B3940",
            fg="white",
            activebackground="#364851",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=8,
            pady=6,
        ).pack(fill=tk.X, padx=20, pady=(0, 8))

        tk.Button(
            side,
            text="重新生成验证码",
            command=self._regen_password,
            bg="#2B3940",
            fg="white",
            activebackground="#364851",
            relief=tk.FLAT,
            font=("Segoe UI", 9),
            cursor="hand2",
            padx=8,
            pady=6,
        ).pack(fill=tk.X, padx=20)

        self.lbl_host_state = tk.Label(side, text="远控未开启", bg=COLOR_SIDE, fg="#F0C674", font=("Segoe UI", 9))
        self.lbl_host_state.pack(anchor="w", padx=20, pady=(18, 20))

        main = ttk.Frame(shell, padding=(18, 16, 18, 12))
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        header = ttk.Frame(main)
        header.pack(fill=tk.X)
        ttk.Label(header, text="设备列表", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="设置", command=self._open_settings).pack(side=tk.RIGHT, padx=(8, 0))
        ttk.Button(header, text="快速连接", command=self._quick_connect).pack(side=tk.RIGHT)

        search = ttk.Frame(main)
        search.pack(fill=tk.X, pady=(14, 8))
        ttk.Label(search, text="搜索").pack(side=tk.LEFT)
        entry = ttk.Entry(search, textvariable=self._filter)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)

        table_card = tk.Frame(main, bg=COLOR_CARD, highlightbackground="#D7DEE5", highlightthickness=1)
        table_card.pack(fill=tk.BOTH, expand=True)

        columns = ("name", "address", "status", "last")
        self.tree = ttk.Treeview(table_card, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("name", text="设备名称")
        self.tree.heading("address", text="地址")
        self.tree.heading("status", text="状态")
        self.tree.heading("last", text="最近连接")
        self.tree.column("name", width=180, anchor="w")
        self.tree.column("address", width=220, anchor="w")
        self.tree.column("status", width=90, anchor="center")
        self.tree.column("last", width=160, anchor="center")
        scroll = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(1, 0), pady=1)
        scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=1)
        self.tree.bind("<Double-1>", lambda _e: self._connect_selected())
        self.tree.tag_configure("online", foreground=COLOR_ONLINE)
        self.tree.tag_configure("offline", foreground=COLOR_OFFLINE)
        self.tree.tag_configure("unknown", foreground=COLOR_UNKNOWN)
        self._filter.trace_add("write", lambda *_: self._reload_tree())

        actions = ttk.Frame(main)
        actions.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(actions, text="添加设备", command=self._add_device).pack(side=tk.LEFT)
        ttk.Button(actions, text="编辑", command=self._edit_device).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="删除", command=self._delete_device).pack(side=tk.LEFT)
        ttk.Button(actions, text="刷新状态", command=self._probe_now).pack(side=tk.LEFT, padx=6)
        ttk.Button(actions, text="远程控制", style="Accent.TButton", command=self._connect_selected).pack(
            side=tk.RIGHT
        )

        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(main, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(10, 0))

    def _refresh_local_info(self) -> None:
        s = self.store.settings
        self.lbl_local_name.configure(text=f"本机名称：{s.local_name}")
        self.lbl_code.configure(text=self._format_code(s.device_code))
        pwd = s.host_password
        self.lbl_verify.configure(text=pwd if self._show_password.get() else ("*" * max(4, len(pwd))))
        ips = list_local_ipv4()
        self.lbl_ips.configure(text="本机 IP：\n" + "\n".join(ips))
        self.var_host_port.set(str(s.host_port))

    @staticmethod
    def _format_code(code: str) -> str:
        digits = "".join(ch for ch in code if ch.isdigit())
        if len(digits) == 9:
            return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
        return code

    def _reload_tree(self) -> None:
        keyword = self._filter.get().strip().lower()
        for item in self.tree.get_children():
            self.tree.delete(item)
        for device in self.store.devices:
            hay = f"{device.name} {device.host} {device.notes}".lower()
            if keyword and keyword not in hay:
                continue
            status = self._status.get(device.id, "未知")
            tag = {"在线": "online", "离线": "offline"}.get(status, "unknown")
            last = _fmt_time(device.last_connected)
            self.tree.insert(
                "",
                tk.END,
                iid=device.id,
                values=(device.name, f"{device.host}:{device.port}", status, last),
                tags=(tag,),
            )

    def _selected_device(self) -> Device | None:
        sel = self.tree.selection()
        if not sel:
            return None
        return self.store.get(sel[0])

    def _add_device(self) -> None:
        dialog = DeviceDialog(self.root, "添加设备")
        self.root.wait_window(dialog)
        if dialog.result:
            self.store.upsert(dialog.result)
            self._reload_tree()
            self._set_status(f"已添加：{dialog.result.name}")
            self._probe_now()

    def _edit_device(self) -> None:
        device = self._selected_device()
        if not device:
            messagebox.showinfo("提示", "请先选择设备", parent=self.root)
            return
        dialog = DeviceDialog(self.root, "编辑设备", device)
        self.root.wait_window(dialog)
        if dialog.result:
            self.store.upsert(dialog.result)
            self._reload_tree()
            self._set_status(f"已更新：{dialog.result.name}")

    def _delete_device(self) -> None:
        device = self._selected_device()
        if not device:
            messagebox.showinfo("提示", "请先选择设备", parent=self.root)
            return
        if not messagebox.askyesno("确认", f"删除设备「{device.name}」？", parent=self.root):
            return
        self.store.remove(device.id)
        self._status.pop(device.id, None)
        self._reload_tree()
        self._set_status("设备已删除")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self.root, self.store)
        self.root.wait_window(dialog)
        self._set_status("设置已保存")

    def _regen_password(self) -> None:
        if self._host is not None:
            messagebox.showwarning("提示", "请先停止远控再修改验证码", parent=self.root)
            return
        self.store.settings.host_password = make_verify_code()
        self.store.save()
        self._refresh_local_info()
        self._set_status("验证码已更新")

    def _toggle_host(self) -> None:
        if self._host is not None:
            self._stop_host()
            return
        self._start_host()

    def _start_host(self) -> None:
        try:
            port = int(self.var_host_port.get().strip())
            if not (1 <= port <= 65535):
                raise ValueError
        except ValueError:
            messagebox.showwarning("提示", "端口无效", parent=self.root)
            return
        password = self.store.settings.host_password.strip()
        if not password:
            messagebox.showwarning("提示", "验证码不能为空", parent=self.root)
            return

        self.store.settings.host_port = port
        self.store.settings.host_password = password
        self.store.save()

        stream = StreamConfig(
            max_fps=self.store.settings.max_fps,
            jpeg_quality=self.store.settings.jpeg_quality,
            scale=self.store.settings.scale,
        ).clamp()
        net = NetConfig(host=self.store.settings.host_bind, port=port, password=password)
        cfg = HostConfig(net=net, stream=stream, bind_require_password=True)
        host = RemoteHost(cfg)
        self._host = host

        def runner() -> None:
            try:
                host.run()
            except Exception:
                log.exception("host failed")
                self.root.after(0, lambda: self._on_host_crashed())

        self._host_thread = threading.Thread(target=runner, name="gui-host", daemon=True)
        self._host_thread.start()
        self.btn_host.configure(text="停止远控", bg="#C24B4B", activebackground="#9E3B3B")
        self.lbl_host_state.configure(text=f"远控已开启 · 端口 {port}", fg="#7DCEA0")
        self._set_status(f"本机远控已开启（端口 {port}）")

    def _stop_host(self) -> None:
        host = self._host
        self._host = None
        if host:
            host.stop()
        self.btn_host.configure(text="开启远控", bg=COLOR_ACCENT, activebackground=COLOR_ACCENT_DARK)
        self.lbl_host_state.configure(text="远控未开启", fg="#F0C674")
        self._set_status("本机远控已停止")

    def _on_host_crashed(self) -> None:
        self._host = None
        self.btn_host.configure(text="开启远控", bg=COLOR_ACCENT, activebackground=COLOR_ACCENT_DARK)
        self.lbl_host_state.configure(text="远控异常退出", fg="#E07474")
        messagebox.showerror("错误", "本机远控异常退出，请检查端口占用或权限", parent=self.root)

    def _connect_selected(self) -> None:
        device = self._selected_device()
        if not device:
            messagebox.showinfo("提示", "请先选择设备", parent=self.root)
            return
        self._launch_client(device.host, device.port, device.password, device.name, device.id)

    def _quick_connect(self) -> None:
        host = simpledialog.askstring("快速连接", "主机地址 / IP：", parent=self.root)
        if not host:
            return
        port_s = simpledialog.askstring("快速连接", "端口：", initialvalue="5959", parent=self.root)
        if not port_s:
            return
        try:
            port = int(port_s)
        except ValueError:
            messagebox.showwarning("提示", "端口无效", parent=self.root)
            return
        password = simpledialog.askstring("快速连接", "验证码/密码：", show="*", parent=self.root) or ""
        save = messagebox.askyesno("快速连接", "是否同时保存到设备列表？", parent=self.root)
        device_id = None
        if save:
            device = Device.create(name=host, host=host, port=port, password=password)
            self.store.upsert(device)
            device_id = device.id
            self._reload_tree()
        self._launch_client(host, port, password, host, device_id)

    def _launch_client(
        self,
        host: str,
        port: int,
        password: str,
        title: str,
        device_id: str | None,
    ) -> None:
        # Separate process avoids tkinter + pygame main-thread conflicts.
        cmd = [
            sys.executable,
            str(MAIN_SCRIPT),
            "client",
            "--host",
            host,
            "--port",
            str(port),
            "--password",
            password,
            "--fps",
            str(self.store.settings.max_fps),
            "--quality",
            str(self.store.settings.jpeg_quality),
            "--scale",
            str(self.store.settings.scale),
        ]
        try:
            proc = subprocess.Popen(cmd, cwd=str(MAIN_SCRIPT.parent))
        except OSError as exc:
            messagebox.showerror("错误", f"无法启动远程窗口：{exc}", parent=self.root)
            return
        self._client_procs.append(proc)
        if device_id:
            self.store.touch_connected(device_id)
            self._reload_tree()
        self._set_status(f"正在连接 {title} ({host}:{port})")

    def _probe_now(self) -> None:
        threading.Thread(target=self._probe_devices, name="probe-now", daemon=True).start()

    def _start_probe_loop(self) -> None:
        def loop() -> None:
            while not self._probe_stop.is_set():
                self._probe_devices()
                self._probe_stop.wait(max(3.0, self.store.settings.auto_probe_s))

        threading.Thread(target=loop, name="probe-loop", daemon=True).start()

    def _probe_devices(self) -> None:
        snapshot = list(self.store.devices)
        results: dict[str, str] = {}
        for device in snapshot:
            online = probe_online(device.host, device.port)
            results[device.id] = "在线" if online else "离线"
        def apply() -> None:
            self._status.update(results)
            self._reload_tree()
            online_n = sum(1 for v in results.values() if v == "在线")
            self._set_status(f"状态已更新：在线 {online_n}/{len(results)}")

        self.root.after(0, apply)

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _on_close(self) -> None:
        self._probe_stop.set()
        if self._host is not None:
            self._stop_host()
        for proc in self._client_procs:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except OSError:
                    pass
        self.root.destroy()


def _fmt_time(ts: float | None) -> str:
    if not ts:
        return "-"
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def run_app() -> None:
    root = tk.Tk()
    RemoteDesktopApp(root)
    root.mainloop()
