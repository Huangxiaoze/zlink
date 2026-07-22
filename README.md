# Remote Desktop (Python + Qt)

跨平台远程桌面控制（Linux / Windows / macOS），**PySide6 图形界面**，支持中英文。

设计说明与编程规范见 [AGENTS.md](./AGENTS.md)。

## 功能

- Qt 设备管理：添加 / 编辑 / 删除 / 搜索 / 在线探测
- 本机远控开关：识别码、验证码、局域网 IP、端口
- 远程控制窗口（防闪烁合帧渲染）
- 中英文切换（设置里选择，自动保存）
- 键鼠远程控制 + JPEG 自适应画质

## 安装

```bash
cd remote
python -m venv .venv

# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### Ubuntu 中文字体（重要）

若中文显示为方框或乱码：

```bash
sudo apt update
sudo apt install -y fonts-noto-cjk
# 或：sudo apt install -y fonts-wqy-microhei
```

然后重新打开应用。程序会按 Noto / 文泉驿 / 雅黑等顺序自动选择字体。

## 使用

```bash
python main.py
# 或
python main.py gui
```

1. **被控电脑**：开启「本机远控」，记下验证码与 IP  
2. **主控电脑**：添加设备（IP/端口/验证码）→「远程控制」  
3. **语言**：右上角「设置」→ Language / 语言 → 中文或 English  

设备数据：

| 系统 | 路径 |
|------|------|
| Windows | `%APPDATA%\remote_desktop\devices.json` |
| macOS | `~/Library/Application Support/remote_desktop/devices.json` |
| Linux | `~/.config/remote_desktop/devices.json` |

## 命令行

```bash
python main.py host --bind 0.0.0.0 --port 5959 --password yourpass
python main.py client --host <HOST_IP> --port 5959 --password yourpass
```

## 平台权限

| 平台 | 需要 |
|------|------|
| macOS | 屏幕录制、辅助功能 |
| Windows | 一般可直接运行 |
| Linux | 推荐 X11；需可用的 Qt/xcb 平台插件 |

## 限制

- 仅直连 TCP，无公网中继
- 传输未加密
- 本地 `devices.json` 中密码为明文存储
