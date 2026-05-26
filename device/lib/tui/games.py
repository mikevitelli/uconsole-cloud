"""TUI module: games"""

import curses
import os
import random
import subprocess
import time

from tui.framework import (
    C_BORDER, C_CAT, C_DIM, C_FOOTER, C_HEADER, C_ITEM, C_SEL, C_STATUS,
    _gp_set_cooldown, _tui_input_loop, open_gamepad, read_gamepad, wait_for_input,
)
import tui_lib as tui


# ═══════════════════════════════════════════════════════════════════════
#  Minesweeper
# ═══════════════════════════════════════════════════════════════════════

def run_minesweeper(scr):
    """Minesweeper game with themed panels and gamepad support."""
    import random

    js = open_gamepad()
    scr.timeout(100)
    tui.init_gauge_colors()

    hdr = curses.color_pair(C_HEADER) | curses.A_BOLD
    val = curses.color_pair(C_ITEM) | curses.A_BOLD
    dim = curses.color_pair(C_DIM)
    brd = curses.color_pair(C_BORDER)
    sel = curses.color_pair(C_SEL) | curses.A_BOLD
    ok_attr = curses.color_pair(tui.C_OK) | curses.A_BOLD
    warn_attr = curses.color_pair(tui.C_WARN) | curses.A_BOLD
    crit_attr = curses.color_pair(tui.C_CRIT) | curses.A_BOLD
    flag_attr = curses.color_pair(C_CAT) | curses.A_BOLD
    num_attr = [
        dim,                                                  # 0 (empty)
        curses.color_pair(C_STATUS) | curses.A_BOLD,          # 1
        ok_attr,                                              # 2
        crit_attr,                                            # 3
        curses.color_pair(C_HEADER) | curses.A_BOLD,          # 4
        warn_attr,                                            # 5+
    ]

    def new_game():
        nonlocal board, revealed, flagged, cx, cy, game_over, won, elapsed
        h, w = scr.getmaxyx()
        # grid takes rows*2+1 lines; reserve 4 for header/stats/gap/footer
        r = min(9, (h - 4) // 2)
        c = min(16, (w - 3) // 4)
        m = max(5, r * c // 6)
        board = [[0] * c for _ in range(r)]
        revealed = [[False] * c for _ in range(r)]
        flagged = [[False] * c for _ in range(r)]
        pos = [(ri, ci) for ri in range(r) for ci in range(c)]
        for ri, ci in random.sample(pos, m):
            board[ri][ci] = -1
        for ri in range(r):
            for ci in range(c):
                if board[ri][ci] == -1:
                    continue
                n = 0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        nr, nc = ri + dr, ci + dc
                        if 0 <= nr < r and 0 <= nc < c and board[nr][nc] == -1:
                            n += 1
                board[ri][ci] = n
        cx, cy = 0, 0
        game_over = False
        won = False
        elapsed = time.time()
        return r, c, m

    board = revealed = flagged = None
    cx = cy = 0
    game_over = won = False
    elapsed = time.time()
    rows, cols, mines = new_game()

    def flood_reveal(r, c):
        if r < 0 or r >= rows or c < 0 or c >= cols:
            return
        if revealed[r][c] or flagged[r][c]:
            return
        revealed[r][c] = True
        if board[r][c] == 0:
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    flood_reveal(r + dr, c + dc)

    def check_win():
        for r in range(rows):
            for c in range(cols):
                if board[r][c] != -1 and not revealed[r][c]:
                    return False
        return True

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        pw = w - 2  # panel width

        flags_placed = sum(flagged[r][c] for r in range(rows) for c in range(cols))
        revealed_count = sum(revealed[r][c] for r in range(rows) for c in range(cols))
        secs = int(time.time() - elapsed) if not game_over else int(elapsed)
        timer_str = f"{secs // 60}:{secs % 60:02d}"

        # -- Layout calculations --
        CELL_W = 4
        grid_w = cols * CELL_W + 1
        grid_h = rows * 2 + 1
        ox = max(1, (w - grid_w) // 2)
        # vertical center: header(1) + stats(1) + grid + game_over(1) + footer(1)
        total_content = 2 + grid_h + 2
        oy = max(0, (h - total_content) // 2)

        y = oy

        # -- Header --
        title = "MINESWEEPER"
        mines_left = mines - flags_placed
        if game_over:
            result_str = "YOU WIN!" if won else "GAME OVER"
            result_attr = ok_attr if won else crit_attr
            tui.put(scr, y, ox, title, grid_w, hdr)
            tui.put(scr, y, ox + grid_w - len(result_str), result_str, len(result_str), result_attr)
        else:
            tui.put(scr, y, ox, title, grid_w, hdr)
            right_info = f"✹ {mines_left}  ▸ {flags_placed}  {timer_str}"
            tui.put(scr, y, ox + grid_w - len(right_info), right_info, len(right_info), val)
        y += 1

        # -- Board grid --
        top = "┌" + "┬".join("───" for _ in range(cols)) + "┐"
        tui.put(scr, y, ox, top, grid_w, brd)
        y += 1

        for r in range(rows):
            # cell row: │ . │ 1 │ F │
            for c in range(cols):
                cell_x = ox + c * CELL_W
                tui.put(scr, y, cell_x, "│", 1, brd)

                if revealed[r][c]:
                    if board[r][c] == -1:
                        ch = " ✹ "
                        attr = crit_attr
                    elif board[r][c] == 0:
                        ch = "   "
                        attr = dim
                    else:
                        ch = f" {board[r][c]} "
                        attr = num_attr[min(board[r][c], 5)]
                elif flagged[r][c]:
                    ch = " ▸ "
                    attr = flag_attr
                elif game_over and board[r][c] == -1:
                    ch = " ✹ "
                    attr = curses.color_pair(C_DIM)
                else:
                    ch = " ■ "
                    attr = curses.color_pair(C_BORDER)

                if r == cy and c == cx and not game_over:
                    attr = sel | curses.A_REVERSE

                tui.put(scr, y, cell_x + 1, ch, 3, attr)

            # right border
            tui.put(scr, y, ox + cols * CELL_W, "│", 1, brd)
            y += 1

            # row separator: ├───┼───┼───┤  (or bottom: └───┴───┴───┘)
            if r < rows - 1:
                sep = "├" + "┼".join("───" for _ in range(cols)) + "┤"
            else:
                sep = "└" + "┴".join("───" for _ in range(cols)) + "┘"
            tui.put(scr, y, ox, sep, grid_w, brd)
            y += 1

        y += 1

        # -- Game over overlay --
        if game_over:
            msg = "A New Game │ B Quit" if won else "A Try Again │ B Quit"
            mx = max(1, (pw - len(msg)) // 2)
            tui.put(scr, y, mx, msg, len(msg), ok_attr if won else warn_attr)
            y += 1

        # -- Cursor position --
        pos_str = f"({cx + 1},{cy + 1})"
        tui.put(scr, h - 2, pw - len(pos_str), pos_str, len(pos_str), dim)

        # -- Footer --
        bar = " ←↑↓→ Move │ A Reveal │ X Flag │ B Quit "
        tui.put(scr, h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue

        if game_over:
            if key == ord("q") or key == ord("Q") or gp == "back":
                break
            elapsed = int(time.time() - elapsed)
            rows, cols, mines = new_game()
            continue

        if key == ord("q") or key == ord("Q") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            cy = max(0, cy - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            cy = min(rows - 1, cy + 1)
        elif key == curses.KEY_LEFT or key == ord("h"):
            cx = max(0, cx - 1)
        elif key == curses.KEY_RIGHT or key == ord("l"):
            cx = min(cols - 1, cx + 1)
        elif gp == "refresh" or key == ord("f") or key == ord("x"):
            if not revealed[cy][cx]:
                flagged[cy][cx] = not flagged[cy][cx]
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter" or key == ord("a"):
            if not flagged[cy][cx] and not revealed[cy][cx]:
                if board[cy][cx] == -1:
                    revealed[cy][cx] = True
                    game_over = True
                    won = False
                    elapsed = time.time() - elapsed
                else:
                    flood_reveal(cy, cx)
                    if check_win():
                        game_over = True
                        won = True
                        elapsed = time.time() - elapsed

    if js:
        js.close()


# ═══════════════════════════════════════════════════════════════════════
#  Snake
# ═══════════════════════════════════════════════════════════════════════

def run_snake(scr):
    """Classic snake game with themed panels and gamepad support."""
    js = open_gamepad()
    tui.init_gauge_colors()

    hdr = curses.color_pair(C_HEADER) | curses.A_BOLD
    val = curses.color_pair(C_ITEM) | curses.A_BOLD
    dim = curses.color_pair(C_DIM)
    brd = curses.color_pair(C_BORDER)
    sel_attr = curses.color_pair(C_SEL) | curses.A_BOLD
    ok_attr = curses.color_pair(tui.C_OK) | curses.A_BOLD
    warn_attr = curses.color_pair(tui.C_WARN) | curses.A_BOLD
    crit_attr = curses.color_pair(tui.C_CRIT) | curses.A_BOLD
    food_attr = curses.color_pair(C_CAT) | curses.A_BOLD

    # Board fits in 24x80: 18 rows x 20 cols playfield
    ROWS, COLS = 10, 20

    def new_game():
        snake = [(ROWS // 2, COLS // 2 - i) for i in range(3)]
        direction = (0, 1)  # moving right
        food = place_food(snake)
        return snake, direction, food, 0, False

    def place_food(snake):
        empty = [(r, c) for r in range(ROWS) for c in range(COLS)
                 if (r, c) not in snake]
        return random.choice(empty) if empty else (0, 0)

    snake, direction, food, score, game_over = new_game()
    last_move = time.time()
    speed = 0.15  # seconds per step

    scr.timeout(50)

    while True:
        h, w = scr.getmaxyx()
        now = time.time()

        # -- Input --
        key, gp = _tui_input_loop(scr, js)

        if key == ord("q") or key == ord("Q") or gp == "back":
            if game_over:
                break
            else:
                break
        if game_over:
            if key in (curses.KEY_ENTER, 10, 13) or gp == "enter" or key == ord("a"):
                snake, direction, food, score, game_over = new_game()
                last_move = time.time()
            continue

        # Direction change (prevent reversal)
        dr, dc = direction
        if key == curses.KEY_UP or key == ord("k"):
            if dr != 1:
                direction = (-1, 0)
        elif key == curses.KEY_DOWN or key == ord("j"):
            if dr != -1:
                direction = (1, 0)
        elif key == curses.KEY_LEFT or key == ord("h"):
            if dc != 1:
                direction = (0, -1)
        elif key == curses.KEY_RIGHT or key == ord("l"):
            if dc != -1:
                direction = (0, 1)

        # -- Game tick --
        if now - last_move < speed:
            # Still render
            pass
        else:
            last_move = now
            dr, dc = direction
            head_r, head_c = snake[0]
            nr, nc = head_r + dr, head_c + dc

            # Collision check
            if nr < 0 or nr >= ROWS or nc < 0 or nc >= COLS or (nr, nc) in snake:
                game_over = True
            else:
                snake.insert(0, (nr, nc))
                if (nr, nc) == food:
                    score += 10
                    food = place_food(snake)
                else:
                    snake.pop()

        # -- Render --
        scr.erase()

        CELL_W = 2
        grid_w = COLS * CELL_W + 1
        grid_h = ROWS * 2 + 1
        ox = max(1, (w - grid_w) // 2)
        total_content = 2 + grid_h + 2
        oy = max(0, (h - total_content) // 2)

        y = oy

        # Header
        title = "SNAKE"
        score_str = f"Score: {score}"
        tui.put(scr, y, ox, title, grid_w, hdr)
        tui.put(scr, y, ox + grid_w - len(score_str), score_str, len(score_str), val)
        y += 1

        # Top border
        top = "┌" + "┬".join("─" for _ in range(COLS)) + "┐"
        tui.put(scr, y, ox, top, grid_w, brd)
        y += 1

        snake_set = set(snake)
        head = snake[0] if snake else (-1, -1)

        for r in range(ROWS):
            for c in range(COLS):
                cell_x = ox + c * CELL_W
                tui.put(scr, y, cell_x, "│", 1, brd)

                if (r, c) == head:
                    tui.put(scr, y, cell_x + 1, "█", 1, ok_attr)
                elif (r, c) in snake_set:
                    tui.put(scr, y, cell_x + 1, "█", 1, sel_attr)
                elif (r, c) == food:
                    tui.put(scr, y, cell_x + 1, "◆", 1, food_attr)
                else:
                    tui.put(scr, y, cell_x + 1, " ", 1, dim)

            tui.put(scr, y, ox + COLS * CELL_W, "│", 1, brd)
            y += 1

            if r < ROWS - 1:
                sep = "├" + "┼".join("─" for _ in range(COLS)) + "┤"
            else:
                sep = "└" + "┴".join("─" for _ in range(COLS)) + "┘"
            tui.put(scr, y, ox, sep, grid_w, brd)
            y += 1

        y += 1

        if game_over:
            msg = "GAME OVER"
            tui.put(scr, y, max(1, (w - len(msg)) // 2), msg, len(msg), crit_attr)
            y += 1
            restart_msg = "A Try Again │ B Quit"
            tui.put(scr, y, max(1, (w - len(restart_msg)) // 2), restart_msg,
                    len(restart_msg), warn_attr)

        # Footer
        bar = " ←↑↓→ Move │ B Quit "
        tui.put(scr, h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

    if js:
        js.close()
    scr.timeout(100)


# ═══════════════════════════════════════════════════════════════════════
#  Tetris
# ═══════════════════════════════════════════════════════════════════════

def run_tetris(scr):
    """Falling block puzzle with themed panels and gamepad support."""
    js = open_gamepad()
    tui.init_gauge_colors()

    hdr = curses.color_pair(C_HEADER) | curses.A_BOLD
    val = curses.color_pair(C_ITEM) | curses.A_BOLD
    dim = curses.color_pair(C_DIM)
    brd = curses.color_pair(C_BORDER)
    ok_attr = curses.color_pair(tui.C_OK) | curses.A_BOLD
    warn_attr = curses.color_pair(tui.C_WARN) | curses.A_BOLD
    crit_attr = curses.color_pair(tui.C_CRIT) | curses.A_BOLD
    cat_attr = curses.color_pair(C_CAT) | curses.A_BOLD
    status_attr = curses.color_pair(C_STATUS) | curses.A_BOLD

    WELL_W, WELL_H = 10, 20

    # Tetrominoes: each is list of rotations, each rotation is list of (r, c) offsets
    PIECES = {
        "I": [[(0, 0), (0, 1), (0, 2), (0, 3)],
              [(0, 0), (1, 0), (2, 0), (3, 0)]],
        "O": [[(0, 0), (0, 1), (1, 0), (1, 1)]],
        "T": [[(0, 0), (0, 1), (0, 2), (1, 1)],
              [(0, 0), (1, 0), (2, 0), (1, 1)],
              [(1, 0), (1, 1), (1, 2), (0, 1)],
              [(0, 0), (1, 0), (2, 0), (1, -1)]],
        "S": [[(0, 1), (0, 2), (1, 0), (1, 1)],
              [(0, 0), (1, 0), (1, 1), (2, 1)]],
        "Z": [[(0, 0), (0, 1), (1, 1), (1, 2)],
              [(0, 1), (1, 0), (1, 1), (2, 0)]],
        "J": [[(0, 0), (1, 0), (1, 1), (1, 2)],
              [(0, 0), (0, 1), (1, 0), (2, 0)],
              [(0, 0), (0, 1), (0, 2), (1, 2)],
              [(0, 0), (1, 0), (2, 0), (2, -1)]],
        "L": [[(0, 2), (1, 0), (1, 1), (1, 2)],
              [(0, 0), (1, 0), (2, 0), (2, 1)],
              [(0, 0), (0, 1), (0, 2), (1, 0)],
              [(0, 0), (0, 1), (1, 1), (2, 1)]],
    }
    PIECE_NAMES = list(PIECES.keys())
    LINE_SCORES = {0: 0, 1: 100, 2: 300, 3: 500, 4: 800}

    def new_game():
        well = [[0] * WELL_W for _ in range(WELL_H)]
        return well, 0, 0, 0, False

    def random_piece():
        name = random.choice(PIECE_NAMES)
        return name, 0  # name, rotation index

    def get_cells(name, rot, pr, pc):
        shape = PIECES[name][rot % len(PIECES[name])]
        return [(pr + dr, pc + dc) for dr, dc in shape]

    def fits(well, cells):
        for r, c in cells:
            if r < 0 or r >= WELL_H or c < 0 or c >= WELL_W:
                return False
            if well[r][c]:
                return False
        return True

    def lock_piece(well, cells):
        for r, c in cells:
            if 0 <= r < WELL_H and 0 <= c < WELL_W:
                well[r][c] = 1

    def clear_lines(well):
        cleared = 0
        r = WELL_H - 1
        while r >= 0:
            if all(well[r]):
                del well[r]
                well.insert(0, [0] * WELL_W)
                cleared += 1
            else:
                r -= 1
        return cleared

    well, score, lines, level, game_over = new_game()
    piece_name, piece_rot = random_piece()
    next_name, next_rot = random_piece()
    piece_r, piece_c = 0, WELL_W // 2 - 1
    last_drop = time.time()

    # Check initial spawn
    if not fits(well, get_cells(piece_name, piece_rot, piece_r, piece_c)):
        game_over = True

    scr.timeout(50)

    while True:
        h, w = scr.getmaxyx()
        now = time.time()

        drop_speed = max(0.05, 0.5 - level * 0.04)

        # -- Input --
        key, gp = _tui_input_loop(scr, js)

        if key == ord("q") or key == ord("Q") or gp == "back":
            break

        if game_over:
            if key in (curses.KEY_ENTER, 10, 13) or gp == "enter" or key == ord("a"):
                well, score, lines, level, game_over = new_game()
                piece_name, piece_rot = random_piece()
                next_name, next_rot = random_piece()
                piece_r, piece_c = 0, WELL_W // 2 - 1
                last_drop = time.time()
                if not fits(well, get_cells(piece_name, piece_rot, piece_r, piece_c)):
                    game_over = True
        else:
            # Movement
            if key == curses.KEY_LEFT or key == ord("h"):
                cells = get_cells(piece_name, piece_rot, piece_r, piece_c - 1)
                if fits(well, cells):
                    piece_c -= 1
            elif key == curses.KEY_RIGHT or key == ord("l"):
                cells = get_cells(piece_name, piece_rot, piece_r, piece_c + 1)
                if fits(well, cells):
                    piece_c += 1
            elif key == curses.KEY_DOWN or key == ord("j"):
                cells = get_cells(piece_name, piece_rot, piece_r + 1, piece_c)
                if fits(well, cells):
                    piece_r += 1
                    last_drop = now
            elif key == curses.KEY_UP or key == ord("a") or gp == "enter":
                new_rot = (piece_rot + 1) % len(PIECES[piece_name])
                cells = get_cells(piece_name, new_rot, piece_r, piece_c)
                if fits(well, cells):
                    piece_rot = new_rot
            elif key == ord("x") or gp == "refresh":
                # Hard drop
                while True:
                    cells = get_cells(piece_name, piece_rot, piece_r + 1, piece_c)
                    if fits(well, cells):
                        piece_r += 1
                    else:
                        break
                last_drop = now - drop_speed  # Force lock on next tick

            # Gravity
            if not game_over and now - last_drop >= drop_speed:
                last_drop = now
                cells = get_cells(piece_name, piece_rot, piece_r + 1, piece_c)
                if fits(well, cells):
                    piece_r += 1
                else:
                    # Lock piece
                    lock_piece(well, get_cells(piece_name, piece_rot, piece_r, piece_c))
                    cleared = clear_lines(well)
                    lines += cleared
                    score += LINE_SCORES.get(cleared, 800)
                    level = lines // 10
                    # Next piece
                    piece_name, piece_rot = next_name, next_rot
                    next_name, next_rot = random_piece()
                    piece_r, piece_c = 0, WELL_W // 2 - 1
                    if not fits(well, get_cells(piece_name, piece_rot, piece_r, piece_c)):
                        game_over = True

        # -- Render --
        scr.erase()

        CELL_W = 2
        well_draw_w = WELL_W * CELL_W + 2  # +2 for left/right borders
        next_panel_w = 12
        total_w = well_draw_w + 2 + next_panel_w
        ox = max(1, (w - total_w) // 2)
        total_content = 2 + WELL_H + 2
        oy = max(0, (h - total_content) // 2)

        y = oy

        # Header
        title = "TETRIS"
        score_str = f"Score: {score}  Lvl: {level}  Lines: {lines}"
        tui.put(scr, y, ox, title, well_draw_w, hdr)
        tui.put(scr, y, ox + well_draw_w - len(score_str) - 1, score_str,
                len(score_str), val)
        y += 1

        # Build display grid (well + current piece)
        display = [row[:] for row in well]
        if not game_over:
            for r, c in get_cells(piece_name, piece_rot, piece_r, piece_c):
                if 0 <= r < WELL_H and 0 <= c < WELL_W:
                    display[r][c] = 2  # active piece marker

        # Top border
        top_border = "┌" + "──" * WELL_W + "┐"
        tui.put(scr, y, ox, top_border, well_draw_w, brd)
        y += 1

        for r in range(WELL_H):
            tui.put(scr, y, ox, "│", 1, brd)
            for c in range(WELL_W):
                cell_x = ox + 1 + c * CELL_W
                if display[r][c] == 2:
                    tui.put(scr, y, cell_x, "██", 2, cat_attr)
                elif display[r][c] == 1:
                    tui.put(scr, y, cell_x, "██", 2, status_attr)
                else:
                    tui.put(scr, y, cell_x, "  ", 2, dim)
            tui.put(scr, y, ox + 1 + WELL_W * CELL_W, "│", 1, brd)
            y += 1

        # Bottom border
        bot_border = "└" + "──" * WELL_W + "┘"
        tui.put(scr, y, ox, bot_border, well_draw_w, brd)

        # Next piece panel (to the right)
        npx = ox + well_draw_w + 2
        npy = oy + 1
        tui.put(scr, npy, npx, "NEXT", 4, hdr)
        npy += 1
        tui.put(scr, npy, npx, "┌────────┐", 10, brd)
        npy += 1
        # Render next piece in a 4x4 area
        next_cells = set(get_cells(next_name, next_rot, 0, 0))
        for nr in range(4):
            tui.put(scr, npy, npx, "│", 1, brd)
            for nc in range(4):
                cx = npx + 1 + nc * 2
                if (nr, nc) in next_cells:
                    tui.put(scr, npy, cx, "██", 2, cat_attr)
                else:
                    tui.put(scr, npy, cx, "  ", 2, dim)
            tui.put(scr, npy, npx + 9, "│", 1, brd)
            npy += 1
        tui.put(scr, npy, npx, "└────────┘", 10, brd)

        if game_over:
            msg = "GAME OVER"
            tui.put(scr, h - 3, max(1, (w - len(msg)) // 2), msg, len(msg), crit_attr)
            restart_msg = "A Try Again │ B Quit"
            tui.put(scr, h - 2, max(1, (w - len(restart_msg)) // 2), restart_msg,
                    len(restart_msg), warn_attr)

        # Footer
        bar = " ←→ Move │ ↓ Drop │ ↑/A Rotate │ X Hard Drop │ B Quit "
        tui.put(scr, h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

    if js:
        js.close()
    scr.timeout(100)


# ═══════════════════════════════════════════════════════════════════════
#  2048
# ═══════════════════════════════════════════════════════════════════════

def run_2048(scr):
    """Sliding number tiles puzzle with themed panels and gamepad support."""
    js = open_gamepad()
    scr.timeout(100)
    tui.init_gauge_colors()

    hdr = curses.color_pair(C_HEADER) | curses.A_BOLD
    val = curses.color_pair(C_ITEM) | curses.A_BOLD
    dim = curses.color_pair(C_DIM)
    brd = curses.color_pair(C_BORDER)
    ok_attr = curses.color_pair(tui.C_OK) | curses.A_BOLD
    warn_attr = curses.color_pair(tui.C_WARN) | curses.A_BOLD
    crit_attr = curses.color_pair(tui.C_CRIT) | curses.A_BOLD
    cat_attr = curses.color_pair(C_CAT) | curses.A_BOLD
    status_attr = curses.color_pair(C_STATUS) | curses.A_BOLD
    sel_attr = curses.color_pair(C_SEL) | curses.A_BOLD

    SIZE = 4
    CELL_W = 6  # width per cell (content area)

    def new_game():
        grid = [[0] * SIZE for _ in range(SIZE)]
        add_tile(grid)
        add_tile(grid)
        return grid, 0, False, False

    def add_tile(grid):
        empty = [(r, c) for r in range(SIZE) for c in range(SIZE) if grid[r][c] == 0]
        if empty:
            r, c = random.choice(empty)
            grid[r][c] = 4 if random.random() < 0.1 else 2

    def slide_row(row):
        """Slide and merge a single row to the left. Returns (new_row, points)."""
        # Remove zeros
        tiles = [v for v in row if v != 0]
        merged = []
        pts = 0
        skip = False
        for i in range(len(tiles)):
            if skip:
                skip = False
                continue
            if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
                merged.append(tiles[i] * 2)
                pts += tiles[i] * 2
                skip = True
            else:
                merged.append(tiles[i])
        # Pad with zeros
        merged += [0] * (SIZE - len(merged))
        return merged, pts

    def move(grid, direction):
        """Apply move. Returns (new_grid, points, changed)."""
        new_grid = [row[:] for row in grid]
        total_pts = 0
        changed = False

        if direction == "left":
            for r in range(SIZE):
                new_row, pts = slide_row(new_grid[r])
                if new_row != new_grid[r]:
                    changed = True
                new_grid[r] = new_row
                total_pts += pts
        elif direction == "right":
            for r in range(SIZE):
                new_row, pts = slide_row(new_grid[r][::-1])
                new_row = new_row[::-1]
                if new_row != new_grid[r]:
                    changed = True
                new_grid[r] = new_row
                total_pts += pts
        elif direction == "up":
            for c in range(SIZE):
                col = [new_grid[r][c] for r in range(SIZE)]
                new_col, pts = slide_row(col)
                for r in range(SIZE):
                    if new_grid[r][c] != new_col[r]:
                        changed = True
                    new_grid[r][c] = new_col[r]
                total_pts += pts
        elif direction == "down":
            for c in range(SIZE):
                col = [new_grid[r][c] for r in range(SIZE)][::-1]
                new_col, pts = slide_row(col)
                new_col = new_col[::-1]
                for r in range(SIZE):
                    if new_grid[r][c] != new_col[r]:
                        changed = True
                    new_grid[r][c] = new_col[r]
                total_pts += pts

        return new_grid, total_pts, changed

    def can_move(grid):
        for r in range(SIZE):
            for c in range(SIZE):
                if grid[r][c] == 0:
                    return True
                if c + 1 < SIZE and grid[r][c] == grid[r][c + 1]:
                    return True
                if r + 1 < SIZE and grid[r][c] == grid[r + 1][c]:
                    return True
        return False

    def has_2048(grid):
        for r in range(SIZE):
            for c in range(SIZE):
                if grid[r][c] >= 2048:
                    return True
        return False

    def tile_attr(v):
        if v == 0:
            return dim
        elif v <= 4:
            return val
        elif v <= 16:
            return status_attr
        elif v <= 128:
            return cat_attr
        elif v <= 512:
            return ok_attr
        elif v <= 1024:
            return warn_attr
        else:
            return sel_attr

    grid, score, won_flag, game_over = new_game()

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        grid_draw_w = SIZE * (CELL_W + 1) + 1
        grid_draw_h = SIZE * 2 + 1
        ox = max(1, (w - grid_draw_w) // 2)
        total_content = 2 + grid_draw_h + 2
        oy = max(0, (h - total_content) // 2)

        y = oy

        # Header
        title = "2048"
        score_str = f"Score: {score}"
        tui.put(scr, y, ox, title, grid_draw_w, hdr)
        tui.put(scr, y, ox + grid_draw_w - len(score_str), score_str,
                len(score_str), val)
        y += 1

        # Grid top border
        top = "┌" + "┬".join("─" * CELL_W for _ in range(SIZE)) + "┐"
        tui.put(scr, y, ox, top, grid_draw_w, brd)
        y += 1

        for r in range(SIZE):
            for c in range(SIZE):
                cell_x = ox + c * (CELL_W + 1)
                tui.put(scr, y, cell_x, "│", 1, brd)
                v = grid[r][c]
                if v == 0:
                    txt = " " * CELL_W
                else:
                    txt = str(v).center(CELL_W)
                tui.put(scr, y, cell_x + 1, txt, CELL_W, tile_attr(v))

            tui.put(scr, y, ox + SIZE * (CELL_W + 1), "│", 1, brd)
            y += 1

            if r < SIZE - 1:
                sep = "├" + "┼".join("─" * CELL_W for _ in range(SIZE)) + "┤"
            else:
                sep = "└" + "┴".join("─" * CELL_W for _ in range(SIZE)) + "┘"
            tui.put(scr, y, ox, sep, grid_draw_w, brd)
            y += 1

        y += 1

        if won_flag and not game_over:
            msg = "YOU WIN! Keep going?"
            tui.put(scr, y, max(1, (w - len(msg)) // 2), msg, len(msg), ok_attr)
        elif game_over:
            msg = "GAME OVER"
            tui.put(scr, y, max(1, (w - len(msg)) // 2), msg, len(msg), crit_attr)
            y += 1
            restart_msg = "A New Game │ B Quit"
            tui.put(scr, y, max(1, (w - len(restart_msg)) // 2), restart_msg,
                    len(restart_msg), warn_attr)

        # Footer
        bar = " ←↑↓→ Slide │ A New Game │ B Quit "
        tui.put(scr, h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

        # -- Input --
        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue

        if key == ord("q") or key == ord("Q") or gp == "back":
            break

        if game_over:
            if key in (curses.KEY_ENTER, 10, 13) or gp == "enter" or key == ord("a"):
                grid, score, won_flag, game_over = new_game()
            continue

        direction = None
        if key == curses.KEY_UP or key == ord("k"):
            direction = "up"
        elif key == curses.KEY_DOWN or key == ord("j"):
            direction = "down"
        elif key == curses.KEY_LEFT or key == ord("h"):
            direction = "left"
        elif key == curses.KEY_RIGHT or key == ord("l"):
            direction = "right"

        if direction:
            new_grid, pts, changed = move(grid, direction)
            if changed:
                grid = new_grid
                score += pts
                add_tile(grid)
                if has_2048(grid) and not won_flag:
                    won_flag = True
                if not can_move(grid):
                    game_over = True

        # New game on A when not game_over
        if key == ord("a") or (gp == "enter" and not direction):
            grid, score, won_flag, game_over = new_game()

    if js:
        js.close()


# ═══════════════════════════════════════════════════════════════════════
#  ROM Launcher
# ═══════════════════════════════════════════════════════════════════════

ROM_DIRS = [
    os.path.expanduser("~/retropie/roms"),
    os.path.expanduser("~/roms"),
    "/opt/retropie/roms",
]

ROM_EXTENSIONS = {
    ".gb", ".gbc", ".gba", ".n64", ".z64", ".v64",
    ".nes", ".snes", ".smc", ".sfc",
}

# SDL controller mapping for ClockworkPI uConsole gamepad
# SDL 2.26+ encodes CRC16 in GUID bytes 2-3: 030000fd...
# Physical layout: A=b1, B=b2, X=b3, Y=b0
SDL_CONTROLLER_MAP = (
    "030000fdaf1e00002400000010010000,"
    "ClockworkPI uConsole,"
    "a:b1,b:b2,back:b8,"
    "dpdown:+a1,dpleft:-a0,dpright:+a0,dpup:-a1,"
    "start:b9,x:b3,y:b0,"
    "platform:Linux,"
)

MGBA_ARGS = ["-f", "-C", "lockAspectRatio=1"]

# Per-system emulator options: {system: [(name, args_fn), ...]}
# First entry is the default; user prefs override via config file.
EMULATOR_OPTIONS = {
    "gb": [
        ("mgba",    lambda: _mgba_entry()),
        ("gearboy", lambda: _gearboy_entry()),
    ],
    "gbc": [
        ("mgba",    lambda: _mgba_entry()),
        ("gearboy", lambda: _gearboy_entry()),
    ],
    "gba": [
        ("mgba", lambda: _mgba_entry()),
    ],
    "n64": [
        ("retroarch (mupen64plus)", lambda: _retroarch_entry("mupen64plus_next")),
    ],
    "nes": [
        ("retroarch", lambda: _retroarch_entry(None)),
    ],
    "snes": [
        ("retroarch", lambda: _retroarch_entry(None)),
    ],
}

# Map file extension to system key
EXT_TO_SYSTEM = {
    ".gb": "gb", ".gbc": "gbc", ".gba": "gba",
    ".n64": "n64", ".z64": "n64", ".v64": "n64",
    ".nes": "nes", ".snes": "snes", ".smc": "snes", ".sfc": "snes",
}

RETROARCH_CORE_DIRS = [
    os.path.expanduser("~/.config/retroarch/cores"),
    "/usr/lib/libretro",
    "/usr/lib/aarch64-linux-gnu/libretro",
]

EMU_PREFS_FILE = os.path.expanduser("~/.config/uconsole/emulator-prefs.conf")


def _load_emu_prefs():
    """Load emulator preferences from config file."""
    prefs = {}
    try:
        with open(EMU_PREFS_FILE) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    sys_key, emu_name = line.split("=", 1)
                    prefs[sys_key.strip()] = emu_name.strip()
    except FileNotFoundError:
        pass
    return prefs


def _save_emu_prefs(prefs):
    """Save emulator preferences to config file."""
    os.makedirs(os.path.dirname(EMU_PREFS_FILE), exist_ok=True)
    with open(EMU_PREFS_FILE, "w") as f:
        f.write("# Emulator preferences per system\n")
        for sys_key in sorted(prefs):
            f.write(f"{sys_key}={prefs[sys_key]}\n")


def _mgba_entry():
    """Build (path, args) for mGBA."""
    path = _find_binary("mgba")
    if path:
        return (path, list(MGBA_ARGS))
    return None


def _gearboy_entry():
    """Build (path, args) for Gearboy."""
    path = _find_binary("gearboy")
    if path:
        return (path, [])
    return None


def _retroarch_entry(core_name):
    """Build (path, args) for RetroArch, optionally with a core."""
    ra = _find_binary("retroarch")
    if not ra:
        return None
    if core_name:
        for d in RETROARCH_CORE_DIRS:
            core = os.path.join(d, f"{core_name}_libretro.so")
            if os.path.isfile(core):
                return (ra, ["-L", core])
        return None
    return (ra, [])


def _find_emulator(ext):
    """Find the emulator binary for a given ROM extension.

    Returns (cmd, args) tuple or None.
    """
    sys_key = EXT_TO_SYSTEM.get(ext)
    if not sys_key:
        return None

    options = EMULATOR_OPTIONS.get(sys_key, [])
    if not options:
        return None

    # Check user preference
    prefs = _load_emu_prefs()
    preferred = prefs.get(sys_key)

    # Try preferred emulator first
    if preferred:
        for name, entry_fn in options:
            if name == preferred:
                result = entry_fn()
                if result:
                    return result
                break

    # Fall back to first available
    for _name, entry_fn in options:
        result = entry_fn()
        if result:
            return result
    return None


def _emu_label_for_ext(ext):
    """Get the display name of the selected emulator for an extension."""
    sys_key = EXT_TO_SYSTEM.get(ext)
    if not sys_key:
        return "?"
    options = EMULATOR_OPTIONS.get(sys_key, [])
    prefs = _load_emu_prefs()
    preferred = prefs.get(sys_key)
    if preferred:
        for name, entry_fn in options:
            if name == preferred and entry_fn():
                return name
    for name, entry_fn in options:
        if entry_fn():
            return name
    return "?"


def _launch_env():
    """Build environment dict with SDL controller mapping."""
    env = os.environ.copy()
    # Use our canonical mapping, replacing any existing one for this GUID
    guid = SDL_CONTROLLER_MAP.split(",")[0]
    existing = env.get("SDL_GAMECONTROLLERCONFIG", "")
    # Filter out any existing entries for this GUID
    lines = [l for l in existing.split("\n") if l.strip() and not l.startswith(guid)]
    lines.insert(0, SDL_CONTROLLER_MAP)
    env["SDL_GAMECONTROLLERCONFIG"] = "\n".join(lines)
    return env


def _find_binary(name):
    """Find an executable by name."""
    # Check local emulators directory first (flat or nested)
    local = os.path.expanduser(f"~/emulators/{name}")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    nested = os.path.expanduser(f"~/emulators/{name}/{name}")
    if os.path.isfile(nested) and os.access(nested, os.X_OK):
        return nested
    # Check /usr/games (Debian installs games there)
    usr_games = f"/usr/games/{name}"
    if os.path.isfile(usr_games) and os.access(usr_games, os.X_OK):
        return usr_games
    # Fall back to system PATH
    try:
        result = subprocess.run(["which", name], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


def _scan_roms():
    """Scan ROM directories and return {system: [(name, path), ...]}."""
    systems = {}
    for rom_dir in ROM_DIRS:
        if not os.path.isdir(rom_dir):
            continue
        for entry in sorted(os.listdir(rom_dir)):
            sys_path = os.path.join(rom_dir, entry)
            if os.path.isdir(sys_path):
                roms = []
                try:
                    for f in sorted(os.listdir(sys_path)):
                        _, ext = os.path.splitext(f)
                        if ext.lower() in ROM_EXTENSIONS:
                            roms.append((f, os.path.join(sys_path, f)))
                except PermissionError:
                    continue
                if roms:
                    key = entry
                    if key in systems:
                        systems[key].extend(roms)
                    else:
                        systems[key] = roms
            else:
                # ROM files directly in the base directory
                _, ext = os.path.splitext(entry)
                if ext.lower() in ROM_EXTENSIONS:
                    key = "(unsorted)"
                    if key not in systems:
                        systems[key] = []
                    systems[key].append((entry, sys_path))
    return systems


def _emulator_config_menu(scr, js):
    """Show emulator preference menu for each system."""
    hdr = curses.color_pair(C_HEADER) | curses.A_BOLD
    val = curses.color_pair(C_ITEM) | curses.A_BOLD
    dim = curses.color_pair(C_DIM)
    sel_attr = curses.color_pair(C_SEL) | curses.A_BOLD
    cat_attr = curses.color_pair(C_CAT) | curses.A_BOLD
    warn_attr = curses.color_pair(tui.C_WARN) | curses.A_BOLD

    prefs = _load_emu_prefs()
    sys_keys = sorted(EMULATOR_OPTIONS.keys())
    sel = 0
    message = ""
    msg_time = 0

    while True:
        h, w = scr.getmaxyx()
        scr.erase()
        tui.put(scr, 0, 1, "EMULATOR CONFIG", w - 2, hdr)

        for i, sys_key in enumerate(sys_keys):
            options = EMULATOR_OPTIONS[sys_key]
            current = prefs.get(sys_key)
            # Find active emulator name
            active = None
            if current:
                for name, fn in options:
                    if name == current:
                        active = name
                        break
            if not active:
                for name, fn in options:
                    if fn():
                        active = name
                        break
            active = active or "none"

            available = [n for n, fn in options if fn()]
            label = f"  {sys_key.upper():<8} {active}"
            if len(available) <= 1:
                label += " (only option)"
            attr = sel_attr if i == sel else val
            marker = "▸" if i == sel else " "
            tui.put(scr, i + 2, 1, f"{marker}{label}", w - 2, attr)

        if message and time.time() - msg_time < 3:
            tui.put(scr, h - 2, 2, message, w - 4, warn_attr)

        bar = " ↑↓ Select │ A/→ Cycle │ B Back "
        tui.put(scr, h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue

        if key == ord("q") or key == ord("b") or gp == "back":
            break
        elif key == curses.KEY_UP or key == ord("k"):
            sel = max(0, sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            sel = min(len(sys_keys) - 1, sel + 1)
        elif key in (curses.KEY_ENTER, 10, 13, curses.KEY_RIGHT, ord("a")) or gp in ("enter", "right"):
            sys_key = sys_keys[sel]
            options = EMULATOR_OPTIONS[sys_key]
            available = [(n, fn) for n, fn in options if fn()]
            if len(available) <= 1:
                message = f"No alternatives for {sys_key.upper()}"
                msg_time = time.time()
                continue
            current = prefs.get(sys_key, available[0][0])
            # Cycle to next
            names = [n for n, _ in available]
            try:
                idx = names.index(current)
                nxt = names[(idx + 1) % len(names)]
            except ValueError:
                nxt = names[0]
            prefs[sys_key] = nxt
            _save_emu_prefs(prefs)
            message = f"{sys_key.upper()} → {nxt}"
            msg_time = time.time()


def run_romlauncher(scr):
    """ROM launcher — scan directories, select, and launch with emulator."""
    js = open_gamepad()
    scr.timeout(100)

    hdr = curses.color_pair(C_HEADER) | curses.A_BOLD
    val = curses.color_pair(C_ITEM) | curses.A_BOLD
    dim = curses.color_pair(C_DIM)
    brd = curses.color_pair(C_BORDER)
    cat_attr = curses.color_pair(C_CAT) | curses.A_BOLD
    sel_attr = curses.color_pair(C_SEL) | curses.A_BOLD
    status_attr = curses.color_pair(C_STATUS) | curses.A_BOLD
    warn_attr = curses.color_pair(tui.C_WARN) | curses.A_BOLD

    systems = _scan_roms()
    system_names = sorted(systems.keys())

    # State: browsing systems or ROMs inside a system
    in_system = False
    sys_sel = 0
    rom_sel = 0
    sys_scroll = 0
    rom_scroll = 0
    message = ""
    msg_time = 0

    while True:
        h, w = scr.getmaxyx()
        scr.erase()

        # Header
        if in_system and system_names:
            sname = system_names[sys_sel]
            title = f"ROM LAUNCHER: {sname.upper()}"
            count_str = f"{len(systems[sname])} ROMs"
        else:
            title = "ROM LAUNCHER"
            count_str = f"{len(system_names)} systems"
        tui.put(scr, 0, 1, title, w - 2, hdr)
        tui.put(scr, 0, w - 1 - len(count_str), count_str, len(count_str), val)

        view_h = h - 3

        if not system_names:
            msg = "No ROMs found"
            dirs_str = "  Searched: " + ", ".join(ROM_DIRS)
            tui.put(scr, 3, 4, msg, w - 8, dim)
            tui.put(scr, 5, 2, dirs_str, w - 4, dim)
        elif not in_system:
            # System list
            sys_sel = min(sys_sel, max(0, len(system_names) - 1))
            if sys_sel < sys_scroll:
                sys_scroll = sys_sel
            if sys_sel >= sys_scroll + view_h:
                sys_scroll = sys_sel - view_h + 1

            for i in range(view_h):
                idx = sys_scroll + i
                if idx >= len(system_names):
                    break
                sname = system_names[idx]
                rom_count = len(systems[sname])
                line = f"  {sname:<30} {rom_count} ROM{'s' if rom_count != 1 else ''}"
                if idx == sys_sel:
                    marker = "▸"
                    attr = sel_attr
                else:
                    marker = " "
                    attr = val
                tui.put(scr, i + 1, 1, f"{marker}{line}", w - 2, attr)
        else:
            # ROM list inside a system
            sname = system_names[sys_sel]
            roms = systems[sname]
            rom_sel = min(rom_sel, max(0, len(roms) - 1))
            if rom_sel < rom_scroll:
                rom_scroll = rom_sel
            if rom_sel >= rom_scroll + view_h:
                rom_scroll = rom_sel - view_h + 1

            for i in range(view_h):
                idx = rom_scroll + i
                if idx >= len(roms):
                    break
                fname, fpath = roms[idx]
                _, ext = os.path.splitext(fname)
                emu = _emu_label_for_ext(ext.lower())
                line = f"  {fname:<50} [{emu}]"
                if idx == rom_sel:
                    marker = "▸"
                    attr = sel_attr
                else:
                    marker = " "
                    attr = val
                tui.put(scr, i + 1, 1, f"{marker}{line}", w - 2, attr)

        # Transient message
        if message and time.time() - msg_time < 3:
            tui.put(scr, h - 2, 2, message, w - 4, warn_attr)

        # Footer
        if in_system:
            bar = " ↑↓ Select │ A Launch │ B Back │ X Refresh │ Y Emulator "
        else:
            bar = " ↑↓ Select │ A Open │ B Quit │ X Refresh │ Y Emulator "
        tui.put(scr, h - 1, 0, bar.center(w), w, curses.color_pair(C_FOOTER))
        scr.refresh()

        # -- Input --
        key, gp = _tui_input_loop(scr, js)
        if key == -1 and gp is None:
            continue

        if key == ord("q") or key == ord("Q") or gp == "back":
            if in_system:
                in_system = False
                rom_sel = 0
                rom_scroll = 0
            else:
                break
        elif key == curses.KEY_UP or key == ord("k"):
            if in_system:
                rom_sel = max(0, rom_sel - 1)
            else:
                sys_sel = max(0, sys_sel - 1)
        elif key == curses.KEY_DOWN or key == ord("j"):
            if in_system:
                sname = system_names[sys_sel]
                rom_sel = min(len(systems[sname]) - 1, rom_sel + 1)
            else:
                sys_sel = min(len(system_names) - 1, sys_sel + 1)
        elif gp == "refresh" or key == ord("x"):
            systems = _scan_roms()
            system_names = sorted(systems.keys())
            sys_sel = 0
            rom_sel = 0
            in_system = False
        elif key == ord("y"):
            _emulator_config_menu(scr, js)
            read_gamepad(js)
            curses.flushinp()
            _gp_set_cooldown()
        elif key in (curses.KEY_ENTER, 10, 13) or gp == "enter" or key == ord("a"):
            if not system_names:
                continue
            if not in_system:
                in_system = True
                rom_sel = 0
                rom_scroll = 0
            else:
                # Launch ROM
                sname = system_names[sys_sel]
                roms = systems[sname]
                if roms and rom_sel < len(roms):
                    fname, fpath = roms[rom_sel]
                    _, ext = os.path.splitext(fname)
                    emu = _find_emulator(ext.lower())
                    if not emu:
                        message = f"No emulator found for {ext}"
                        msg_time = time.time()
                    else:
                        emu_path, emu_args = emu
                        fpath_abs = os.path.abspath(fpath)
                        if js:
                            js.close()
                            js = None
                        try:
                            subprocess.Popen(
                                [emu_path] + emu_args + [fpath_abs],
                                cwd=os.path.dirname(fpath_abs),
                                env=_launch_env(),
                                stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                                start_new_session=True,
                            )
                            message = f"Launched {fname} - returning to menu"
                        except Exception as e:
                            message = f"Launch error: {e}"
                        msg_time = time.time()
                        # Draw the toast immediately before returning so the user sees it
                        h, w = scr.getmaxyx()
                        attr_ok = curses.color_pair(C_STATUS) | curses.A_BOLD
                        attr_err = curses.color_pair(C_DIM) | curses.A_BOLD
                        msg_line = h - 2
                        msg_x = max(1, (w - len(message)) // 2)
                        try:
                            scr.hline(msg_line, 1, ord(' '), w - 2)
                            scr.addstr(msg_line, msg_x, message[:w - 2],
                                       attr_ok if "Launched" in message else attr_err)
                            scr.refresh()
                        except curses.error:
                            pass
                        time.sleep(1.0)
                        return

    if js:
        js.close()


HANDLERS = {
    "_minesweeper": run_minesweeper,
    "_snake":       run_snake,
    "_tetris":      run_tetris,
    "_2048":        run_2048,
    "_romlauncher": run_romlauncher,
}
