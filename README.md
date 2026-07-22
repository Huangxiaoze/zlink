# Remote Desktop (Python)

跨平台远程桌面控制（Linux / Windows / macOS），带**向日葵风格设备管理界面**。

设计说明与编程规范见 [AGENTS.md](./AGENTS.md)。

## 功能

- 图形界面管理设备：添加 / 编辑 / 删除 / 搜索
- 本机远控开关：展示识别码、验证码、局域网 IP、端口
- 设备在线探测（TCP 端口）
- 一键远程控制 / 快速连接
- 屏幕实时传输 + 键鼠控制（流畅优先：可丢旧帧、画质自适应）

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

## 使用（推荐 GUI）

```bash
python main.py
# 或
python main.py gui
```

典型流程：

1. **被控电脑**：打开 GUI → 左侧查看验证码与 IP → 点击「开启远控」
2. **主控电脑**：打开 GUI →「添加设备」填入对方 IP/端口/验证码 → 选中后点「远程控制」（或双击）

设备数据保存在用户目录：

| 系统 | 路径 |
|------|------|
| Windows | `%APPDATA%\remote_desktop\devices.json` |
| macOS | `~/Library/Application Support/remote_desktop/devices.json` |
| Linux | `~/.config/remote_desktop/devices.json` |

> 识别码是本地展示标识，**当前版本没有公网中继**，跨设备请用局域网 IP（或已做端口映射的公网 IP）连接。

## 命令行（可选）

```bash
# 被控端
python main.py host --bind 0.0.0.0 --port 5959 --password yourpass

# 主控端
python main.py client --host <HOST_IP> --port 5959 --password yourpass
```

## 平台权限

| 平台 | 需要 |
|------|------|
| macOS | 系统设置 → 隐私与安全性 → **屏幕录制**、**辅助功能** |
| Windows | 一般可直接运行；控制提升权限窗口可能失败 |
| Linux | 推荐 X11；Wayland 下截屏/注入可能受限；需可用的 Tk |

防火墙需放行 Host 端口（默认 `5959/tcp`）。

## 限制（当前版本）

- 仅直连 TCP，无公网中继 / NAT 穿透
- 传输未加密（勿直接暴露公网）
- 设备密码以明文保存在本地 `devices.json`（仅本机可读权限依赖 OS）
