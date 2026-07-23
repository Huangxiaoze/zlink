# Remote Desktop — AGENTS.md

> 分支：`compat/remote-ubuntu-18.04`  
> 目标平台：**Ubuntu 18.04（glibc 2.27）+ Python 3.8 + PySide2/Qt5**

本文档记录本项目的设计取舍、架构决策与编程规范，供后续开发与 AI Agent 协作时遵循。

## 1. 目标与边界

### 目标

- 用 **Python 3.8+** 实现跨平台远程桌面；本分支优先保证 **Ubuntu 18.04** 可运行
- 角色分离：**Host（被控端）** 抓屏并注入输入；**Client（主控端）** 显示画面并采集键鼠
- 提供 **向日葵风格设备管理 GUI（Qt）**：本机远控开关、设备卡片列表 CRUD、在线探测、一键远程控制
- **中英文切换**与 **主题切换**（浅色/深色/森绿）；Ubuntu 下通过 CJK 字体回退解决中文乱码
- 提供各平台 **PyInstaller 打包脚本**（`scripts/build_*.sh|ps1`）
- 优先保证 **流畅性**（低延迟、可丢帧、远程画面防闪烁）与 **稳定性**（心跳、超时、优雅断开、客户端重连）
- 直连 TCP 模式（Host 监听，Client 连接）；不实现向日葵式公网中继 / NAT 穿透（可后续扩展）

### 非目标（当前阶段不做）

- 完整商业级安全（端到端审计、证书体系、权限细粒度控制）
- WebRTC / 硬件编码（NVENC/VideoToolbox）优先路径
- 公网识别码解析（无中继时识别码仅为本地展示标识）
- 多显示器选择 UI、任意目录大文件传输（剪贴板文件有大小上限）

## 2. 架构决策（思考结论）

### 2.1 为什么不用共享内存做跨机通信

共享内存适合本机多进程。远程桌面跨机器，必须走网络。本项目采用：

```text
Host: capture → encode(JPEG) → TCP send
Client: TCP recv → decode → present
Client: input events → TCP send → Host inject
```

与管道/消息队列同类：数据经传输通道中转；与共享内存不同：双方地址空间完全独立，靠协议交换。

### 2.2 流畅性策略（刻意选择）

| 策略 | 原因 |
|------|------|
| 最新帧覆盖（drop stale frames） | 远程桌面要“当前画面”，宁可丢旧帧也不排队堆积 |
| JPEG + 可调质量/缩放 | 跨平台依赖少，CPU 编码稳定；质量随拥塞自适应 |
| 采集 / 编码 / 发送线程解耦 | 避免网络阻塞拖死抓屏 |
| TCP_NODELAY | 降低小包（输入事件）延迟 |
| 有界发送队列 | 防止内存无限增长 |

### 2.3 稳定性策略

- 应用层 **心跳** + 活动超时（`last_activity`，含大帧分片接收进度）
- **发送锁**：所有 `send_*` 必须经 `Connection` 锁，禁止多线程裸 `sock.send`
- **整帧原子发送**：拥塞时可整帧丢弃，绝不可半截发送后改发别的消息
- 键鼠：鼠标 move 限频（约 30Hz），down/up/key 立即发送
- Host **不要** 回显 HEARTBEAT（接收即刷新活性；回显易引发发送风暴/竞态）
- 消息 **长度前缀帧**，避免粘包/半包导致状态机崩溃
- Host 单会话；Client 指数退避重连
- 所有线程以 `threading.Event` 统一停机

### 2.4 可移植性策略

| 能力 | 库 | 说明 |
|------|-----|------|
| 截屏 | `mss` | Win/macOS/Linux(X11) 表现稳定 |
| 图像 | `Pillow` | JPEG 编解码 |
| 键鼠注入/采集 | `pynput` | 需系统辅助权限（见 README） |
| 管理界面 / 远程画面 | `PySide2`（优先）/ `PySide6`（回退） | 经 `qt_bind.py` 统一枚举与 API |
| 中英文 | `i18n.py` | 运行时可切换，写入 `settings.language` |
| CJK 字体 | `qt_fonts.py` | 字体族回退链，优先 Noto/文泉驿/雅黑 |

### 2.5 为何本分支不用 PySide6

- Ubuntu 18.04 仅有 **glibc 2.27**
- 官方 Qt6 / 新版 PySide6 轮子通常要求 **glibc ≥ 2.28**
- 因此本分支：**PySide2 5.15 + Python 3.8**；`qt_bind.py` 在缺少 PySide2 时回退 PySide6，便于现代机器开发自测

### 2.6 GUI 架构决策

```text
QApplication
  ├─ MainWindow（设备管理）
  │    ├─ 后台线程：RemoteHost
  │    └─ 后台线程：在线探测
  └─ ViewerShell（单一远程窗口）
       ├─ 自定义标题栏：会话 Tab + 窗口控制同一行
       └─ RemoteClientPage × N（QStackedWidget）
            ├─ 网络线程：收帧 / 心跳
            └─ QTimer(~16ms)：合并最新 JPEG 后上屏（防闪烁）
```

- **所有 Qt import 必须走 `qt_bind.py`**，禁止业务代码直接 `from PySide6...` / `from PySide2...`
- 对话框用 `dialog_exec()`（兼容 `exec_` / `exec`）
- **防闪烁要点**（改动时勿破坏）：
  1. 网络线程只保留最新帧，旧帧丢弃
  2. GUI 用 `QTimer` 合帧，不要每包立刻 `repaint`
  3. `RemoteCanvas` 使用 `WA_OpaquePaintEvent`，在同一次 `paintEvent` 内绘制
  4. 缩放结果按窗口尺寸缓存
  5. 用 `QImage.fromData(..., "JPEG")`
- **中文乱码**：启动时 `apply_app_font()`；Ubuntu 18.04 安装 `fonts-noto-cjk` 或 `fonts-wqy-microhei`
- 设备与设置持久化到用户配置目录（含 `language`）
- “设备识别码”仅本地展示；连接用 **IP + 端口 + 验证码**

平台注意：

- **Ubuntu 18.04**：Python 3.8（deadsnakes）、X11、见 `requirements-ubuntu1804.txt`
- **Linux Wayland**：`mss`/`pynput` 可能受限，优先 X11
- **macOS**：屏幕录制 + 辅助功能权限
- **Windows**：部分提升权限窗口注入可能失败

## 3. 目录结构

```text
remote/
  AGENTS.md                 # 本文件：决策与规范
  README.md                 # 用户使用说明
  requirements.txt
  pyproject.toml
  main.py                   # CLI / GUI 入口（默认 gui）
  remote_desktop/
    __init__.py
    config.py               # 默认参数与校验
    protocol.py             # 二进制帧协议
    codec.py                # 截屏缩放与 JPEG
    capture.py              # Host 采集循环
    input_io.py             # 键鼠映射与注入
    net.py                  # TCP 帧读写、心跳辅助
    host.py                 # 被控端
    client.py               # 主控端
    devices.py              # 设备列表 / 本机设置持久化
    i18n.py                 # 中英文文案
    themes.py               # 浅色/深色/森绿主题与 QSS
    qt_bind.py              # PySide2/PySide6 兼容层（本分支核心）
    qt_fonts.py             # CJK 字体选择
    app_gui.py              # Qt 设备管理界面（卡片列表）
    client.py               # Qt 远程画面（防闪烁）
    clipboard_sync.py       # 文字/文件剪贴板同步（Ctrl+Alt+C 推送 / Ctrl+Alt+V 拉取）
    file_transfer.py        # 专用远程文件传输（MsgType.FILE，落盘 Downloads/ZLink）
    remote_files.py         # 控制端远程文件浏览器（list/download）
    terminal_pty.py         # 被控端 PTY / 终端桥
    terminal_view.py        # 控制端远程终端窗口（pyte）
  scripts/build.py          # PyInstaller 跨平台打包入口
  scripts/build_windows.ps1
  scripts/build_linux.sh
  scripts/build_macos.sh
  requirements-ubuntu1804.txt  # 18.04 钉扎依赖
  requirements-build.txt       # pyinstaller
```

## 4. 协议规范

### 4.1 帧格式

```text
| magic 4B | type 1B | flags 1B | length 4B BE | payload length 字节 |
magic = b"RD01"
```

- `type`：见 `MsgType`
- `flags`：保留，当前为 0
- `length`：payload 字节数，最大 `MAX_PAYLOAD`（默认 16 MiB）

### 4.2 消息类型

| Type | 方向 | Payload |
|------|------|---------|
| HELLO | C→H | JSON：`{role, version, password?}`；`role=client` 远程桌面，`role=terminal` 直连终端，`role=probe` 探测 |
| HELLO_ACK | H→C | JSON：`{ok, reason?, mode?, screen_w?, screen_h?, features?}` |
| FRAME | H→C | JSON meta（utf-8）+ `\n\n` + JPEG bytes |
| MOUSE | C→H | JSON：归一化坐标 + 按键/滚轮 |
| KEY | C→H | JSON：key / action / modifiers |
| QUALITY | C→H | JSON：`{jpeg_quality, scale, max_fps}` |
| HEARTBEAT | 双向 | JSON：`{t}` |
| BYE | 双向 | JSON：`{reason}` |
| CLIPBOARD | 双向 | JSON meta + `\n\n` + blob（文字 UTF-8 或文件分片） |
| FILE | 双向 | JSON meta + `\n\n` + blob（专用文件传输分片） |
| TERM | 双向 | JSON meta + `\n\n` + blob（远程 PTY：open/data/resize/close） |

CLIPBOARD meta：

- 文字：`{"kind":"text"}`，blob 为 UTF-8 文本（≤2MiB）
- 文件：`{"kind":"file","id","name","size","offset","done"}`，blob 为分片（块 256KiB）

FILE meta（与剪贴板文件通道独立，不经系统剪贴板）：

- 分片：`{"op":"chunk","id","name","size","offset","done"}`，blob 为分片（块 256KiB；默认无单文件大小上限）
- 列目录：控制端 `{"op":"list","path"}` → 被控端 `list_ok` / `list_err`（entries 含 name/path/is_dir/size/mtime）
- 远程下载：控制端 `{"op":"download","path"}` → 被控端回传 `chunk` 分片（或 `download_err`）
- 能力协商：HELLO_ACK `features` 含 `"file_transfer"`

TERM meta：

- 打开：控制端 `{"op":"open","cols","rows"}` → 被控端 `open_ok` / `open_err`
- 数据：双向 `{"op":"data"}` + blob（stdin/stdout 字节流）
- 调整大小：控制端 `{"op":"resize","cols","rows"}`
- 关闭：控制端 `{"op":"close"}` / 被控端 `{"op":"closed"}`
- 能力协商：HELLO_ACK `features` 含 `"terminal"`
- `role=terminal`：独立会话（不占桌面锁、不推送画面），控制端主界面可直接连接

坐标使用 **相对屏幕归一化** `[0.0, 1.0]`，避免双方分辨率不一致。  
`PROTOCOL_VERSION = 2`（剪贴板 / 文件传输 / 终端能力通过 `features` 协商）。

### 4.3 扩展规则

- 新增消息类型只追加枚举值，不复用旧值
- JSON 字段采用加字段兼容，禁止随意改名
- 二进制 FRAME 分隔符固定为 `\n\n`，meta 必须是单行 JSON 或紧凑 JSON（不含该分隔符）

## 5. 编程规范

### 5.1 语言与风格

- Python 3.8+，使用 `from __future__ import annotations`
- 公共 API 加类型标注；用 `@dataclass`（**不要** `slots=True`，3.10 才支持）
- 禁止使用仅 3.10+ 的运行时特性（如 `match`、dataclass slots）
- 格式：4 空格缩进；字符串默认双引号
- 禁止无意义注释；注释只解释非显而易见的约束（权限、丢帧策略、协议边界）

### 5.2 并发

- I/O 与 CPU（编码）分离线程；共享状态用 `queue.Queue(maxsize=...)` 或锁
- 跨线程停止统一用 `threading.Event`
- 不在持锁时做网络阻塞调用
- 发送路径：**可丢弃旧 FRAME**；控制消息（MOUSE/KEY/HEARTBEAT/CLIPBOARD/FILE）不丢

### 5.3 错误处理

- 边界（断开、超时、鉴权失败）记 `warning`/`error`，不刷栈除非意外异常
- 套接字异常视为会话结束，走统一 `cleanup`
- 不对用户展示内部路径；CLI 给出可操作提示（权限、端口占用、密码错误）

### 5.4 安全底线

- 默认绑定 `0.0.0.0` 时必须要求密码（CLI 强制）
- 密码只做连接鉴权（SHA-256 恒定时间比较），**不声称加密传输**
- 不在日志中打印密码明文
- 后续若加公网暴露，必须先加 TLS

### 5.5 依赖原则

- 只引入实现必需的跨平台库（见 `requirements.txt`）
- 不把平台特定 `#ifdef` 逻辑散落各处：集中在 `capture.py` / `input_io.py`
- 禁止在库代码里 `sys.exit`；由 `main.py` 决定进程退出码

### 5.6 测试与手工验证

最低验收：

1. 本机 Host + Client loopback 可见画面
2. 鼠标移动/点击映射正确
3. 拔网线或杀 Client 后 Host 回到监听，不崩溃
4. 降低带宽时画面质量下降但操作仍可跟手（丢帧而非卡死）
5. GUI：添加/编辑/删除设备可持久化；开启本机远控后列表可探测在线；双击可打开控制窗口
6. 远程画面连续移动窗口内容时无明显黑闪；设置中切换中英文后主界面文案立即更新
7. Ubuntu 安装 Noto CJK 后中文不再方框/乱码

## 6. 性能参数默认值

定义于 `config.py`，调参优先改配置而非散落魔法数：

- `max_fps = 30`
- `jpeg_quality = 90`（拥塞时可降到 55；JPEG 使用 4:4:4）
- `scale = 1.0`（全分辨率采集；拥塞时优先降质量再降分辨率）
- `heartbeat_interval_s = 2.0`
- `heartbeat_timeout_s = 8.0`
- `send_queue_size = 2`（FRAME 队列极短，促发丢帧）

## 7. Agent 协作约定

修改本项目时：

1. 先读本文件与 `protocol.py`，保持协议兼容或显式升 `PROTOCOL_VERSION`
2. 改动流畅性相关逻辑时，说明对“丢帧 / 延迟 / CPU”的影响
3. 不主动扩展文件传输、中继服务器等大功能，除非用户明确要求
4. 用户可见说明更新 `README.md`；设计规范更新本文件
5. GUI 统一经 `qt_bind.py`；禁止再引入 tkinter/pygame 作为主界面或远程画面渲染路径
6. 新增可见文案必须同时写入 `i18n.py` 的 `zh_CN` 与 `en_US`
7. 改动 Qt API 时同时验证 PySide2（18.04）与 PySide6（回退）语义
