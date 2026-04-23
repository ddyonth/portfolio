import re
import time
import tkinter as tk
from tkinter import ttk, messagebox
import oracledb

BG_COLOR = "#1e1e1e"
FG_COLOR = "#dcdcdc"
BTN_BG = "#2a2a2a"
BTN_BG_HOVER = "#3b3b3b"
CELL_BG = "#2a2a2a"
CELL_BORDER = "#444444"
HIGHLIGHT_COLOR = "#00bcd4"
SELECT_COLOR = "#ffe600"
FONT_MAIN = ("Consolas", 13)
RED_CHIP = "#ff3b3b"
YELLOW_CHIP = "#ffeb3b"

DB_CONFIG = {
    "user": "KA2206_12",
    "password": "KA2206_12",
    "dsn": "10.22.10.49/ORCL"
}

AUTO_REFRESH_MS = 2000
IDLE_CLOSE_SECONDS = 3 * 3600
MIN_WIDTH, MAX_WIDTH = 7, 10
MIN_HEIGHT, MAX_HEIGHT = 6, 8

active_sessions = {}

def read_dbms_output(cursor):
    out = ""
    line = cursor.var(str)
    status = cursor.var(int)
    while True:
        try:
            cursor.callproc("dbms_output.get_line", (line, status))
        except Exception:
            break
        if status.getvalue() != 0:
            break
        out += (line.getvalue() or "") + "\n"
    return out.strip()


def make_connection():
    return oracledb.connect(user=DB_CONFIG["user"],
                            password=DB_CONFIG["password"],
                            dsn=DB_CONFIG["dsn"])

class ScreenManager: #переключение экранов
    def __init__(self, root):
        self.root = root
        self.screens = {}

    def add(self, name, frame):

        old = self.screens.get(name)
        if old:
            try:
                old.destroy()
            except Exception:
                pass
        self.screens[name] = frame

    def show(self, name):

        for k, f in list(self.screens.items()):
            try:
                f.pack_forget()
            except Exception:
                pass
        frame = self.screens.get(name)
        if frame:
            frame.pack(fill="both", expand=True)

class GameBoardWindow(tk.Frame):
    def __init__(self, parent, manager, conn, game_id, logged_player_name, preferred_color=None):
        super().__init__(parent, bg=BG_COLOR)
        self.parent = parent
        self.manager = manager
        self.conn = conn
        self.cursor = conn.cursor()
        self.game_id = game_id
        self.logged_player_name = logged_player_name
        self.preferred_color = preferred_color

        if active_sessions.get(logged_player_name):
            messagebox.showwarning("Внимание", "У этого пользователя уже открыта игровая сессия.")
            raise RuntimeError("session_exists")

        active_sessions[logged_player_name] = True

        self.cell_size = 64
        self.preview_tag = "preview"
        self.win_tag = "win"
        self.hint_tag = "hint"

        self.auto_refresh_job = None
        self.timer_job = None
        self.timer_seconds = 60
        self.timer_enabled = False
        self.timer_remaining = None
        self.timer_owner_id = None
        self.result_shown = False
        self.last_move_count = 0
        self.last_activity_time = time.time()
        self.selected_column = None

        top = tk.Frame(self, bg=BG_COLOR)
        top.pack(fill="x", padx=6, pady=4)
        self.lbl_logged = tk.Label(top, text=f"Вход: {self.logged_player_name}", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_logged.pack(side="left")
        self.lbl_turn = tk.Label(top, text="", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_turn.pack(side="right")
        self.lbl_timer = tk.Label(top, text="", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_timer.pack(side="right", padx=(0, 10))

        q = "SELECT width, height, timer_enabled FROM Game_history WHERE id_game = :g"
        self.cursor.execute(q, [self.game_id])
        row = self.cursor.fetchone()
        if not row:
            messagebox.showerror("Ошибка", "Игра не найдена в БД")
            self.cleanup_and_close()
            return

        self.width, self.height, tflag = row
        self.timer_enabled = (tflag == 'Y')

        self.board_frame = tk.Frame(self, bg=BG_COLOR)
        self.board_frame.pack(padx=10, pady=8)

        self.cells = []
        for r in range(self.height):
            row_widgets = []
            for c in range(self.width):
                cv = tk.Canvas(self.board_frame, width=self.cell_size, height=self.cell_size, bg=CELL_BG, highlightthickness=1, highlightbackground=CELL_BORDER)
                cv.grid(row=r, column=c, padx=2, pady=2)
                cv.bind("<Enter>", lambda e, col=c: self.on_column_enter(col))
                cv.bind("<Leave>", lambda e, col=c: self.on_column_leave(col))
                cv.bind("<Button-1>", lambda e, col=c: self.on_click(col + 1))
                row_widgets.append(cv)
            self.cells.append(row_widgets)

        bottom = tk.Frame(self, bg=BG_COLOR)
        bottom.pack(pady=6)

        self.btn_hint = tk.Button(bottom, text="Победный ряд", command=self.show_hint)
        self._style_button_local(self.btn_hint)
        self.btn_hint.pack(side="left", padx=4)
        self.btn_rematch = tk.Button(bottom, text="Реванш", state="disabled", command=self.do_rematch)
        self._style_button_local(self.btn_rematch)
        self.btn_rematch.pack(side="left", padx=4)
        btn_back = tk.Button(bottom, text="Назад", command=self.on_back)
        self._style_button_local(btn_back)
        btn_back.pack(side="right", padx=4)
        self.bind_all("<Key>", self.on_key)
        self.player_colors = {}
        self.load_player_tokens()

        if self.preferred_color:
            try:
                self.apply_preferred_color()
            except Exception:
                pass

        self.refresh_board(initial=True)
        self.schedule_auto_refresh()

        if self.timer_enabled:
            self.timer_remaining = self.timer_seconds
            self.timer_owner_id = None
            self._tick_timer()

    def _style_button_local(self, btn):
        try:
            btn.configure(
                bg=BTN_BG,
                fg=FG_COLOR,
                activebackground=BTN_BG_HOVER,
                activeforeground=FG_COLOR,
                font=FONT_MAIN,
                bd=1,
                relief="solid",
                highlightthickness=0
            )
        except Exception:
            pass

    def load_player_tokens(self):
        try:
            q = "SELECT id_player, token FROM Current_game WHERE id_game = :g"
            self.cursor.execute(q, [self.game_id])
            self.player_colors = {}
            for pid, token in self.cursor.fetchall():
                if token and token.upper().startswith("Y"):
                    self.player_colors[pid] = "YELLOW"
                else:
                    self.player_colors[pid] = "RED"
        except Exception:
            self.player_colors = {}

    def apply_preferred_color(self): #применили выбранный цвет
        if not self.preferred_color:
            return
        pref = self.preferred_color.upper()
        self.cursor.execute("SELECT id_player FROM Players WHERE LOWER(name)=LOWER(:n)", [self.logged_player_name])
        row = self.cursor.fetchone()
        if not row:
            return
        my_id = row[0]
        self.cursor.execute("SELECT id_player, token FROM Current_game WHERE id_game = :g", [self.game_id])
        rows = self.cursor.fetchall()
        if not rows or len(rows) < 2:
            return
        mapping = {r[0]: (r[1] or "RED") for r in rows}
        my_token = (mapping.get(my_id) or "RED").upper()
        want_token = "YELLOW" if pref.startswith("Y") else "RED"
        if (my_token.startswith("Y") and want_token.startswith("Y")) or (my_token.startswith("R") and want_token.startswith("R")):
            return
        try:
            opponent_id = None
            for pid in mapping:
                if pid != my_id:
                    opponent_id = pid
            if opponent_id is None:
                return

            if want_token.startswith("Y"):
                self.cursor.execute("UPDATE Current_game SET token = CASE WHEN id_player = :me THEN 'YELLOW' WHEN id_player = :op THEN 'RED' ELSE token END WHERE id_game = :g", [my_id, opponent_id, self.game_id])
            else:
                self.cursor.execute("UPDATE Current_game SET token = CASE WHEN id_player = :me THEN 'RED' WHEN id_player = :op THEN 'YELLOW' ELSE token END WHERE id_game = :g", [my_id, opponent_id, self.game_id])
            self.conn.commit()
            self.load_player_tokens()
        except Exception:
            try:
                self.conn.rollback()
            except Exception:
                pass

    def on_click(self, column): #клик по столбцу
        if not self.is_active_game():
            return
        try:
            self.cursor.execute("SELECT current_player_id FROM Game_history WHERE id_game = :g", [self.game_id])
            row = self.cursor.fetchone()
            if not row:
                messagebox.showerror("Ошибка", "Не удалось определить текущего игрока")
                return
            current_id = row[0]
        except Exception as e:
            messagebox.showerror("Ошибка БД", str(e))
            return

        try:
            self.cursor.callproc("connect_four.make_move", [self.game_id, current_id, column])
            self.conn.commit()
            out = read_dbms_output(self.cursor)
            self.refresh_board()
            self.reset_timer_for_current_player()
            m = re.search(r'WIN_CELLS\s*=\s*([0-9,;]+)', out)
            if m:
                cells_str = m.group(1)
                self.highlight_win_cells(cells_str)
        except Exception as e:
            messagebox.showerror("Ошибка хода", str(e))

    def refresh_board(self, initial=False):
        for r in range(self.height):
            for c in range(self.width):
                self.cells[r][c].delete("all")
                self.cells[r][c].create_rectangle(0, 0, self.cell_size, self.cell_size, fill=CELL_BG, outline=CELL_BORDER)

        q = """
            SELECT row_pos, col_pos, id_player
            FROM Moves
            WHERE id_game = :g AND skip_flag='N' AND row_pos IS NOT NULL
        """
        try:
            self.cursor.execute(q, [self.game_id])
            moves = self.cursor.fetchall()
        except Exception:
            moves = []

        for row_pos, col_pos, pid in moves:
            if row_pos is None or col_pos is None:
                continue
            display_row = int(row_pos) - 1
            display_col = int(col_pos) - 1
            token = self.player_colors.get(pid, "RED")
            color = RED_CHIP if token.upper().startswith("R") else YELLOW_CHIP
            x0 = 6; y0 = 6; x1 = self.cell_size - 6; y1 = self.cell_size - 6
            if 0 <= display_row < self.height and 0 <= display_col < self.width:
                self.cells[display_row][display_col].create_oval(x0, y0, x1, y1, fill=color, outline="#000000")

        self.cursor.execute("SELECT current_player_id, result FROM Game_history WHERE id_game = :g", [self.game_id])
        row = self.cursor.fetchone()
        curr_id, result = (row[0], row[1]) if row else (None, None)
        current_name = "-"
        if curr_id:
            self.cursor.execute("SELECT name FROM Players WHERE id_player = :p", [curr_id])
            r = self.cursor.fetchone()
            current_name = r[0] if r else str(curr_id)
        self.lbl_turn.config(text=f"Сейчас ход: {current_name}")

        self.cursor.execute("SELECT COUNT(*) FROM Moves WHERE id_game = :g", [self.game_id])
        cnt = self.cursor.fetchone()[0]
        if initial:
            self.last_move_count = cnt
            self.last_activity_time = time.time()
        else:
            if cnt != self.last_move_count:
                self.last_move_count = cnt
                self.last_activity_time = time.time()

        if result and result != "В процессе":
            if self.result_shown:
                return
            self.result_shown = True

            if self.auto_refresh_job:
                try:
                    self.after_cancel(self.auto_refresh_job)
                except Exception:
                    pass
                self.auto_refresh_job = None

            if self.timer_job:
                try:
                    self.after_cancel(self.timer_job)
                except Exception:
                    pass
                self.timer_job = None
                self.lbl_timer.config(text="")

            if result == "Ничья — крестики-нолики":
                self.launch_tic_tac_toe()
            else:
                out = read_dbms_output(self.cursor)
                messagebox.showinfo("Итог", out if out else result)
                self.btn_hint.config(state="disabled")
                self.btn_rematch.config(state="normal")

            return

        self.load_player_tokens()
        if self.timer_enabled:
            try:
                self.cursor.execute("SELECT current_player_id FROM Game_history WHERE id_game = :g", [self.game_id])
                r = self.cursor.fetchone()
                curr_pid = r[0] if r else None
                if curr_pid != self.timer_owner_id:
                    self.timer_owner_id = curr_pid
                    self.timer_remaining = self.timer_seconds
                    if self.timer_job:
                        try: self.after_cancel(self.timer_job)
                        except Exception: pass
                        self.timer_job = None
                    self._tick_timer()
            except Exception:
                pass

    def schedule_auto_refresh(self):
        if self.auto_refresh_job:
            try: self.after_cancel(self.auto_refresh_job)
            except Exception: pass
        self.auto_refresh_job = self.after(AUTO_REFRESH_MS, self.auto_refresh_tick)

    def auto_refresh_tick(self):
        try:
            try:
                self.cursor.callproc("connect_four.close_idle_games", [])
                self.conn.commit()
            except Exception:
                pass

            self.load_player_tokens()
            self.refresh_board()

            elapsed = time.time() - self.last_activity_time
            if elapsed >= IDLE_CLOSE_SECONDS and self.is_active_game():
                try:
                    self.cursor.execute("UPDATE Game_history SET end_time = SYSDATE, result='Прервано (длительное ожидание)', winner_id = NULL WHERE id_game = :g AND result = 'В процессе'", [self.game_id])
                    self.conn.commit()
                except Exception:
                    pass
                if not self.result_shown:
                    self.result_shown = True
                    messagebox.showinfo("Итог", "Игра автоматически завершена из-за длительного простоя.")

                self.refresh_board()
                if self.auto_refresh_job:
                    try: self.after_cancel(self.auto_refresh_job)
                    except: pass
                    self.auto_refresh_job = None
                return

            self.schedule_auto_refresh()
        except Exception as e:
            print("Auto refresh error:", e)
            self.schedule_auto_refresh()

    def is_active_game(self):
        try:
            self.cursor.execute("SELECT result FROM Game_history WHERE id_game = :g", [self.game_id])
            row = self.cursor.fetchone()
            return bool(row and row[0] == "В процессе")
        except Exception:
            return False

    def on_column_enter(self, col): #подсветка
        try:
            self.cursor.execute(
                "SELECT COUNT(*) FROM Moves WHERE id_game = :g AND col_pos = :c AND skip_flag='N'",
                [self.game_id, col + 1]
            )
            cnt = self.cursor.fetchone()[0]
        except Exception:
            cnt = 0

        for r in range(self.height):
            cell = self.cells[r][col]
            cell.delete("hover")
            cell.delete(self.preview_tag)

        if cnt >= self.height:
            return

        for r in range(self.height):
            cell = self.cells[r][col]
            cell.create_rectangle(
                2, 2, self.cell_size - 2, self.cell_size - 2,
                outline=HIGHLIGHT_COLOR, width=3, tags="hover"
            )
        try:
            landing_row = self.height - cnt - 1
            cell = self.cells[landing_row][col]

            self.cursor.execute("SELECT current_player_id FROM Game_history WHERE id_game = :g", [self.game_id])
            r = self.cursor.fetchone()
            curr_pid = r[0] if r else None
            token = self.player_colors.get(curr_pid, "RED")
            color = RED_CHIP if token.upper().startswith("R") else YELLOW_CHIP

            cell.delete(self.preview_tag)

            cell.create_oval(
                6, 6, self.cell_size - 6, self.cell_size - 6,
                fill=color,
                outline="#000000",
                stipple="gray12",
                tags=self.preview_tag
            )
        except Exception:
            pass

    def on_column_leave(self, col): #убирает подсветку, мышь
        for r in range(self.height):
            cell = self.cells[r][col]
            cell.delete("hover")
            cell.delete(self.preview_tag)

    def highlight_column(self): #подсетка колонны
        for r in range(self.height):
            for c in range(self.width):
                self.cells[r][c].delete("highlight")
        if self.selected_column is None:
            return
        col = self.selected_column
        for r in range(self.height):
            cell = self.cells[r][col]
            cell.create_rectangle(
                2, 2, self.cell_size - 2, self.cell_size - 2,
                outline=SELECT_COLOR,
                width=3,
                tags="highlight"
            )

    def preview_selected_column(self):
        for r in range(self.height):
            for c in range(self.width):
                self.cells[r][c].delete("hover")
                self.cells[r][c].delete(self.preview_tag)
        if self.selected_column is None:
            return
        self.on_column_enter(self.selected_column)

    def highlight_win_cells(self, cells_str): #подсветка победы
        try:
            parts = cells_str.split(";")
            for p in parts:
                r, c = map(int, p.split(","))
                rr = r - 1; cc = c - 1
                if 0 <= rr < self.height and 0 <= cc < self.width:
                    cv = self.cells[rr][cc]
                    cv.create_rectangle(2, 2, self.cell_size - 2, self.cell_size - 2, outline="green", width=4, tags=self.win_tag)
        except Exception:
            pass

    def show_hint(self): #победный ряд
        try:
            self.cursor.execute("SELECT current_player_id FROM Game_history WHERE id_game = :g", [self.game_id])
            row = self.cursor.fetchone()
            if not row or row[0] is None:
                messagebox.showinfo("Подсказка", "Ход не определён.")
                return
            curr_id = row[0]

            board = {}
            self.cursor.execute("SELECT row_pos, col_pos, id_player FROM Moves WHERE id_game = :g AND skip_flag='N' AND row_pos IS NOT NULL", [self.game_id])
            rows = self.cursor.fetchall()
            for rp, cp, pid in rows:
                board[(int(rp), int(cp))] = pid

            w = self.width
            h = self.height

            def is_win_after_place(r, c, player_id): #проверка выгрышной позиции
                dirs = [(0,1),(1,0),(1,1),(1,-1)]
                for dr, dc in dirs:
                    cnt = 1
                    cells = [(r,c)]
                    rr, cc = r+dr, c+dc
                    while 1 <= rr <= h and 1 <= cc <= w and board.get((rr,cc)) == player_id:
                        cells.append((rr,cc)); cnt += 1
                        rr += dr; cc += dc
                    rr, cc = r-dr, c-dc
                    while 1 <= rr <= h and 1 <= cc <= w and board.get((rr,cc)) == player_id:
                        cells.insert(0,(rr,cc)); cnt += 1
                        rr -= dr; cc -= dc
                    if cnt >= 4:
                        return True, cells[:4] if len(cells) >= 4 else cells
                return False, None

            found = False
            win_cells = None
            for col in range(1, w+1):
                cnt = sum(1 for (rr,cc) in board.keys() if cc == col)
                if cnt >= h:
                    continue
                row_to = h - cnt
                board[(row_to, col)] = curr_id
                ok, cells = is_win_after_place(row_to, col, curr_id)
                board.pop((row_to, col), None)
                if ok:
                    found = True
                    win_cells = cells
                    break

            if not found:
                messagebox.showinfo("Подсказка", "Выигрышного хода нет.")
                return

            s = ";".join(f"{r},{c}" for (r,c) in win_cells)
            self.highlight_win_cells(s)
        except Exception as e:
            messagebox.showerror("Ошибка подсказки", str(e))

    def _tick_timer(self): #отсчет
        if not self.is_active_game():
            self.lbl_timer.config(text="")
            return

        try:
            self.cursor.execute("SELECT current_player_id FROM Game_history WHERE id_game = :g", [self.game_id])
            row = self.cursor.fetchone()
            curr_pid = row[0] if row else None
        except Exception:
            curr_pid = None

        if curr_pid != self.timer_owner_id:
            self.timer_owner_id = curr_pid
            self.timer_remaining = self.timer_seconds

        if self.timer_remaining is None:
            self.timer_remaining = self.timer_seconds

        if curr_pid:
            try:
                self.cursor.execute("SELECT name FROM Players WHERE id_player = :p", [curr_pid])
                r = self.cursor.fetchone()
                nm = r[0] if r else str(curr_pid)
            except Exception:
                nm = str(curr_pid)
            self.lbl_timer.config(text=f"{nm}: {self.timer_remaining}s")
        else:
            self.lbl_timer.config(text="")

        if self.timer_remaining <= 0:
            try:
                if curr_pid:
                    self.cursor.callproc("connect_four.skip_move", [self.game_id, curr_pid])
                    self.conn.commit()
                    out = read_dbms_output(self.cursor)
                    self.refresh_board()
                    if out and re.search(r'Побед|Ничья|Тех', out, re.IGNORECASE):
                        if not self.result_shown:
                            messagebox.showinfo("Итог", out)
                            self.result_shown = True

                self.timer_remaining = self.timer_seconds
                try:
                    self.cursor.execute("SELECT current_player_id FROM Game_history WHERE id_game = :g", [self.game_id])
                    row = self.cursor.fetchone()
                    self.timer_owner_id = row[0] if row else None
                except Exception:
                    self.timer_owner_id = None
            except Exception as e:
                print("skip_move error:", e)
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                self.timer_remaining = self.timer_seconds
        else:
            self.timer_remaining -= 1

        if self.is_active_game():
            if self.timer_job:
                try: self.after_cancel(self.timer_job)
                except Exception: pass
            self.timer_job = self.after(1000, self._tick_timer)
        else:
            self.lbl_timer.config(text="")
            self.timer_job = None

    def reset_timer_for_current_player(self): #сброс таймера для текущ. игрока
        try:
            self.cursor.execute("SELECT current_player_id FROM Game_history WHERE id_game = :g", [self.game_id])
            row = self.cursor.fetchone()
            curr_pid = row[0] if row else None
            self.timer_owner_id = curr_pid
            self.timer_remaining = self.timer_seconds
            if self.timer_job:
                try: self.after_cancel(self.timer_job)
                except Exception: pass
                self.timer_job = None
            if self.timer_enabled:
                self._tick_timer()
        except Exception:
            pass

    def on_key(self, event):#клавиши
        key = event.keysym

        if event.char and event.char.isdigit():
            num = int(event.char)
            if num == 0:
                col = 10
            else:
                col = num

            if 1 <= col <= self.width:
                self.selected_column = col - 1
                self.highlight_column()
                self.preview_selected_column()
            return

        if key == "Left":
            if self.selected_column is None:
                self.selected_column = 0
            else:
                self.selected_column = (self.selected_column - 1) % self.width
            self.highlight_column()
            self.preview_selected_column()
            return

        if key == "Right":
            if self.selected_column is None:
                self.selected_column = 0
            else:
                self.selected_column = (self.selected_column + 1) % self.width
            self.highlight_column()
            self.preview_selected_column()
            return

        if key == "Return":
            if self.selected_column is not None:
                self.on_click(self.selected_column + 1)
            return

        if key.lower() == 'r':
            if self.btn_rematch['state'] == 'normal':
                self.do_rematch()

    def do_rematch(self): #реванш
        self.btn_rematch.config(state="disabled")
        try:
            self.cursor.callproc("connect_four.rematch", [self.game_id])
            self.conn.commit()
            out = read_dbms_output(self.cursor)
            m = re.search(r'NEW_GAME_ID\s*=\s*(\d+)', out)
            if m:
                new_id = int(m.group(1))
            else:
                q = """
                    SELECT gh.id_game
                    FROM Game_history gh
                    JOIN Current_game c1 ON c1.id_game = gh.id_game
                    JOIN Current_game c2 ON c2.id_game = gh.id_game AND c2.id_player <> c1.id_player
                    WHERE gh.result = 'В процессе'
                      AND c1.id_player IN (SELECT id_player FROM Current_game WHERE id_game = :g)
                      AND c2.id_player IN (SELECT id_player FROM Current_game WHERE id_game = :g)
                    ORDER BY gh.start_time DESC
                    FETCH FIRST 1 ROWS ONLY
                """
                self.cursor.execute(q, [self.game_id])
                r = self.cursor.fetchone()
                new_id = r[0] if r else None

            if not new_id:
                messagebox.showerror("Ошибка", "Не удалось найти ID новой игры.")
                self.btn_rematch.config(state="normal")
                return

            active_sessions.pop(self.logged_player_name, None)

            new_board = GameBoardWindow(self.parent, self.manager, self.conn, new_id, self.logged_player_name, preferred_color=self.preferred_color)

            self.manager.add("board", new_board)
            self.manager.show("board")

            try:
                self.destroy()
            except Exception:
                pass

        except Exception as e:
            messagebox.showerror("Ошибка реванша", str(e))
            self.btn_rematch.config(state="normal")

    def on_back(self):
        self.cleanup_and_close()
        self.manager.show("menu")

    def launch_tic_tac_toe(self): #крестики-нолики
        try:
            import threading, time

            self.cursor.execute(
                "SELECT id_player FROM Players WHERE LOWER(name)=LOWER(:n)",
                [self.logged_player_name]
            )
            row = self.cursor.fetchone()
            if not row:
                raise Exception("Игрок не найден в таблице Players.")
            my_id = row[0]

            game_id = self.game_id

            resolver_conn = make_connection()
            resolver_cur = resolver_conn.cursor()

            def run_resolver():
                try:
                    resolver_cur.callproc("connect_four.tic_tac_toe_resolve", [game_id])
                    resolver_conn.commit()
                except Exception as e:
                    print("TTT resolver error:", e)
                finally:
                    try:
                        resolver_cur.close()
                    except:
                        pass
                    try:
                        resolver_conn.close()
                    except:
                        pass

            threading.Thread(target=run_resolver, daemon=True).start()

            deadline = time.time() + 5.0
            symbol_map = None
            while time.time() < deadline:
                self.cursor.execute("""
                    SELECT id_player, symbol
                    FROM TicTacToe_Sessions
                    WHERE id_game = :g
                """, [game_id])
                rows = self.cursor.fetchall()
                if len(rows) >= 2:
                    symbol_map = {pid: sym for pid, sym in rows}
                    break
                time.sleep(0.1)

            if not symbol_map or my_id not in symbol_map:
                raise Exception("Oracle не назначил символы в TicTacToe_Sessions (проверь tic_tac_toe_resolve).")

            my_symbol = symbol_map[my_id]

            self.cursor.execute(
                "SELECT id_player FROM Current_game WHERE id_game = :g",
                [game_id]
            )
            players = [r[0] for r in self.cursor.fetchall()]
            if len(players) != 2:
                raise Exception("В Current_game нет двух игроков для этой игры.")
            opponent_id = players[0] if players[1] == my_id else players[1]
            opponent_symbol = symbol_map.get(opponent_id)

            if not opponent_symbol:
                self.cursor.execute("""
                    SELECT symbol
                    FROM TicTacToe_Sessions
                    WHERE id_game = :g AND id_player = :p
                """, [game_id, opponent_id])
                rr = self.cursor.fetchone()
                if not rr:
                    raise Exception("Не найден opponent_symbol в TicTacToe_Sessions.")
                opponent_symbol = rr[0]

            self.cleanup_and_close()

            ttt_window = TicTacToeWindow(
                self.parent, self.manager, self.conn,
                game_id, self.logged_player_name,
                my_id, my_symbol, opponent_id, opponent_symbol
            )
            self.manager.add("ttt", ttt_window)
            self.manager.show("ttt")

        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось запустить крестики-нолики:\n{e}")

    def cleanup_and_close(self): #завершение
        try:
            self.unbind_all("<Key>")
        except Exception:
            pass
        active_sessions.pop(self.logged_player_name, None)
        if self.timer_job:
            try: self.after_cancel(self.timer_job)
            except Exception: pass
            self.timer_job = None
        if self.auto_refresh_job:
            try: self.after_cancel(self.auto_refresh_job)
            except Exception: pass
            self.auto_refresh_job = None
        try:
            self.destroy()
        except Exception:
            pass

class TicTacToeWindow(tk.Frame):
    def __init__(self, parent, manager, conn, game_id, logged_player_name, my_id, my_symbol, opponent_id, opponent_symbol):
        super().__init__(parent, bg=BG_COLOR)
        self.parent = parent
        self.manager = manager
        self.conn = conn
        self.cursor = conn.cursor()
        self.game_id = game_id
        self.logged_player_name = logged_player_name
        self.my_id = my_id
        self.my_symbol = my_symbol
        self.opponent_id = opponent_id
        self.opponent_symbol = opponent_symbol

        try:
            self.parent.winfo_toplevel().title("Крестики-нолики")
        except Exception:
            pass

        self.board_size = 3
        self.cell_size = 100
        self.board = [[None for _ in range(3)] for _ in range(3)]
        self.game_over = False
        self.winning_cells = None
        self.lbl_title = tk.Label(self, text="Крестики-нолики", font=("Arial", 16, "bold"), bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_title.pack(pady=(10, 2))
        self.lbl_login = tk.Label(self, text=f"Вход: {self.logged_player_name}", font=("Arial", 10), bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_login.pack(pady=(0, 2))
        self.lbl_assign = tk.Label(self, text="", font=("Arial", 10), bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_assign.pack(pady=(0, 2))
        self.lbl_turn = tk.Label(self, text="", font=("Arial", 12, "bold"), bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_turn.pack(pady=(0, 8))

        self.canvas = tk.Canvas(
            self,
            width=self.board_size * self.cell_size,
            height=self.board_size * self.cell_size,
            bg=CELL_BG,
            highlightthickness=1,
            highlightbackground=CELL_BORDER
        )
        self.canvas.pack(pady=6)
        self.canvas.bind("<Button-1>", self.on_click)
        self.preview_tag = "ttt_preview"
        self.hover_cell = None
        self.canvas.bind("<Motion>", self.on_mouse_move)
        self.canvas.bind("<Leave>", self.on_mouse_leave)
        bottom = tk.Frame(self, bg=BG_COLOR)
        bottom.pack(pady=10)
        self.lbl_status = tk.Label(bottom, text="Кликните по клетке", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        self.lbl_status.pack()
        tk.Button(bottom, text="Назад", command=self.on_back, font=FONT_MAIN, bg=BTN_BG, fg=FG_COLOR).pack(pady=5)
        self.players_by_symbol = {}
        self._load_sessions_and_players()
        self._update_turn_label()
        self.draw_grid()
        self.refresh_board()

    def draw_grid(self):
        self.canvas.delete("all")
        for i in range(1, 3):
            self.canvas.create_line(i * self.cell_size, 0, i * self.cell_size, 3 * self.cell_size, fill=FG_COLOR, width=2)
            self.canvas.create_line(0, i * self.cell_size, 3 * self.cell_size, i * self.cell_size, fill=FG_COLOR, width=2)

    def refresh_board(self):
        self.draw_grid()
        self.board = [[None for _ in range(3)] for _ in range(3)]

        self.cursor.execute("""
            SELECT row_pos, col_pos, symbol
            FROM TicTacToe_Rounds
            WHERE id_game = :g
            ORDER BY move_number
        """, [self.game_id])

        for r, c, sym in self.cursor.fetchall():
            self.board[r - 1][c - 1] = sym
            x0 = (c - 1) * self.cell_size + 10
            y0 = (r - 1) * self.cell_size + 10
            x1 = c * self.cell_size - 10
            y1 = r * self.cell_size - 10
            if sym == 'X':
                self.canvas.create_line(x0, y0, x1, y1, fill="#ff3b3b", width=4)
                self.canvas.create_line(x0, y1, x1, y0, fill="#ff3b3b", width=4)
            else:
                self.canvas.create_oval(x0, y0, x1, y1, outline="#ffeb3b", width=4)

        if self.winning_cells:
            self._draw_win_highlight(self.winning_cells)
        else:
            self._clear_win_highlight()

    def _find_winning_cells(self):
        lines = [
            [(0, 0), (0, 1), (0, 2)],
            [(1, 0), (1, 1), (1, 2)],
            [(2, 0), (2, 1), (2, 2)],
            [(0, 0), (1, 0), (2, 0)],
            [(0, 1), (1, 1), (2, 1)],
            [(0, 2), (1, 2), (2, 2)],
            [(0, 0), (1, 1), (2, 2)],
            [(0, 2), (1, 1), (2, 0)],
        ]
        for cells in lines:
            a, b, c = cells
            s1 = self.board[a[0]][a[1]]
            s2 = self.board[b[0]][b[1]]
            s3 = self.board[c[0]][c[1]]
            if s1 is not None and s1 == s2 and s2 == s3:
                return cells
        return None

    def _clear_win_highlight(self):
        self.canvas.delete("ttt_win")

    def _draw_win_highlight(self, cells):
        self._clear_win_highlight()
        if not cells:
            return
        pad = 4
        for r, c in cells:
            x0 = c * self.cell_size + pad
            y0 = r * self.cell_size + pad
            x1 = (c + 1) * self.cell_size - pad
            y1 = (r + 1) * self.cell_size - pad
            self.canvas.create_rectangle(
                x0, y0, x1, y1,
                outline="green",
                width=5,
                tags="ttt_win"
            )

    def clear_preview(self):
        self.canvas.delete(self.preview_tag)

    def _get_current_turn_symbol(self) -> str:
        self.cursor.execute("SELECT COUNT(*) FROM TicTacToe_Rounds WHERE id_game = :g", [self.game_id])
        cnt = self.cursor.fetchone()[0]
        return 'X' if (cnt % 2 == 0) else 'O'

    def draw_preview(self, row: int, col: int):
        self.clear_preview()


        if self.game_over or self.board[row][col] is not None:
            return

        sym = self._get_current_turn_symbol()

        x0 = col * self.cell_size + 10
        y0 = row * self.cell_size + 10
        x1 = (col + 1) * self.cell_size - 10
        y1 = (row + 1) * self.cell_size - 10

        if sym == 'X':
            self.canvas.create_line(x0, y0, x1, y1, fill="#9e9e9e", width=3, dash=(6, 4), tags=self.preview_tag)
            self.canvas.create_line(x0, y1, x1, y0, fill="#9e9e9e", width=3, dash=(6, 4), tags=self.preview_tag)
        else:
            self.canvas.create_oval(x0, y0, x1, y1, outline="#9e9e9e", width=3, dash=(6, 4), tags=self.preview_tag)

    def on_mouse_move(self, event):
        col = event.x // self.cell_size
        row = event.y // self.cell_size

        if not (0 <= row < 3 and 0 <= col < 3):
            if self.hover_cell is not None:
                self.hover_cell = None
                self.clear_preview()
            return

        cell = (row, col)
        if cell != self.hover_cell:
            self.hover_cell = cell
            self.draw_preview(row, col)

    def on_mouse_leave(self, event):
        self.hover_cell = None
        self.clear_preview()

    def on_click(self, event):
        import time
        self.clear_preview()

        if self.game_over:
            return

        col = event.x // self.cell_size
        row = event.y // self.cell_size
        if not (0 <= row < 3 and 0 <= col < 3):
            return
        if self.board[row][col] is not None:
            return

        def wait_sessions_ready(timeout_sec=3.0):
            deadline = time.time() + timeout_sec
            while time.time() < deadline:
                self.cursor.execute("""
                    SELECT ts.symbol, ts.id_player, p.name
                    FROM TicTacToe_Sessions ts
                    JOIN Players p ON p.id_player = ts.id_player
                    WHERE ts.id_game = :g
                """, [self.game_id])
                rows = self.cursor.fetchall()
                m = {sym: {"id": pid, "name": name} for sym, pid, name in rows}
                if 'X' in m and 'O' in m:
                    self.players_by_symbol = m
                    self.lbl_assign.config(text=f"X: {m['X']['name']}    |    O: {m['O']['name']}")
                    return True
                time.sleep(0.05)

            self.cursor.execute("""
                SELECT ts.symbol, ts.id_player, p.name
                FROM TicTacToe_Sessions ts
                JOIN Players p ON p.id_player = ts.id_player
                WHERE ts.id_game = :g
            """, [self.game_id])
            rows = self.cursor.fetchall()
            self.players_by_symbol = {sym: {"id": pid, "name": name} for sym, pid, name in rows}
            return False

        try:
            self.cursor.execute("SELECT COUNT(*) FROM TicTacToe_Rounds WHERE id_game = :g", [self.game_id])
            cnt = self.cursor.fetchone()[0]

            if cnt == 0:
                wait_sessions_ready(timeout_sec=3.0)
            turn_symbol = 'X' if cnt % 2 == 0 else 'O'
            player = self.players_by_symbol.get(turn_symbol)
            if not player:
                wait_sessions_ready(timeout_sec=3.0)
                player = self.players_by_symbol.get(turn_symbol)
                if not player:
                    raise Exception("Не могу определить игрока для текущего символа (X/O).")

            turn_player_id = player["id"]
            try:
                self.cursor.callproc("connect_four.make_ttt_move", [
                    self.game_id, turn_player_id, row + 1, col + 1, turn_symbol
                ])
                self.conn.commit()

            except Exception as e:
                msg = str(e)
                if "ORA-20062" in msg:
                    wait_sessions_ready(timeout_sec=3.0)
                    self.cursor.execute("SELECT COUNT(*) FROM TicTacToe_Rounds WHERE id_game = :g", [self.game_id])
                    cnt2 = self.cursor.fetchone()[0]
                    turn_symbol2 = 'X' if cnt2 % 2 == 0 else 'O'

                    player2 = self.players_by_symbol.get(turn_symbol2)
                    if not player2:
                        raise Exception("После перераздачи не вижу X/O в TicTacToe_Sessions.")

                    self.cursor.callproc("connect_four.make_ttt_move", [
                        self.game_id, player2["id"], row + 1, col + 1, turn_symbol2
                    ])
                    self.conn.commit()
                else:
                    raise

            self.refresh_board()
            self.clear_preview()

            winner = self.check_winner()
            if winner is None:
                self._update_turn_label()
            else:
                self.handle_game_end(winner)

        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

    def _wait_for_sessions_ready(self, timeout_sec=3.0):
        import time
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            self.cursor.execute("""
                SELECT symbol, id_player
                FROM TicTacToe_Sessions
                WHERE id_game = :g
            """, [self.game_id])
            rows = self.cursor.fetchall()
            m = {sym: pid for sym, pid in rows}
            if 'X' in m and 'O' in m:
                self._load_sessions_and_players()
                return True
            time.sleep(0.05)
        self._load_sessions_and_players()
        return False

    def wait_for_opponent_move(self):
        if self.game_over:
            return
        self.cursor.execute("""
            SELECT row_pos, col_pos, symbol
            FROM TicTacToe_Rounds
            WHERE id_game = :g AND id_player = :p AND row_pos IS NOT NULL
        """, [self.game_id, self.opponent_id])
        moves = self.cursor.fetchall()
        for r, c, sym in moves:
            if self.board[r-1][c-1] is None:
                self.board[r-1][c-1] = sym
        self.refresh_board()
        winner = self.check_winner()
        if winner is not None:
            self.handle_game_end(winner)
        else:
            self.lbl_status.config(text="Ваш ход")

    def check_winner(self):
        self.cursor.execute("SELECT connect_four.ttt_check_winner(:g) FROM dual", [self.game_id])
        row = self.cursor.fetchone()
        return row[0] if row else None

    def handle_game_end(self, result):
        if result == -1:
            self.lbl_turn.config(text="Ничья! Новый раунд...")
            self.board = [[None for _ in range(3)] for _ in range(3)]
            self.canvas.delete("all")
            self.draw_grid()
            self.winning_cells = None
            self._clear_win_highlight()
            self._wait_for_sessions_ready(timeout_sec=3.0)
            self._update_turn_label()
            self.lbl_status.config(text="Новый раунд начат. Кликайте по клетке.")
            return

        self.game_over = True
        if result is None:
            return

        self.cursor.execute("SELECT name FROM Players WHERE id_player = :p", [result])
        name = (self.cursor.fetchone() or ["Игрок"])[0]
        self.winning_cells = self._find_winning_cells()
        self._draw_win_highlight(self.winning_cells)
        messagebox.showinfo("Крестики-нолики", f"Победил {name}!")
        self.on_back()

    def on_back(self):
        self.destroy()
        self.manager.show("menu")

    def _load_sessions_and_players(self):
        self.cursor.execute("""
            SELECT ts.symbol, ts.id_player, p.name
            FROM TicTacToe_Sessions ts
            JOIN Players p ON p.id_player = ts.id_player
            WHERE ts.id_game = :g
        """, [self.game_id])
        rows = self.cursor.fetchall()

        self.players_by_symbol = {}
        for sym, pid, name in rows:
            self.players_by_symbol[sym] = {"id": pid, "name": name}

        x = self.players_by_symbol.get('X')
        o = self.players_by_symbol.get('O')
        if x and o:
            self.lbl_assign.config(text=f"X: {x['name']}    |    O: {o['name']}")
        else:
            self.lbl_assign.config(text="X/O ещё не назначены Oracle")

    def _update_turn_label(self):
        self.cursor.execute("SELECT COUNT(*) FROM TicTacToe_Rounds WHERE id_game = :g", [self.game_id])
        cnt = self.cursor.fetchone()[0]

        turn_symbol = 'X' if cnt % 2 == 0 else 'O'
        player = self.players_by_symbol.get(turn_symbol)

        if player:
            self.lbl_turn.config(text=f"Сейчас ход: {player['name']} ({turn_symbol})")
        else:
            self._load_sessions_and_players()
            player = self.players_by_symbol.get(turn_symbol)
            if player:
                self.lbl_turn.config(text=f"Сейчас ход: {player['name']} ({turn_symbol})")
            else:
                self.lbl_turn.config(text=f"Сейчас ход: {turn_symbol}")

class ConnectFourApp:
    def __init__(self, root):
        self.root = root
        self.root.state("zoomed")
        self.root.minsize(900, 600)
        self.root.title("Connect Four — Client")
        self.root.configure(bg=BG_COLOR)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            try:
                style.theme_use("classic")
            except Exception:
                pass
        style.configure(".", background=BG_COLOR, foreground=FG_COLOR, font=FONT_MAIN)
        style.configure("Treeview", background=BTN_BG, foreground=FG_COLOR, fieldbackground=BTN_BG)
        style.map("Treeview", background=[("selected", "#444")])

        self.manager = ScreenManager(self.root)
        self.conn = make_connection()
        self.cursor = self.conn.cursor()
        try:
            self.cursor.callproc("dbms_output.enable", [None])
        except Exception:
            pass
        self.player_name = None

        self.draw_login()

    def style_button(self, btn):
        try:
            btn.configure(
                bg=BTN_BG,
                fg=FG_COLOR,
                activebackground=BTN_BG_HOVER,
                activeforeground=FG_COLOR,
                font=FONT_MAIN,
                bd=1,
                relief="solid",
                highlightthickness=0
            )
        except Exception:
            pass

    def draw_login(self):
        frm = tk.Frame(self.root, bg=BG_COLOR)
        self.manager.add("login", frm)

        lbl = tk.Label(frm, text="Имя игрока:", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        lbl.pack(pady=20)
        self.e_name = tk.Entry(frm, font=FONT_MAIN, bg="#2b2b2b", fg=FG_COLOR, insertbackground=FG_COLOR)
        self.e_name.pack(pady=5)

        btn = tk.Button(frm, text="Регистрация", command=self.register)
        self.style_button(btn)
        btn.pack(pady=10)

        btn2 = tk.Button(frm, text="Войти", command=self.login)
        self.style_button(btn2)
        btn2.pack(pady=10)

        self.manager.show("login")

    def register(self):
        name = self.e_name.get().strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите имя")
            return
        try:
            self.cursor.execute("SELECT id_player FROM Players WHERE LOWER(name) = LOWER(:n)", [name])
            if self.cursor.fetchone():
                messagebox.showinfo("Информация",
                                    "Игрок с таким именем уже существует. Войдите или выберите другое имя.")
                return
        except Exception as e:
            messagebox.showerror("Ошибка БД", f"Не удалось проверить существование игрока:\n{e}")
            return

        try:
            self.cursor.callproc("connect_four.create_player", [name])
            self.conn.commit()
            out = read_dbms_output(self.cursor)
            messagebox.showinfo("OK", out or "Игрок создан")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось создать игрока:\n{e}")

    def login(self):
        name = self.e_name.get().strip()
        if not name:
            messagebox.showwarning("Ошибка", "Введите имя")
            return
        self.cursor.execute("SELECT 1 FROM Players WHERE LOWER(name) = LOWER(:n)", [name])
        if not self.cursor.fetchone():
            messagebox.showerror("Ошибка", "Игрок не найден")
            return
        self.player_name = name
        self.draw_menu()
        self.manager.show("menu")

    def draw_menu(self):
        frm = tk.Frame(self.root, bg=BG_COLOR)
        self.manager.add("menu", frm)

        lbl = tk.Label(frm, text=f"Игрок: {self.player_name}", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        lbl.pack(pady=20)
        btn = tk.Button(frm, text="Новая игра", width=20, height=2, command=self.new_game)
        self.style_button(btn)
        btn.pack(pady=10)
        btn2 = tk.Button(frm, text="Запущенные партии", width=20, height=2, command=self.open_active_games)
        self.style_button(btn2)
        btn2.pack(pady=10)
        btn3 = tk.Button(frm, text="История", width=20, height=2, command=self.show_history)
        self.style_button(btn3)
        btn3.pack(pady=10)
        btn4 = tk.Button(frm, text="Лидеры", width=20, height=2, command=self.show_leaders)
        self.style_button(btn4)
        btn4.pack(pady=10)
        btn5 = tk.Button(frm, text="Правила игры", width=20, height=2, command=self.show_rules)
        self.style_button(btn5)
        btn5.pack(pady=10)
        btn6 = tk.Button(frm, text="Выйти", width=20, height=2, command=self.logout)
        self.style_button(btn6)
        btn6.pack(pady=20)
        self.manager.show("menu")

    def logout(self):
        self.player_name = None
        self.draw_login()
        self.manager.show("login")

    def new_game(self):
        frm = tk.Frame(self.root, bg=BG_COLOR)
        self.manager.add("new_game", frm)
        btn_back = tk.Button(frm, text="Назад", command=lambda: self.manager.show("menu"))
        self.style_button(btn_back)
        btn_back.pack(anchor="w", padx=10, pady=10)
        lbl = tk.Label(frm, text="Имя соперника:", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        lbl.pack(pady=5)
        e_rival = tk.Entry(frm, font=FONT_MAIN, bg="#2b2b2b", fg=FG_COLOR, insertbackground=FG_COLOR)
        e_rival.pack(pady=5)
        lblw = tk.Label(frm, text=f"Ширина (7..10):", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        lblw.pack(pady=5)
        e_w = tk.Entry(frm, font=FONT_MAIN, bg="#2b2b2b", fg=FG_COLOR, insertbackground=FG_COLOR)
        e_w.insert(0, "7")
        e_w.pack(pady=5)
        lblh = tk.Label(frm, text=f"Высота (6..8):", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        lblh.pack(pady=5)
        e_h = tk.Entry(frm, font=FONT_MAIN, bg="#2b2b2b", fg=FG_COLOR, insertbackground=FG_COLOR)
        e_h.insert(0, "6")
        e_h.pack(pady=5)
        v_timer = tk.BooleanVar(value=False)
        chk = tk.Checkbutton(frm, text="Таймер (60s)", variable=v_timer, font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR, selectcolor=BG_COLOR, activebackground=BG_COLOR)
        chk.pack(pady=5)
        lblc = tk.Label(frm, text="Ваш цвет:", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR)
        lblc.pack(pady=5)
        color_var = tk.StringVar(value="RED")
        rb1 = tk.Radiobutton(frm, text="Красный", variable=color_var, value="RED", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR, activebackground=BG_COLOR, selectcolor=BG_COLOR)
        rb1.pack()
        rb2 = tk.Radiobutton(frm, text="Желтый", variable=color_var, value="YELLOW", font=FONT_MAIN, bg=BG_COLOR, fg=FG_COLOR, activebackground=BG_COLOR, selectcolor=BG_COLOR)
        rb2.pack()

        def do_start():
            if active_sessions.get(self.player_name):
                messagebox.showwarning("Внимание", "У вас уже запущена игровая сессия в этом интерфейсе.")
                return

            rival = e_rival.get().strip()
            try:
                w = int(e_w.get())
                h = int(e_h.get())
            except ValueError:
                messagebox.showwarning("Ошибка", "Некорректные размеры")
                return

            if not rival:
                messagebox.showwarning("Ошибка", "Введите имя соперника")
                return

            try:
                self.cursor.callproc("connect_four.start_game", [
                    self.player_name, rival, w, h, bool(v_timer.get())
                ])
                self.conn.commit()
                out = read_dbms_output(self.cursor)
            except Exception as e:
                messagebox.showerror("Ошибка", f"Не удалось создать игру:\n{e}")
                return

            if out and not re.search(r'NEW_GAME_ID\s*=\s*\d+', out):
                messagebox.showinfo("Сообщение сервера", out)
                return

            m = re.search(r'NEW_GAME_ID\s*=\s*(\d+)', out)
            if not m:
                messagebox.showerror("Ошибка", "Не удалось создать игру")
                return

            gid = int(m.group(1))

            try:
                board = GameBoardWindow(self.root, self.manager, self.conn, gid, self.player_name, preferred_color=color_var.get())
            except RuntimeError:
                messagebox.showwarning("Внимание", "У этого пользователя уже открыта игровая сессия.")
                return
            self.manager.add("board", board)
            self.manager.show("board")

        btn_start = tk.Button(frm, text="Старт", command=do_start)
        self.style_button(btn_start)
        btn_start.pack(pady=20)
        self.manager.show("new_game")

    def open_active_games(self):
        frm = tk.Frame(self.root, bg=BG_COLOR)
        self.manager.add("active_games", frm)

        btn_back = tk.Button(frm, text="Назад", command=lambda: self.manager.show("menu"))
        self.style_button(btn_back)
        btn_back.pack(anchor="w", padx=10, pady=10)

        tree = ttk.Treeview(frm, columns=("id", "start", "opponent"), show="headings")
        tree.heading("id", text="ID")
        tree.heading("start", text="Start")
        tree.heading("opponent", text="Opponent")
        tree.pack(fill="both", expand=True)

        q = """
            SELECT gh.id_game, gh.start_time,
                   (SELECT p.name FROM Players p
                    JOIN Current_game cg ON p.id_player = cg.id_player
                    WHERE cg.id_game = gh.id_game AND p.name <> :n
                    AND ROWNUM = 1) AS opponent
            FROM Game_history gh
            JOIN Current_game cg ON cg.id_game = gh.id_game
            JOIN Players p ON p.id_player = cg.id_player
            WHERE LOWER(p.name) = LOWER(:n)
              AND gh.result = 'В процессе'
            GROUP BY gh.id_game, gh.start_time
            ORDER BY gh.start_time DESC
        """
        self.cursor.execute(q, [self.player_name, self.player_name])
        rows = self.cursor.fetchall()

        for r in rows:
            tree.insert("", "end", values=r)

        def open_selected():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Info", "Выберите партию.")
                return
            gid = tree.item(sel[0])['values'][0]
            if active_sessions.get(self.player_name):
                messagebox.showwarning("Внимание", "У этого пользователя уже открыта игровая сессия.")
                return
            try:
                board = GameBoardWindow(self.root, self.manager, self.conn, gid, self.player_name)
            except RuntimeError:
                messagebox.showwarning("Внимание", "У этого пользователя уже открыта игровая сессия.")
                return
            self.manager.add("board", board)
            self.manager.show("board")

        btn_open = tk.Button(frm, text="Открыть", command=open_selected)
        self.style_button(btn_open)
        btn_open.pack(pady=10)

        self.manager.show("active_games")

    def show_history(self):
        frm = tk.Frame(self.root, bg=BG_COLOR)
        self.manager.add("history", frm)
        btn_back = tk.Button(frm, text="Назад", command=lambda: self.manager.show("menu"))
        self.style_button(btn_back)
        btn_back.pack(anchor="w", padx=10, pady=10)

        cols = ("id","start","end","duration","result","winner")
        tree = ttk.Treeview(frm, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c.capitalize())
        tree.pack(fill="both", expand=True)

        try:
            self.cursor.execute("SELECT id_player FROM Players WHERE LOWER(name)=LOWER(:n)", [self.player_name])
            r = self.cursor.fetchone()
            if not r:
                messagebox.showerror("Ошибка", "Игрок не найден")
                return
            pid = r[0]
        except Exception as e:
            messagebox.showerror("Ошибка БД", str(e))
            return

        q = """
            SELECT gh.id_game,
                   TO_CHAR(gh.start_time,'YYYY-MM-DD HH24:MI:SS') AS start_time,
                   NVL(TO_CHAR(gh.end_time,'YYYY-MM-DD HH24:MI:SS'),'N/A') AS end_time,
                   NVL(ROUND((gh.end_time - gh.start_time)*24*3600), 0) AS duration_sec,
                   gh.result,
                   gh.winner_id
            FROM Game_history gh
            JOIN Current_game cg ON cg.id_game = gh.id_game
            WHERE cg.id_player = :pid
            ORDER BY gh.start_time DESC
        """
        try:
            self.cursor.execute(q, [pid])
            rows = self.cursor.fetchall()
            for r in rows:
                gid, start_t, end_t, dur, result, winner_id = r
                if winner_id:
                    self.cursor.execute("SELECT name FROM Players WHERE id_player = :w", [winner_id])
                    rr = self.cursor.fetchone()
                    wname = rr[0] if rr else str(winner_id)
                    winner_display = f"{wname} (id {winner_id})"
                else:
                    winner_display = "-"
                tree.insert("", "end", values=(gid, start_t, end_t, dur, result, winner_display))
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

        self.manager.show("history")

    def show_rules(self):
        try:
            self.cursor.callproc("connect_four.info", [])
            out = read_dbms_output(self.cursor)
            if out.strip():
                messagebox.showinfo("Правила игры", out.strip())
            else:
                messagebox.showinfo("Правила игры", "Правила недоступны.")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось загрузить правила:\n{e}")

    def show_leaders(self):
        frm = tk.Frame(self.root, bg=BG_COLOR)
        self.manager.add("leaders", frm)

        btn_back = tk.Button(frm, text="Назад", command=lambda: self.manager.show("menu"))
        self.style_button(btn_back)
        btn_back.pack(anchor="w", padx=10, pady=10)

        tree = ttk.Treeview(frm, columns=("name","wins","losses","draws","success","total"), show="headings")
        for col in ("name","wins","losses","draws","success","total"):
            tree.heading(col, text=col.capitalize())
        tree.pack(fill="both", expand=True)

        q = """
            SELECT p.name, NVL(r.wins,0), NVL(r.losses,0),
                   NVL(r.draws,0), NVL(r.success,0), (NVL(r.wins,0)+NVL(r.losses,0)+NVL(r.draws,0)) AS total_games
            FROM Rating r
            JOIN Players p ON r.id_player = p.id_player
            WHERE (NVL(r.wins,0)+NVL(r.losses,0)+NVL(r.draws,0)) >= 10
            ORDER BY r.success DESC NULLS LAST, r.wins DESC
        """
        try:
            self.cursor.execute(q)
            rows = self.cursor.fetchall()
            for r in rows:
                tree.insert("", "end", values=r)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))

        self.manager.show("leaders")

if __name__ == "__main__":
    root = tk.Tk()
    app = ConnectFourApp(root)
    root.mainloop()