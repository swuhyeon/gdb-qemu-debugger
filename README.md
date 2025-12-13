# QEMU 기반 x86_64 가상 하드웨어 디버거

> QEMU based x86_64 Virtual Hardware Debugger (QVHD)

QEMU의 gdbstub을 활용해 **레지스터·페이지 테이블·가상 메모리 상태**를 한 화면에서 추적하는 TUI 기반 x86_64 가상 하드웨어 디버거입니다.

---



## 1. Features
### 1) Register
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

### 2) Page Info
- 현재 선택된 VA에 대해 **페이지 테이블 워크**를 수행하며, 출력 항목은 다음과 같습니다.
  - `va`
  - `perm` (`R-X (kernel)`)
  - `present`, `page_size`, `level`
  - `cr3`
  - `pml4_index`, `pdpt_index`, `pd_index`, `pt_index`, `offset`
  - `pml4_entry`, `pdpt_entry`, `pd_entry`
  - `flags`

- Page Info 모드는 두 가지가 있습니다:
  - `rip` 모드: `rip` 레지스터 값을 VA로 사용
  - `manual` 모드: 사용자가 직접 지정한 VA를 사용

### 3) Mem Dump
- VA 기준으로 메모리를 읽어 **hexdump 형식**으로 표시합니다.
- 한 줄에 16바이트씩 표시:
  - 왼쪽: 주소
  - 가운데: 16바이트 hex
  - 오른쪽: ASCII 표현



## 2. Layout
### 1) Directory Layout
- Directory Layout은 다음과 같습니다.
- 이 저장소에는 **`qvhd/`와 `scripts/` 디렉터리만** 포함되어 있으며, **`qemu/`, `iso/`, `vm/` 디렉터리는** 아래 **Requirements** 섹션에 따라 사용자가 별도로 준비·설정해야 합니다.

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



## 3. Requirements
### 1) qemu/
- QEMU 소스

```bash
git clone https://gitlab.com/qemu-project/qemu.git
cd qemu
```

- QEMU 빌드 의존성 설치 (Ubuntu 기준)

```bash
sudo apt update

sudo apt install -y \
  build-essential \
  ninja-build \
  pkg-config \
  libglib2.0-dev \
  libpixman-1-dev \
  zlib1g-dev \
  libfdt-dev \
  python3-venv python3-pip \
  libgtk-3-dev libsdl2-dev \
  libslirp-dev
```

- QEMU 빌드

```bash
mkdir build
cd build

../configure \
  --target-list=x86_64-softmmu \
  --enable-debug \
  --enable-gtk \
  --enable-sdl \
  --enable-slirp

make -j"$(nproc)"
```

- QEMU 빌드 확인

```bash
./qemu-system-x86_64 --version
```

### 2) iso/
- 별도로 ISO 파일을 다운로드한 뒤 `~/iso` 아래 위치
- ex) `ubuntu-24.04.3-live-server-amd64.iso`

```bash
mkdir -p ~/iso
```

### 3) vm/
- 게스트 디스크 이미지 생성

```bash
mkdir -p ~/vm
cd ~/vm

qemu-img create -f qcow2 linux_guest.qcow2 20G
```

### 4) ISO 부팅
-  **`qemu/`, `iso/`, `vm/`** 설정을 모두 마친 후 ISO 부팅 진행
```bash
cd ~/qemu/build

./qemu-system-x86_64 \
  -accel tcg \
  -cpu qemu64 \
  -m 2048 \
  -smp 1 \
  -drive file=$HOME/vm/linux_guest.qcow2,if=virtio,format=qcow2 \
  -netdev user,id=n1,hostfwd=tcp::2222-:22 \
  -device e1000,netdev=n1 \
  -display gtk \
  -cdrom $HOME/iso/ubuntu-24.04.3-live-server-amd64.iso \
  -boot d
```



## 4. How to Use
### 1) Run QEMU & QVHD

> QEMU가 gdbstub(`-s -S`)으로 실행된 상태에서 QVHD TUI가 `localhost:1234`로 연결되는 구조입니다.  
> 두 개의 터미널을 사용합니다.

**Terminal 1 – QEMU + gdbstub**

```bash
cd ~/scripts
./run_qemu.sh
```

**Terminal 2 – QVHD TUI**

```bash
cd ~/scripts
./run_ui.sh
```

### 2) Built-in Commands
| Command | 설명                                                                                               |
| ------- | -------------------------------------------------------------------------------------------------- |
| `n`     | `stepi` 한 instruction씩 실행하며, 실행 후 **Register + Page Info 갱신** |
| `c`     | `continue` 게스트를 계속 실행하며, **is_running = True** 상태로 전환 |
| `p`     | `pause` 실행 중인 게스트를 멈추고 **Register + Page Info 갱신** |
| `r`     | `refresh` 게스트가 멈춘 상태에서 **Register + Page Info를 다시 읽어 옴** |
| `q`     | TUI 종료 & GDB 세션 정리 후 프로그램 종료 |

### 3) Page Info Commands
| Command | 설명                                                                                               |
| ------- | -------------------------------------------------------------------------------------------------- |
| `va rip`    | Page Info 모드를 **rip 모드**로 전환하고, 현재 rip 기준으로 페이지 정보 출력 |
| `va <addr>` | Page Info 모드를 **manual 모드**로 전환하고, 지정한 VA 기준으로 페이지 정보 출력 |

### 4) Memory Dump Commands
| Command | 설명                                                                                               |
| ------- | -------------------------------------------------------------------------------------------------- |
| `md <va>`        | `<va>` 기준으로 **기본 64바이트** 메모리 덤프 |
| `md <va> <size>` | `<va>` 기준으로 **지정한 size 바이트만큼** 메모리 덤프 |



## 5. UI
- 기본 UI (Registers + Page Info 레이아웃)
<img width="700" height="300" alt="qvhd" src="https://github.com/user-attachments/assets/857bbe27-0c64-40bf-89b2-977d4a2873e5" />

- `md <va>` 실행 후의 UI (하단 Mem Dump 레이아웃 활성화)
<img width="700" height="300" alt="qvhd2" src="https://github.com/user-attachments/assets/20a56241-71b5-4a61-93b2-b7c1ea49f094" />
