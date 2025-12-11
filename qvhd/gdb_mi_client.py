import subprocess
import signal
import time
import re
import ast

REG_ORDER = [
    "rax", "rbx", "rcx", "rdx",
    "rsi", "rdi", "rbp", "rsp",
    "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15",
    "rip", "eflags",
    "cs", "ss", "ds", "es", "fs", "gs",
]

class GdbMIClient:
    # GDB/MI 클라이언트 초기화
    def __init__(self, target="localhost:1234", gdb_path="gdb", timeout=5.0):
        self.target = target
        self.gdb_path = gdb_path
        self.timeout = timeout

        self.proc = None
        self.name2num = {}
        self.num2name = {}

    # GDB/MI 클라이언트 연결
    def connect(self):
        if self.proc is not None and self.proc.poll() is None:
            return

        self.proc = subprocess.Popen(
            [self.gdb_path, "--nx", "--quiet", "--interpreter=mi2"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        # 기본 설정
        self.mi_cmd("-gdb-set pagination off")
        self.mi_cmd("-gdb-set confirm off")
        self.mi_cmd(f'-interpreter-exec console "target remote {self.target}"', timeout=10.0)

        self.init_register_map()

    def close(self):
        if self.proc is not None and self.proc.poll() is None:
            try:
                self.proc.stdin.write("quit\n")
                self.proc.stdin.flush()
            except Exception:
                pass

            try:
                self.proc.wait(timeout=0.2)
            except Exception:
                pass

            if self.proc.poll() is None:
                self.proc.terminate()

    def stepi(self):
        self.mi_cmd("-exec-step-instruction")

    def cont(self):
        self.mi_cmd("-exec-continue")

    def interrupt(self):
        if self.proc is None or self.proc.poll() is not None:
            raise RuntimeError("gdb is not running")
        self.proc.send_signal(signal.SIGINT)

    # GDB/MI 명령어 송수신
    def mi_cmd(self, cmd, timeout=None):
        if timeout is None:
            timeout = self.timeout
        if self.proc is None or self.proc.poll() is not None:
            raise RuntimeError("gdb is not running")

        full = cmd.strip()
        self.proc.stdin.write(full + "\n")
        self.proc.stdin.flush()

        deadline = time.time() + timeout
        lines = []
        result = None

        while True:
            if time.time() > deadline:
                raise RuntimeError(f"MI timeout for '{cmd}'")

            line = self.proc.stdout.readline()
            if not line:
                raise RuntimeError("gdb exited")

            line = line.rstrip()
            if not line:
                continue

            lines.append(line)

            if line.startswith("^done") or line.startswith("^running") or line.startswith("^error"):
                result = line
                break

        if result.startswith("^error"):
            raise RuntimeError(f"MI error for '{cmd}': {result}")
        return result, lines

    # QEMU Monitor 명령어 송수신
    def monitor_cmd(self, cmd, timeout=None):
        if timeout is None:
            timeout = self.timeout

        mi = f'-interpreter-exec console "monitor {cmd}"'
        result, lines = self.mi_cmd(mi, timeout=timeout)
        console_text = self.extract_console_text(lines)

        return console_text

    # 명령어 응답 텍스트 추출
    def extract_console_text(self, lines):
        out_parts = []
        for line in lines:
            if len(line) >= 3 and line[0] in ("~", "@") and line[1] == '"':
                s = line[2:]
                if s.endswith('"'):
                    s = s[:-1]
                try:
                    s = bytes(s, "utf-8").decode("unicode_escape")
                except Exception:
                    pass
                out_parts.append(s)
        return "".join(out_parts)

    # Registers 매핑
    def init_register_map(self):
        result, lines = self.mi_cmd("-data-list-register-names")
        text = "\n".join(lines)

        m = re.search(r"register-names=\[(.*)\]", text, re.S)
        if not m:
            raise RuntimeError("failed to parse register names from MI")
        inner = m.group(1).strip()

        names = ast.literal_eval("[" + inner + "]")
        self.num2name = {i: n for i, n in enumerate(names) if n}
        self.name2num = {n: i for i, n in self.num2name.items()}

    # Registers 읽기
    def read_registers(self):
        result, lines = self.mi_cmd("-data-list-register-values x")
        text = "\n".join(lines)

        entries = re.findall(r'number="(\d+)",value="([^"]*)"', text)
        by_num = {int(num): val for num, val in entries}

        regs = {}
        for name in REG_ORDER:
            num = self.name2num.get(name)
            if num is None:
                regs[name] = "N/A"
            else:
                regs[name] = by_num.get(num, "N/A")
        return regs

    # CR3 읽기
    def read_cr3(self) -> int:
        # GDB 레지스터에서 직접 읽기
        if "cr3" in self.name2num:
            num = self.name2num["cr3"]
            result, lines = self.mi_cmd(f"-data-list-register-values x {num}")
            text = "\n".join(lines)

            m = re.search(r'value="([^"]+)"', text)
            if m:
                val_str = m.group(1)
                try:
                    return int(val_str, 0)
                except ValueError:
                    pass

        # QEMU Monitor에서 info cr3 사용
        result, lines = self.mi_cmd(
            '-interpreter-exec console "monitor info cr3"',
            timeout=10.0,
        )

        console_chunks = []
        for ln in lines:
            if ln.startswith('~"') and ln.endswith('"'):
                s = ln[2:-1]
                console_chunks.append(s)

        out = "\n".join(console_chunks).strip()

        if not out:
            raise RuntimeError(
                f"failed to parse CR3 from monitor output: {lines!r}"
            )

        patterns = [
            r"CR3\s*=\s*(0x[0-9a-fA-F]+)",
            r"CR3\s*=\s*([0-9a-fA-F]+)",
            r"PDBR\s*=\s*(0x[0-9a-fA-F]+)",
            r"PDBR\s*=\s*([0-9a-fA-F]+)",
        ]

        for pat in patterns:
            m = re.search(pat, out)
            if m:
                return int(m.group(1), 0)

        raise RuntimeError(f"failed to parse CR3 from: {out!r}")

    # 메모리 읽기
    def read_phys_qword(self, phys_addr: int) -> int:
        cmd = f'-interpreter-exec console "monitor xp /1gx {phys_addr:#x}"'
        result, lines = self.mi_cmd(cmd, timeout=5.0)

        raw_strs = []
        for line in lines:
            if len(line) >= 3 and line[0] in ("~", "@") and line[1] == '"':
                raw_strs.append(line[2:])

        if not raw_strs:
            raise RuntimeError(
                f"xp had no console/target output; MI lines = {lines!r}"
            )

        decoded = []
        for s in raw_strs:
            try:
                decoded.append(ast.literal_eval(s))
            except Exception:
                decoded.append(
                    s.strip('"').encode("utf-8").decode("unicode_escape")
                )

        text = "".join(decoded)
        first_line = text.strip().splitlines()[0]

        m = re.search(r":\s*(0x[0-9a-fA-F]+)", first_line)
        if not m:
            raise RuntimeError(f"failed to parse xp line: {first_line!r}")

        return int(m.group(1), 16)

    # x86_64 페이지 오프셋 추출
    def split_va(self, va: int):
        pml4_i = (va >> 39) & 0x1FF
        pdpt_i = (va >> 30) & 0x1FF
        pd_i   = (va >> 21) & 0x1FF
        pt_i   = (va >> 12) & 0x1FF
        offset = va & 0xFFF
        return pml4_i, pdpt_i, pd_i, pt_i, offset

    # x86_64 페이지 엔트리 플래그 추출
    def parse_pte_flags(self, entry: int) -> dict:
        flags = {
            "present":      bool(entry & (1 << 0)),
            "writable":     bool(entry & (1 << 1)),
            "user":         bool(entry & (1 << 2)),
            "write_through":bool(entry & (1 << 3)),
            "cache_disable":bool(entry & (1 << 4)),
            "accessed":     bool(entry & (1 << 5)),
            "dirty":        bool(entry & (1 << 6)),
            "page_size":    bool(entry & (1 << 7)),
            "global":       bool(entry & (1 << 8)),
            "nx":           bool(entry & (1 << 63)),
        }
        return flags

    def inspect_va(self, va: int) -> dict:
        # CR3
        cr3 = self.read_cr3()
        pml4_i, pdpt_i, pd_i, pt_i, offset = self.split_va(va)

        result = {
            "va": va,
            "cr3": cr3,
            "pml4_index": pml4_i,
            "pdpt_index": pdpt_i,
            "pd_index": pd_i,
            "pt_index": pt_i,
            "offset": offset,
        }

        # PML4
        pml4_phys = cr3 & ~0xFFF
        pml4_entry_addr = pml4_phys + pml4_i * 8
        pml4_entry = self.read_phys_qword(pml4_entry_addr)
        result["pml4_entry"] = pml4_entry

        if not (pml4_entry & 1):
            result["level"] = "pml4"
            result["present"] = False
            result["page_size"] = None
            return result

        # PDPT
        pdpt_phys = pml4_entry & ~0xFFF
        pdpt_entry_addr = pdpt_phys + pdpt_i * 8
        pdpt_entry = self.read_phys_qword(pdpt_entry_addr)
        result["pdpt_entry"] = pdpt_entry

        if not (pdpt_entry & 1):
            result["level"] = "pdpt"
            result["present"] = False
            result["page_size"] = None
            return result

        if pdpt_entry & (1 << 7):
            page_base = pdpt_entry & ~((1 << 30) - 1)
            phys_addr = page_base + (va & ((1 << 30) - 1))
            result["level"] = "1G"
            result["present"] = True
            result["page_size"] = "1G"
            result["page_phys"] = page_base
            result["phys_addr"] = phys_addr
            result["flags"] = self.parse_pte_flags(pdpt_entry)
            return result

        # PD
        pd_phys = pdpt_entry & ~0xFFF
        pd_entry_addr = pd_phys + pd_i * 8
        pd_entry = self.read_phys_qword(pd_entry_addr)
        result["pd_entry"] = pd_entry

        if not (pd_entry & 1):
            result["level"] = "pd"
            result["present"] = False
            result["page_size"] = None
            return result

        if pd_entry & (1 << 7):
            page_base = pd_entry & ~((1 << 21) - 1)
            phys_addr = page_base + (va & ((1 << 21) - 1))
            result["level"] = "2M"
            result["present"] = True
            result["page_size"] = "2M"
            result["page_phys"] = page_base
            result["phys_addr"] = phys_addr
            result["flags"] = self.parse_pte_flags(pd_entry)
            return result

        # PT
        pt_phys = pd_entry & ~0xFFF
        pt_entry_addr = pt_phys + pt_i * 8
        pt_entry = self.read_phys_qword(pt_entry_addr)
        result["pt_entry"] = pt_entry

        if not (pt_entry & 1):
            result["level"] = "pt"
            result["present"] = False
            result["page_size"] = None
            return result

        # 최종 4KB 페이지
        page_base = pt_entry & ~0xFFF
        phys_addr = page_base + offset

        result["level"] = "4K"
        result["present"] = True
        result["page_size"] = "4K"
        result["page_phys"] = page_base
        result["phys_addr"] = phys_addr
        result["flags"] = self.parse_pte_flags(pt_entry)

        return result

    # 메모리 덤프
    def read_virt_bytes(self, va: int, size: int = 64) -> bytes:
        if size <= 0:
            return b""

        cmd = f'-data-read-memory-bytes 0x{va:x} {size}'
        result, lines = self.mi_cmd(cmd, timeout=5.0)
        text = "\n".join(lines)

        m = re.search(r'contents="([0-9a-fA-F]*)"', text)
        if not m:
            raise RuntimeError(f"failed to parse memory bytes from MI: {text!r}")

        hexstr = m.group(1)
        hexstr = hexstr[: 2 * size]

        byte_list: list[int] = []
        for i in range(0, len(hexstr), 2):
            try:
                byte_list.append(int(hexstr[i:i+2], 16))
            except ValueError:
                break

        return bytes(byte_list)