# `zlink` package layout

| Package | Role |
|---------|------|
| [`core/`](core/) | Wire protocol (`protocol`), TCP session (`net`), app/stream config (`config`), screen JPEG (`codec`) |
| [`session/`](session/) | Controlled endpoint (`host`, `capture`, `input_io`, `pointer_sync`) and controller viewer (`client`, `win_input_capture`) |
| [`ui/`](ui/) | Device manager GUI (`app_gui`), themes/i18n, Qt compatibility (`qt_bind`, `qt_fonts`), chrome widgets |
| [`features/`](features/) | Device list persistence, clipboard sync, file transfer/browser, remote terminal |

Public entry points (CLI / packaging):

- `zlink.ui.app_gui.run_app` — default GUI
- `zlink.session.host.RemoteHost` — headless host
- `zlink.session.client.RemoteClient` — headless client loop

Version and protocol constants live in [`__init__.py`](__init__.py).
