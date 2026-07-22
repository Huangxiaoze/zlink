# Remote Desktop — AGENTS.md

本文档记录本项目的设计取舍、架构决策与编程规范，供后续开发与 AI Agent 协作时遵循。

## 1. 目标与边界

### 目标

- 用 **Python 3.10+** 实现跨平台远程桌面（Linux / Windows / macOS）
- 角色分离：**Host（被控端）** 抓屏并注入输入；**Client（主控端）** 显示画面并采集键鼠
- 提供 **向日葵风格设备管理 GUI**：本机远控开关、设备列表 CRUD、在线探测、一键远程控制
- 优先保证 **流畅性**（低延迟、可丢帧）与 **稳定性**（心跳、超时、优雅断开、客户端重连）
- 直连 TCP 模式（Host 监听，Client 连接）；不实现向日葵式公网中继 / NAT 穿透（可后续扩展）

### 非目标（当前阶段不做）

- 完整商业级安全（端到端审计、证书体系、权限细粒度控制）
- WebRTC / 硬件编码（NVENC/VideoToolbox）优先路径
- 公网识别码解析（无中继时识别码仅为本地展示标识）
- 剪贴板同步、多显示器选择 UI、文件传输（预留协议扩展位）

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

- 应用层 **心跳**（双向）+ 读超时检测死连接
- 消息 **长度前缀帧**，避免粘包/半包导致状态机崩溃
- Host 单会话（同时仅一个控制端），简化锁与资源生命周期
- Client 支持指数退避重连
- 所有线程以 `threading.Event` 统一停机，禁止裸 `daemon` 依赖解释器退出

### 2.4 可移植性策略

| 能力 | 库 | 说明 |
|------|-----|------|
| 截屏 | `mss` | Win/macOS/Linux(X11) 表现稳定 |
| 图像 | `Pillow` | JPEG 编解码 |
| 键鼠注入/采集 | `pynput` | 需系统辅助权限（见 README） |
| 主控显示 | `pygame` | 固定帧呈现、键鼠事件统一 |
| 管理界面 | `tkinter`（标准库） | 设备管理主窗口，零额外 GUI 依赖 |

### 2.5 GUI 架构决策

```text
tkinter 主进程（设备管理）
  ├─ 后台线程：RemoteHost（本机被控）
  ├─ 后台线程：TCP 端口探测（在线/离线）
  └─ subprocess：python main.py client ...（远程画面窗口）
```

- **Client 必须独立进程**：`tkinter` 与 `pygame` 都倾向占用主线程/事件循环，同进程易卡死或抢焦点
- 设备与设置持久化到用户配置目录（非仓库内）：
  - Windows: `%APPDATA%/remote_desktop/devices.json`
  - macOS: `~/Library/Application Support/remote_desktop/devices.json`
  - Linux: `~/.config/remote_desktop/devices.json`
- “设备识别码”仅作本机展示/备注；真正连接仍使用 **IP + 端口 + 验证码**
- 密码存本地 JSON（当前未加密）；日志禁止打印密码明文

平台注意：

- **macOS**：屏幕录制 + 辅助功能权限
- **Linux Wayland**：`mss`/`pynput` 可能受限，优先 X11 或文档标明限制
- **Windows**：部分全屏游戏/管理员窗口注入可能失败，属 OS 安全策略

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
    app_gui.py              # 向日葵风格管理界面
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
| HELLO | C→H | JSON：`{role, version, password?}` |
| HELLO_ACK | H→C | JSON：`{ok, reason?, screen_w, screen_h}` |
| FRAME | H→C | JSON meta（utf-8）+ `\n\n` + JPEG bytes |
| MOUSE | C→H | JSON：归一化坐标 + 按键/滚轮 |
| KEY | C→H | JSON：key / action / modifiers |
| QUALITY | C→H | JSON：`{jpeg_quality, scale, max_fps}` |
| HEARTBEAT | 双向 | JSON：`{t}` |
| BYE | 双向 | JSON：`{reason}` |

坐标使用 **相对屏幕归一化** `[0.0, 1.0]`，避免双方分辨率不一致。

### 4.3 扩展规则

- 新增消息类型只追加枚举值，不复用旧值
- JSON 字段采用加字段兼容，禁止随意改名
- 二进制 FRAME 分隔符固定为 `\n\n`，meta 必须是单行 JSON 或紧凑 JSON（不含该分隔符）

## 5. 编程规范

### 5.1 语言与风格

- Python 3.10+，使用 `from __future__ import annotations`
- 公共 API 加类型标注；优先 `dataclass(slots=True)` 表达配置/消息
- 格式：4 空格缩进；字符串默认双引号
- 禁止无意义注释；注释只解释非显而易见的约束（权限、丢帧策略、协议边界）

### 5.2 并发

- I/O 与 CPU（编码）分离线程；共享状态用 `queue.Queue(maxsize=...)` 或锁
- 跨线程停止统一用 `threading.Event`
- 不在持锁时做网络阻塞调用
- 发送路径：**可丢弃旧 FRAME**；控制消息（MOUSE/KEY/HEARTBEAT）尽量不丢

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

## 6. 性能参数默认值

定义于 `config.py`，调参优先改配置而非散落魔法数：

- `max_fps = 30`
- `jpeg_quality = 60`（拥塞时可降到 30）
- `scale = 0.75`（相对原始分辨率）
- `heartbeat_interval_s = 2.0`
- `heartbeat_timeout_s = 8.0`
- `send_queue_size = 2`（FRAME 队列极短，促发丢帧）

## 7. Agent 协作约定

修改本项目时：

1. 先读本文件与 `protocol.py`，保持协议兼容或显式升 `PROTOCOL_VERSION`
2. 改动流畅性相关逻辑时，说明对“丢帧 / 延迟 / CPU”的影响
3. 不主动扩展文件传输、中继服务器等大功能，除非用户明确要求
4. 用户可见说明更新 `README.md`；设计规范更新本文件
5. GUI 变更保持 `tkinter` 单依赖策略；不要把 pygame 事件塞进管理窗口主循环
