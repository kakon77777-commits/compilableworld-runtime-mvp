# CompilableWorld Runtime MVP v0.1.0

這是一套非網頁、零第三方執行依賴的 Python 參考實作。它將 JSON／CSV Authoring Layer 編譯為 Runtime Package，再由 MSSP 模組化世界核心透過終端機執行。

## 快速開始

不安裝也可直接執行：

```bash
cd compilableworld-runtime-mvp
PYTHONPATH=src python3 -m compilableworld validate examples/gray_crown
PYTHONPATH=src python3 -m compilableworld compile examples/gray_crown --out build/gray_crown
PYTHONPATH=src python3 -m compilableworld play build/gray_crown/world.package.json
```

或以 editable mode 安裝：

```bash
python3 -m pip install -e .
cw-runtime compile examples/gray_crown --out build/gray_crown
cw-runtime play build/gray_crown/world.package.json
```

## 測試

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## 範例流程

在 CLI 中依序輸入：

```text
take item.old_key
n
unlock door.old_vault
open door.old_vault
d
look
diag
save demo-save.json
```

## 架構邊界

```text
JSON / CSV / Manifest
        ↓ compiler + validators
Runtime Package (World IR subset)
        ↓ loader
World Kernel
        ↓ Action IR
MSSP TMS Module
        ↓ StateDelta + EventIR
Atomic Commit / Event Log / Projection
        ↓
Terminal Gateway
```

Python 版本用於凍結語言無關契約與快速驗證。後續 Rust 重寫應保持 Runtime Package、Action IR、State Delta、Event IR 與 Module Contract 的語義相容，而非逐行翻譯 Python 類別。

## 已知邊界

- 目前是單程序、單世界實例；沒有帳號、多人網路與分散式鎖。
- Scheduler 支援延遲 Action，但 CLI 尚未暴露複合行為編輯器。
- Quest 模組目前只做狀態投影，事件驅動的任務轉移留待 v0.2。
- 世界、區域與場景的初始階層狀態已編入 State Store；跨層事件轉移規則留待 v0.2。
- Intent Parser 是確定性參考實作；AI Adapter 必須輸出同一 `ActionIR` 並接受 Kernel 驗證。
- Module Contract 的寫入範圍已由 Kernel 強制檢查；讀取範圍與 Action authority 的強制隔離留待 v0.2。
- JSON Schema 與 CSV Schema 目前由程式內驗證器實作；v0.2 應外部化為正式 Schema 檔。
- Replay 重放已提交 Delta；跨版本重放仍需 migration registry。
