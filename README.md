# QEMU 기반 x86_64 가상 하드웨어 디버거

> QEMU based x86_64 Virtual Hardware Debugger (QVHD)

QEMU의 gdbstub을 활용해 **레지스터·페이지 테이블·가상 메모리 상태**를 한 화면에서 추적하는 디버입니다.

---



## 1. Features
### 1) Register (왼쪽 패널)
- QEMU 게스트의 GPR/segment 레지스터를 표시합니다.
- 이전 스텝과 값이 달라진 레지스터는 **색상 강조(노랑)** 로 표시됩니다.
- 표시 순서는 `REG_ORDER` 에 정의되어 있으며, 출력 항목은 다음과 같습니다.

  ```python
  REG_ORDER = [
      "rax", "rbx", "rcx", "rdx",
      "rsi", "rdi", "rbp", "rsp",
      "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
      "rip", "eflags",
      "cs", "ss", "ds", "es", "fs", "gs",
  ]
  ```

### 2) Page Info (오른쪽 상단 패널)
- 현재 선택된 VA에 대해 **페이지 테이블 워크**를 수행하며, 출력 항목은 다음과 같습니다.
  - `va`, `cr3`
  - `pml4_index`, `pdpt_index`, `pd_index`, `pt_index`, `offset`
  - `pml4_entry`, `pdpt_entry`, `pd_entry`, `pt_entry`
  - `present`, `page_size`, `level`
  - `page_phys`, `phys_addr`
  - `flags` (present, writable, user, nx 등)
  - `perm` (`RWX (user)`)

- Page Info 모드는 두 가지가 있습니다:
  - `rip` 모드: `rip` 레지스터 값을 VA로 사용
  - `manual` 모드: 사용자가 직접 지정한 VA를 사용

### 3) Mem Dump (오른쪽 하단 패널)
- VA 기준으로 메모리를 읽어 **hexdump 형식**으로 표시합니다.
- 한 줄에 16바이트씩 표시:
  - 왼쪽: 주소
  - 가운데: 16바이트 hex
  - 오른쪽: ASCII 표현



## 2. Layout
### 1) Directory Layout
- Directory Layout은 다음과 같습니다.
- 해당 Repository에는 **`qvhd/`와 `scripts/`만** 포함되어 있으며, **`qemu/`, `iso/`, `vm/`은** 아래 설명에 따라 사용자가 별도로 준비·설정해야 합니다.

```text
$HOME/
  qemu/    # QEMU source & build (not in this repo)
  iso/     # OS installation ISOs (not in this repo)
  vm/      # VM disk images (not in this repo)
  qvhd/    # QVHD Python debugger (in this repo)
  scripts/ # Scripts to run QEMU & TUI (in this repo)
```

### 2) Repository Layout (in this repo)
- Repository Layout은 다음과 같습니다.
- 두 개의 터미널을 사용합니다.
  - 터미널 1: `run_qemu.sh` 실행 (QEMU + gdbstub)
  - 터미널 2: `run_ui.sh` 실행 (QVHD TUI)

```text
qvhd/
  gdb_mi_client.py  # GDB/MI + QEMU monitor wrapper
  session.py        # DebugSession
  tui.py            # curses-based TUI frontend

scripts/
  run_qemu.sh       # start QEMU guest with gdb stub (-s -S)
  run_ui.sh         # start QVHD TUI (connects to localhost:1234)
```
