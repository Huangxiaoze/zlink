# Remote Desktop (Ubuntu 18.04 Compatible Branch)

跨平台远程桌面控制，本分支面向 **Ubuntu 18.04**（glibc 2.27）：默认使用 **PySide2 / Qt5**。

设计说明见 [AGENTS.md](./AGENTS.md)。

## 系统要求（Ubuntu 18.04）

| 项 | 要求 |
|----|------|
| OS | Ubuntu 18.04 LTS |
| Python | **3.8+**（推荐 deadsnakes 的 3.8） |
| GUI | PySide2 5.15.x（Qt5） |
| 字体 | `fonts-noto-cjk` 或 `fonts-wqy-microhei` |

> 现代系统（Python ≥ 3.11）会自动走 PySide6 回退，代码同一套（`qt_bind.py`）。

## Ubuntu 18.04 安装

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.8 python3.8-venv python3.8-dev \
  libxcb-xinerama0 libxkbcommon-x11-0 libgl1-mesa-glx \
  fonts-noto-cjk

cd remote
python3.8 -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements-ubuntu1804.txt

python main.py
```

若中文显示异常：

```bash
sudo apt install -y fonts-noto-cjk
# 或
sudo apt install -y fonts-wqy-microhei
```

## 功能

- Qt 设备管理界面（中英文）
- 本机远控开关 / 设备列表 / 在线探测
- 远程画面防闪烁合帧渲染
- 键鼠控制
- **剪贴板同步**：文字双向；文件（≤64MB）复制后自动传到对端临时目录并进入剪贴板

> 两端需同为协议 v2（本版本）。被控端请用 GUI「开启远控」，CLI host 暂不启用剪贴板。

## 使用

```bash
python main.py          # GUI
python main.py host ... # CLI 被控
python main.py client --host <IP> --password <code>
```

## 与主分支差异

| | 本分支 `compat/remote-ubuntu-18.04` | 现代分支（PySide6） |
|--|--|--|
| Qt | PySide2 优先 | PySide6 |
| Python | ≥3.8 | ≥3.10 |
| glibc | 2.27 OK | 通常要 ≥2.28 |

## 限制

- 仅直连 TCP，无公网中继
- 传输未加密
- Ubuntu 18.04 已 EOL，仅作兼容维护
