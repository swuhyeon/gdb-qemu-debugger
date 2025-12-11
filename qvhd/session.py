from gdb_mi_client import GdbMIClient, REG_ORDER

class DebugSession:
    # GDB/MI 클라이언트와 디버깅 세션 초기화
    def __init__(self, target: str = "localhost:1234", gdb_path: str = "gdb") -> None:
        self.client = GdbMIClient(target=target, gdb_path=gdb_path)

        # Registers
        self.regs = {name: "N/A" for name in REG_ORDER}
        self.prev_regs = self.regs.copy()

        # Page Info
        self.inspect_mode = "rip"
        self.inspect_va = None
        self.page_info = None
        self.prev_page_info = None

        # Mem Dump
        self.mem_dump_lines = []

        self.status = "init: not connected yet"
        self.is_running = False

    # GDB/MI 명령 실행
    def run_action(self, label: str, action, *, refresh_regs: bool = True) -> None:
        try:
            action()

            # Registers + Page Info 갱신
            if refresh_regs:
                self.prev_regs = self.regs.copy()
                self.regs = self.client.read_registers()
                self.update_page_info()

            self.status = f"{label} OK"

        except KeyboardInterrupt:
            self.status = f"{label} CANCEL: KeyboardInterrupt"

        except Exception as e:
            self.status = f"{label} ERROR: {e!s}"

    # GDB/MI 클라이언트 연결
    def connect(self) -> None:
        try:
            self.client.connect()
            self.regs = self.client.read_registers()
            self.prev_regs = self.regs.copy()
            self.status = "connected to localhost:1234 (use n/c/p/r/q)"
            self.update_page_info()

        except Exception as e:
            self.status = f"init ERROR: {e!s}"

    def close(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass

    # n: stepi
    def cmd_step(self) -> None:
        if self.is_running:
            self.status = "stepi 불가: 현재 running 상태입니다. 먼저 p로 멈춰주세요."
            return

        self.run_action(
            label="stepi",
            action=lambda: self.client.stepi(),
            refresh_regs=True,
        )

    # c: continue
    def cmd_continue(self) -> None:
        if self.is_running:
            self.status = "이미 running 상태입니다. (계속 실행 중)"
            return

        self.run_action(
            label="continue",
            action=lambda: self.client.cont(),
            refresh_regs=False,
        )
        self.is_running = True

    # p: pause
    def cmd_pause(self) -> None:
        self.run_action(
            label="pause (interrupt)",
            action=lambda: self.client.interrupt(),
            refresh_regs=True,
        )
        self.is_running = False

    # r: refresh
    def cmd_refresh(self) -> None:
        if self.is_running:
            self.status = "refresh 불가: 현재 running 상태입니다. 먼저 p로 멈춰주세요."
            return

        self.run_action(
            label="refresh",
            action=lambda: None,
            refresh_regs=True,
        )

    # Page Info Mode
    def current_inspect_va(self):
        if self.inspect_mode == "rip":
            rip_val = self.regs.get("rip")
            if not rip_val or rip_val == "N/A":
                return None
            try:
                return int(str(rip_val), 16)
            except ValueError:
                return None
        
        elif self.inspect_mode == "manual" and self.inspect_va is not None:
            return self.inspect_va
        return None
    
    # Page Info Mode - rip
    def set_inspect_rip(self) -> None:
        if self.is_running:
            self.status = "inspect 모드 변경 불가: 현재 running 상태입니다. 먼저 p로 멈춰주세요."
            return

        self.inspect_mode = "rip"
        self.inspect_va = None
        self.update_page_info()

    # Page Info Mode - manual
    def set_inspect_va(self, va: int) -> None:
        if self.is_running:
            self.status = "inspect 모드 변경 불가: 현재 running 상태입니다. 먼저 p로 멈춰주세요."
            return

        self.inspect_mode = "manual"
        self.inspect_va = va
        self.update_page_info()

    # Page Info Update
    def update_page_info(self) -> None:
        va = self.current_inspect_va()
        if va is None:
            self.prev_page_info = self.page_info
            self.page_info = None
            return

        try:
            self.prev_page_info = self.page_info
            info = self.client.inspect_va(va)

            if isinstance(info, dict):
                flags = info.get("flags")

                # perm
                perm = self.perm_from_flags(flags)
                if perm is not None:
                    info["perm"] = perm

                # va
                info.setdefault("va", va)

                # present
                if isinstance(flags, dict) and "present" in flags:
                    info.setdefault("present", bool(flags["present"]))
                
                # page size
                if "page_size" not in info:
                    level = info.get("level")
                    page_size = None

                    if level in ("pt", "4K"):
                        page_size = "4K"
                    elif level in ("pd", "2M"):
                        page_size = "2M"
                    elif level in ("pdpt", "1G"):
                        page_size = "1G"

                    info["page_size"] = page_size

            self.page_info = info

        except Exception as e:
            self.prev_page_info = self.page_info
            self.page_info = {"error": str(e)}

    # flags를 기반으로 RWX + (user/kernel) 생성
    def perm_from_flags(self, flags):
        if not isinstance(flags, dict):
            return None
        if not flags.get("present", False):
            return None

        # RWX
        r = "R"
        w = "W" if flags.get("writable", False) else "-"
        x = "X" if not flags.get("nx", False) else "-"

        perm = f"{r}{w}{x}"

        # user/kernel
        if flags.get("user", False):
            perm += " (user)"
        else:
            perm += " (kernel)"

        return perm

    # Mem Dump
    def memdump(self, va: int, size: int = 64) -> None:
        if self.is_running:
            self.status = "memdump 불가: 현재 running 상태입니다. 먼저 p로 멈춰주세요."
            return

        try:
            data = self.client.read_virt_bytes(va, size)
            lines = []
            base = va

            for i in range(0, len(data), 16):
                chunk = data[i:i+16]
                addr = base + i

                hexpart = " ".join(f"{b:02x}" for b in chunk)
                asciipart = "".join(
                    chr(b) if 32 <= b < 127 else "."
                    for b in chunk
                )
                
                # 16바이트 기준 한 줄
                lines.append(f"0x{addr:016x}: {hexpart:<47}  {asciipart}")

            self.mem_dump_lines = lines
            self.status = f"memdump 0x{va:x} ({size} bytes) OK, lines={len(lines)}"

        except Exception as e:
            self.mem_dump_lines = [f"memdump ERROR: {e}"]
            self.status = f"memdump ERROR: {e}"