import curses
from gdb_mi_client import REG_ORDER
from session import DebugSession

def draw_ui(stdscr, sess: DebugSession, cmd_buf: str) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()

    # 화면 비율 조정
    top_margin = 1
    bottom_margin = 1
    title_row = top_margin 
    hline_row = title_row + 1 + bottom_margin
    content_top = hline_row + 1

    mid = w * 2 // 5
    left_width = mid - 1
    right_x = mid + 1
    right_width = w - right_x - 1

    # 상단바
    main_title = "[QVHD] QEMU based x86_64 Virtual Hardware Debugger"
    title_x = max(0, (w - len(main_title)) // 2)
    stdscr.addstr(title_row, title_x, main_title[: w - 1])

    # 구분선
    stdscr.hline(hline_row, 0, ord("-"), w)
    stdscr.vline(content_top, mid - 1, ord("|"), h - content_top - 3)

    # 왼쪽 레이아웃 - Registers
    row = content_top
    reg_title = "Registers"
    reg_help = "[n:step  c:cont  p:pause  r:refresh  q:quit]"
    reg_label = f"{reg_title}  {reg_help}"
    reg_x = max(1, (left_width - len(reg_label)) // 2)
    stdscr.addstr(row, reg_x, reg_label[: left_width - 1])
    row += 2

    for name in REG_ORDER:
        if row >= h - 3:
            break

        val = sess.regs.get(name, "N/A")
        prev = sess.prev_regs.get(name, None)

        line = f"{name:>4} : {val}"
        if prev is not None and prev != val and val != "N/A":
            stdscr.attron(curses.color_pair(2))
            stdscr.addstr(row, 2, line[: left_width - 4])
            stdscr.attroff(curses.color_pair(2))
        else:
            stdscr.addstr(row, 2, line[: left_width - 4])

        row += 1

    # 화면 비율 조정
    content_bottom = h - 3
    content_height = content_bottom - content_top
    page_height = (content_height * 3) // 5

    page_top = content_top
    page_bottom = page_top + page_height
    mem_top = page_bottom
    mem_bottom = content_bottom

    # 오른쪽 상단 레이아웃 - Page Info
    row2 = page_top
    page_title = f"Page Info (mode: {sess.inspect_mode})"
    page_help = "[va <addr> OR va rip]"
    page_label = f"{page_title}  {page_help}"
    page_x = right_x + max(0, (right_width - len(page_label)) // 2)
    stdscr.addstr(row2, page_x, page_label[: right_width])
    row2 += 2

    pi = sess.page_info
    prev_pi = sess.prev_page_info if isinstance(sess.prev_page_info, dict) else None

    if pi is None:
        if row2 < page_bottom:
            stdscr.addstr(row2, right_x, "(no page info)")
            row2 += 1
    else:
        if isinstance(pi, dict) and "error" in pi and len(pi) == 1:
            if row2 < page_bottom:
                stdscr.addstr(row2, right_x, f"ERROR: {pi['error']}"[: right_width])
                row2 += 1
        else:
            va = None
            if isinstance(pi, dict):
                va = pi.get("va", None)

            # Page Info - va
            if va is not None and row2 < page_bottom:
                header = f"va: 0x{va:x}  (mode: {sess.inspect_mode})"
                prev_va = None
                if prev_pi is not None:
                    prev_va = prev_pi.get("va", None)

                if prev_va is not None and prev_va != va:
                    stdscr.attron(curses.color_pair(2))
                    stdscr.addstr(row2, right_x, header[: right_width])
                    stdscr.attroff(curses.color_pair(2))
                else:
                    stdscr.addstr(row2, right_x, header[: right_width])
                row2 += 1

            # Page Info - perm
            if isinstance(pi, dict) and "perm" in pi and row2 < page_bottom:
                perm = pi["perm"]
                prev_perm = prev_pi.get("perm") if prev_pi else None
                line = f"perm: {perm}"

                if prev_perm is not None and prev_perm != perm:
                    stdscr.attron(curses.color_pair(2))
                    stdscr.addstr(row2, right_x, line[: right_width])
                    stdscr.attroff(curses.color_pair(2))
                else:
                    stdscr.addstr(row2, right_x, line[: right_width])
                row2 += 1

            # 나머지 key/value 출력
            if isinstance(pi, dict):
                preferred_order = [
                    "present",
                    "page_size",
                    "level",
                    "cr3",
                    "pml4_index",
                    "pdpt_index",
                    "pd_index",
                    "pt_index",
                    "offset",
                    "pml4_entry",
                    "pdpt_entry",
                    "pd_entry",
                    "pt_entry",
                    "flags",
                ]

                printed = {"va", "perm"}

                # 우선순위에 있는 것들 먼저 출력
                for k in preferred_order:
                    if k not in pi or k in printed or row2 >= page_bottom:
                        continue

                    v = pi[k]
                    line = f"{k}: {v}"
                    printed.add(k)

                    changed = (
                        prev_pi is not None
                        and k in prev_pi
                        and prev_pi.get(k) != v
                    )

                    if changed:
                        stdscr.attron(curses.color_pair(2))

                    tmp = line
                    while tmp and row2 < page_bottom:
                        stdscr.addstr(row2, right_x, tmp[: right_width])
                        tmp = tmp[right_width:]
                        row2 += 1

                    if changed:
                        stdscr.attroff(curses.color_pair(2))

                # 나머지 출력
                for k, v in pi.items():
                    if k in printed:
                        continue
                    if row2 >= page_bottom:
                        break

                    line = f"{k}: {v}"
                    changed = (
                        prev_pi is not None
                        and k in prev_pi
                        and prev_pi.get(k) != v
                    )

                    if changed:
                        stdscr.attron(curses.color_pair(2))

                    tmp = line
                    while tmp and row2 < page_bottom:
                        stdscr.addstr(row2, right_x, tmp[: right_width])
                        tmp = tmp[right_width:]
                        row2 += 1

                    if changed:
                        stdscr.attroff(curses.color_pair(2))

    # 구분선
    stdscr.hline(mem_top, right_x, ord("-"), right_width)

    # 오른쪽 하단 레이아웃 - Mem Dump
    row_mem = mem_top + 1

    if row_mem < mem_bottom:
        mem_title = "Mem Dump"
        mem_help = "[md <va> [size]]"
        mem_label = f"{mem_title}  {mem_help}"
        mem_x = right_x + max(0, (right_width - len(mem_label)) // 2)
        stdscr.addstr(row_mem, mem_x, mem_label[: right_width])
        row_mem += 2

    if sess.mem_dump_lines:
        for line in sess.mem_dump_lines:
            if row_mem >= mem_bottom:
                break
            stdscr.addstr(row_mem, right_x, line[: right_width])
            row_mem += 1

    # 커맨드 프롬프트
    stdscr.hline(h - 3, 0, ord("-"), w)
    status_line = sess.status
    stdscr.addstr(h - 2, 0, status_line[: w - 1])

    prompt = f"cmd> {cmd_buf}"
    stdscr.addstr(h - 1, 0, prompt[: w - 1])
    stdscr.move(h - 1, len("cmd> ") + len(cmd_buf))

    stdscr.refresh()

def tui_main(stdscr) -> None:
    curses.curs_set(1)
    stdscr.keypad(True)
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(1, curses.COLOR_WHITE, -1)
    curses.init_pair(2, curses.COLOR_YELLOW, -1)

    sess = DebugSession(target="localhost:1234", gdb_path="gdb")
    cmd_buf = ""
    sess.status = "init: connecting to gdb at localhost:1234 ..."
    sess.connect()

    while True:
        draw_ui(stdscr, sess, cmd_buf)
        ch = stdscr.getch()

        if ch in (curses.KEY_BACKSPACE, 127, 8):
            cmd_buf = cmd_buf[:-1]
            continue

        elif ch in (curses.KEY_ENTER, 10, 13):
            cmd = cmd_buf.strip()
            cmd_buf = ""

            if cmd == "q":
                sess.status = "quit requested ... closing gdb and ui"
                draw_ui(stdscr, sess, "")
                stdscr.refresh()
                sess.close()
                stdscr.erase()
                stdscr.refresh()
                return

            elif cmd == "n":
                sess.status = "stepi ... (GDB 응답 대기 중; 입력 잠시 비활성화)"
                draw_ui(stdscr, sess, "[GDB 응답 대기 중 ...]")
                sess.cmd_step()
                draw_ui(stdscr, sess, "")

            elif cmd == "c":
                sess.status = "continue ... (GDB 응답 대기 중; 입력 잠시 비활성화)"
                draw_ui(stdscr, sess, "[GDB 응답 대기 중 ...]")
                sess.cmd_continue()
                draw_ui(stdscr, sess, "")

            elif cmd == "p":
                sess.status = "pause ... (GDB 응답 대기 중; 입력 잠시 비활성화)"
                draw_ui(stdscr, sess, "[GDB 응답 대기 중 ...]")
                sess.cmd_pause()
                draw_ui(stdscr, sess, "")

            elif cmd == "r":
                sess.status = "refresh ... (GDB 응답 대기 중; 입력 잠시 비활성화)"
                draw_ui(stdscr, sess, "[GDB 응답 대기 중 ...]")
                sess.cmd_refresh()
                draw_ui(stdscr, sess, "")

            elif cmd.startswith("va "):
                arg = cmd[3:].strip()
                if arg.lower() == "rip":
                    sess.set_inspect_rip()
                    sess.status = "inspect 모드: RIP-follow"
                else:
                    try:
                        va = int(arg, 0)
                        sess.set_inspect_va(va)
                        sess.status = f"inspect 모드: VA=0x{va:x}"
                    except ValueError:
                        sess.status = f"invalid VA: {arg!r}"

            elif cmd.startswith("md "):
                parts = cmd.split()
                if len(parts) < 2:
                    sess.status = "usage: md <va> [size]"
                else:
                    target = parts[1]
                    size = 64
                    if len(parts) >= 3:
                        try:
                            size = int(parts[2], 0)
                        except ValueError:
                            size = 64

                    try:
                        va = int(target, 0)
                        sess.memdump(va, size)
                    except ValueError:
                        sess.status = f"invalid VA for md: {target!r}"

            elif cmd == "":
                pass

            else:
                sess.status = f"unknown cmd: {cmd!r}"

        else:
            if 32 <= ch <= 126:
                cmd_buf += chr(ch)
            else:
                sess.status = f"unknown keycode: {ch}"

if __name__ == "__main__":
    curses.wrapper(tui_main)
