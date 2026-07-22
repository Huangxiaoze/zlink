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

- Qt 设备管理界面（中英文、主题切换）
- 本机远控开关 / 设备卡片列表 / 在线探测
- 远程画面防闪烁合帧渲染
- 键鼠控制
- **剪贴板同步**：文字/文件（≤64MB）
- **远程文件传输**：独立通道互传文件（单文件 ≤64MB），保存到 `Downloads/LeafLink`

### 文件传输怎么用

| 方向 | 操作 |
|------|------|
| 控制端 → 被控端 | 远程窗口顶部滑出条点「发送文件」 |
| 被控端 → 控制端 | 被控端主界面侧栏「发送给控制端」（仅在有人连入时显示） |

接收文件默认落在用户下载目录下的 `LeafLink` 文件夹；进度显示在窗口标题 / 状态栏。

### 剪贴板怎么用

| 操作 | 说明 |
|------|------|
| 自动同步 | 任一端复制后，约 0.5s 内同步到另一端系统剪贴板 |
| 远程窗口内 `Ctrl+V` | 先把**本机**剪贴板推到被控端，再在被控端粘贴 |
| `Ctrl+Alt+C`（远程窗口内） | **强制推送**：把本机剪贴板推到对方 |
| `Ctrl+Alt+V`（远程窗口内） | **强制拉取**：向对方要剪贴板并写入本机 |

用法：在**本机**其它窗口 `Ctrl+C` 复制 → 点进远程画面 → `Ctrl+V` 粘贴到对方。  
被控端须用 GUI「开启远控」；两端都要协议 v2。

## 使用

```bash
python main.py          # GUI
python main.py host ... # CLI 被控
python main.py client --host <IP> --password <code>
```

主题：设置 → 主题（浅色 / 深色 / 森绿），立即生效并写入本地配置。

## 打包可执行文件 / 安装包

在**目标平台本机**打包（PyInstaller 交叉编译 Qt 应用不可靠）：

| 平台 | 脚本 |
|------|------|
| Windows | `powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1` |
| Linux（二进制） | `bash scripts/build_linux.sh` |
| Ubuntu/Debian（`.deb`） | `bash scripts/build_deb.sh` |
| macOS | `bash scripts/build_macos.sh` |

### Windows 安装包（推荐）

默认会生成：

1. 应用目录：`dist/LeafLink/LeafLink.exe`
2. 安装包：`dist/LeafLink-Setup-<version>.exe`（Inno Setup）

```powershell
# 若尚未安装 Inno Setup 6，可让脚本自动安装：
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -InstallInnoSetup

# 或先手动安装：
winget install --id JRSoftware.InnoSetup -e
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1
```

只要应用目录、不要安装包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -NoInstaller
```

单文件便携版（启动较慢，不含安装向导）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_windows.ps1 -NoInstaller -OneFile
```

### Ubuntu / Debian 安装包（`.deb`）

在 Ubuntu 本机执行（推荐与目标系统同版本，例如 18.04）：

```bash
sudo apt update
sudo apt install -y dpkg-dev python3-venv
# 若按上文装过运行依赖，可跳过；打包机仍需 Qt/X11 相关库

bash scripts/build_deb.sh
```

产物：

1. 应用目录：`dist/LeafLink/LeafLink`
2. 安装包：`dist/leaflink_<version>_<arch>.deb`

安装 / 卸载：

```bash
sudo apt install ./dist/leaflink_*.deb
# 或
sudo dpkg -i ./dist/leaflink_*.deb && sudo apt-get install -f -y

sudo apt remove leaflink
```

安装后可从应用菜单启动 **LeafLink**，或命令行运行 `leaflink`。  
若已有 `dist/LeafLink`、只想重打 deb：

```bash
DEB_ONLY=1 bash scripts/build_deb.sh
# 等价：python scripts/build.py --deb-only
```

### 通用入口

```bash
pip install -r requirements.txt -r requirements-build.txt
python scripts/build.py --clean
# Windows 安装包：
python scripts/build.py --clean --installer
# Ubuntu/Debian 安装包：
python scripts/build.py --clean --deb
```

调试 CLI 可加 `--console` 保留终端窗口。

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
