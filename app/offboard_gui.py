# -*- coding: utf-8 -*-
"""
OffboardCleaner —— Tkinter 扁平化动画界面
环形扇形图展示各应用数据占比；数据模块/扇形段悬停放大动画；清理进度动画。
"""
import math
import os
import sys
import time
import threading
import queue
import tkinter as tk
from tkinter import ttk

import offboard_app as core

# ---------- 扁平化配色 ----------
BG        = '#F3F5F9'
CARD      = '#FFFFFF'
LINE      = '#E6EAF2'
INK       = '#1F2A3D'
INK2      = '#5A6B84'
INK3      = '#93A1B8'
PRIMARY   = '#3B6FF5'
DANGER    = '#F04B4B'
DANGER_DK = '#D63A3A'
GREEN     = '#07C160'
ORANGE    = '#C97E00'
FONT      = ('Microsoft YaHei UI', 10)
FONT_S    = ('Microsoft YaHei UI', 9)
FONT_B    = ('Microsoft YaHei UI', 10, 'bold')
FONT_T    = ('Microsoft YaHei UI', 16, 'bold')

APP_COLORS = {
    '微信': '#07C160', 'QQ': '#12B7F5', '企业微信': '#1E6FFF',
    'Chrome': '#FBBC04', 'Edge': '#0F6CBD',
    '钉钉': '#0089FF', '飞书': '#3370FF',
    '夸克': '#F94A4A', '豆包': '#6C4EF0',
}


def app_color(name):
    for k, v in APP_COLORS.items():
        if k in name:
            return v
    return '#9AA5B1'


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def donut_seg(cx, cy, r_o, r_i, a0, a1, steps=24):
    pts = []
    for i in range(steps + 1):
        a = a0 + (a1 - a0) * i / steps
        pts += [cx + r_o * math.cos(a), cy + r_o * math.sin(a)]
    for i in range(steps + 1):
        a = a1 - (a1 - a0) * i / steps
        pts += [cx + r_i * math.cos(a), cy + r_i * math.sin(a)]
    return pts


class OffboardGUI:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.cancel_evt = threading.Event()

        # 状态
        self.targets = []
        self.groups = []
        self.total_mb = 0.0
        self.checked = {}          # group name -> bool
        self.passes = 3
        self.scanning = False
        self.cleaning = False

        # 交互状态
        self.hover_seg = None      # 环形段 hover
        self.hover_card = None     # 卡片 hover
        self.seg_scale = {}        # 段当前放大系数
        self.card_anim = {}        # 卡片当前放大系数
        self.scroll_y = 0
        self.anim_running = False

        self.cx = 250; self.cy = 320
        self.r_o = 118; self.r_i = 66
        self.card_h = 76

        self._build()
        self.root.after(100, self._poll)
        self.root.after(200, self.do_scan)

    # ================= UI 构建 =================
    def _build(self):
        self.root.title('OffboardCleaner · 离职数据安全清理')
        self.root.geometry('980x700')
        self.root.minsize(900, 640)
        self.root.configure(bg=BG)
        try:
            self.root.iconbitmap(resource_path('icon.ico'))
        except Exception:
            pass

        # 顶部 Header（真实组件）
        hd = tk.Frame(self.root, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        hd.pack(fill='x', padx=16, pady=(14, 0))
        self.canvas_hd = tk.Canvas(hd, height=58, bg=CARD, highlightthickness=0)
        self.canvas_hd.pack(fill='x')

        # 主体
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=16, pady=14)

        # 左：环形图
        left = tk.Frame(body, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        left.pack(side='left', fill='both', expand=True)
        self.canvas_donut = tk.Canvas(left, bg=CARD, highlightthickness=0)
        self.canvas_donut.pack(fill='both', expand=True, padx=10, pady=6)

        # 右：卡片 + 控制
        right = tk.Frame(body, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        right.pack(side='right', fill='both', expand=True, padx=(14, 0))
        self.canvas_cards = tk.Canvas(right, bg=CARD, highlightthickness=0)
        self.canvas_cards.pack(fill='both', expand=True, padx=10, pady=(6, 0))
        ctrl = tk.Frame(right, bg=CARD)
        ctrl.pack(fill='x', padx=10, pady=10)

        tk.Label(ctrl, text='覆写次数', bg=CARD, fg=INK2, font=FONT_S).pack(side='left')
        self.passes_var = tk.StringVar(value='3')
        cmb = ttk.Combobox(ctrl, textvariable=self.passes_var, values=('3 次（推荐）', '7 次（更彻底）'),
                           state='readonly', width=13, font=FONT_S)
        cmb.pack(side='left', padx=(6, 0))
        cmb.bind('<<ComboboxSelected>>', lambda e: self._set_passes())

        self.btn_kill = tk.Button(ctrl, text='结束相关进程', command=self.do_kill,
                                  bg='#EEF1F7', fg=INK2, relief='flat', font=FONT_S,
                                  activebackground='#E3E8F2', activeforeground=INK,
                                  cursor='hand2', padx=10, pady=5)
        self.btn_kill.pack(side='left', padx=(10, 0))
        self.btn_kill.bind('<Enter>', lambda e: self.btn_kill.configure(bg='#E3E8F2'))
        self.btn_kill.bind('<Leave>', lambda e: self.btn_kill.configure(bg='#EEF1F7'))

        self.btn_clean = tk.Button(ctrl, text='开始安全清理', command=self._ask_confirm,
                                   bg=DANGER, fg='white', relief='flat', font=FONT_B,
                                   activebackground=DANGER_DK, activeforeground='white',
                                   cursor='hand2', padx=16, pady=5)
        self.btn_clean.pack(side='right')
        self.btn_clean.bind('<Enter>', lambda e: self.btn_clean.configure(bg=DANGER_DK))
        self.btn_clean.bind('<Leave>', lambda e: self.btn_clean.configure(bg=DANGER))

        # 扫描进度条
        self.scanbar = tk.Frame(self.root, bg='#E6EAF2', height=4)
        self.scanbar_fill = tk.Frame(self.scanbar, bg=PRIMARY, width=0)

        # 事件
        self.canvas_donut.bind('<Motion>', self._on_motion_donut)
        self.canvas_donut.bind('<Leave>', lambda e: self._clear_hover('seg'))
        self.canvas_cards.bind('<Motion>', self._on_motion_cards)
        self.canvas_cards.bind('<Leave>', lambda e: self._clear_hover('card'))
        self.canvas_cards.bind('<MouseWheel>', self._on_wheel)
        self.canvas_donut.bind('<MouseWheel>', self._on_wheel)
        self.root.bind('<Configure>', lambda e: self._redraw_all())
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ================= 绘制 =================
    def _redraw_all(self):
        self._draw_header()
        self._draw_donut()
        self._draw_cards()

    def _draw_header(self):
        c = self.canvas_hd
        c.delete('all')
        c.update_idletasks()
        W = max(c.winfo_width(), 200)
        # Logo
        logo = rounded_rect(c, 14, 8, 66, 50, 12, fill=PRIMARY, outline='')
        # 环形小图标
        c.create_arc(26, 20, 54, 48, start=90, extent=270, width=4, style='arc',
                     outline='#FFFFFF')
        c.create_text(100, 20, anchor='w', text='OffboardCleaner · 离职数据安全清理',
                      fill=INK, font=FONT_B)
        c.create_text(100, 42, anchor='w',
                      text='多次覆写 + 清零，阻止常规恢复 · 微信 / QQ / 企业微信 / 浏览器密码与记录',
                      fill=INK3, font=('Microsoft YaHei UI', 8))
        # 管理员徽章 + 重新扫描
        admin = core.is_admin()
        bx = W - 96
        rounded_rect(c, bx - 86, 14, bx + 66, 44, 15,
                     fill=('#E9F6EE' if admin else '#FFF2DE'), outline='')
        c.create_text(bx - 10, 29, text=('🛡 管理员模式' if admin else '普通权限'),
                      fill=('#1FA55A' if admin else ORANGE), font=FONT_S)
        btn = rounded_rect(c, bx + 76, 14, bx + 150, 44, 11,
                           fill='#EEF1F7', outline='', tags=('rescan',))
        c.create_text(bx + 113, 29, text='重新扫描', fill=INK2, font=FONT_S, tags=('rescan',))
        c.tag_bind('rescan', '<Button-1>', lambda e: self.do_scan())
        c.tag_bind('rescan', '<Enter>', lambda e: c.itemconfig('rescan', fill='#E3E8F2'))
        c.tag_bind('rescan', '<Leave>', lambda e: c.itemconfig('rescan', fill='#EEF1F7'))

    def _draw_donut(self):
        c = self.canvas_donut
        c.delete('all')
        c.update_idletasks()
        W = max(c.winfo_width(), 300)
        H = max(c.winfo_height(), 300)
        self.cx = W / 2
        self.cy = H / 2 + 6
        ro = self.r_o
        ri = self.r_i

        groups = self.groups
        if not groups:
            c.create_text(self.cx, self.cy - 20, text='未发现可清理数据',
                          fill=INK3, font=FONT_B)
            c.create_text(self.cx, self.cy + 6, text='点击右上角「重新扫描」',
                          fill=INK3, font=FONT_S)
            return

        total = self.total_mb or 1
        start = -math.pi / 2
        n = len(groups)
        for i, g in enumerate(groups):
            frac = g['size_mb'] / total
            sweep = frac * math.pi * 2
            if i == n - 1:
                sweep = math.pi * 2 - (start + math.pi / 2)
            if sweep > math.pi * 1.998:
                sweep = math.pi * 1.998
            end = start + sweep
            scale = self.seg_scale.get(i, 1.0)
            col = app_color(g['name'])
            pts = donut_seg(self.cx, self.cy, ro * scale, ri * scale, start, end)
            c.create_polygon(pts, fill=col, outline=CARD, width=2,
                             tags=('seg', 'seg%d' % i))
            # 中央总量
            c.delete('center_total')
            c.create_text(self.cx, self.cy - 12, text=core.fmt_size(total),
                          fill=INK, font=FONT_T, tags='center_total')
            c.create_text(self.cx, self.cy + 14, text='待清理数据总量',
                          fill=INK3, font=FONT_S, tags='center_total')
            start = end

        # 图例
        ly = H - 46
        c.delete('legend')
        c.create_text(14, ly - 8, anchor='w', text='各应用数据占比（悬停放大查看）',
                      fill=INK2, font=FONT_S, tags='legend')
        x = 14
        for i, g in enumerate(groups):
            col = app_color(g['name'])
            c.create_rectangle(x, ly, x + 10, ly + 10, fill=col, outline='', tags='legend')
            txt = '%s %s · %d%%' % (g['name'], core.fmt_size(g['size_mb']),
                                    max(1, round(g['size_mb'] / total * 100)))
            c.create_text(x + 15, ly + 5, anchor='w', text=txt, fill=INK2,
                          font=('Microsoft YaHei UI', 8), tags='legend')
            x += 150
            if x > W - 150:
                x = 14
                ly += 22

    def _draw_cards(self):
        c = self.canvas_cards
        c.delete('all')
        c.update_idletasks()
        W = max(c.winfo_width(), 320)
        H = max(c.winfo_height(), 200)
        c.create_text(14, 4, anchor='w', text='清理目标（点击卡片可取消勾选）',
                      fill=INK2, font=FONT_S)
        groups = self.groups
        if not groups:
            c.create_text(W / 2, H / 2, text='暂无数据', fill=INK3, font=FONT_B)
            return
        card_w = W - 24
        y = 26 - self.scroll_y
        for i, g in enumerate(groups):
            base_h = self.card_h
            sc = self.card_anim.get(i, 1.0)
            x1 = 8 - (sc - 1) * 8
            y1 = y - (sc - 1) * 6
            x2 = x1 + card_w + (sc - 1) * 16
            y2 = y1 + base_h + (sc - 1) * 12
            col = app_color(g['name'])
            checked = self.checked.get(g['name'], True)
            if y2 < -20 or y1 > H + 20:
                y += base_h + 12
                continue
            # 卡片底
            tag = 'card%d' % i
            rounded_rect(c, x1, y1, x2, y2, 13, fill='#FBFCFE',
                         outline=col if checked else LINE,
                         width=1.5 if not checked else 2, tags=tag)
            # 图标
            rounded_rect(c, x1 + 12, y1 + 14, x1 + 52, y2 - 14, 11, fill=col,
                         outline='', tags=tag)
            c.create_text(x1 + 32, (y1 + y2) / 2, text=g['name'][0], fill='white',
                          font=('Microsoft YaHei UI', 15, 'bold'), tags=tag)
            # 名称/描述
            c.create_text(x1 + 66, y1 + 22, anchor='w', text=g['name'],
                          fill=INK, font=FONT_B, tags=tag)
            c.create_text(x1 + 66, y1 + 46, anchor='w',
                          text='%d 个清理目标 · 覆写 %d 次' % (g['targets'], self.passes),
                          fill=INK3, font=('Microsoft YaHei UI', 8), tags=tag)
            # 大小
            c.create_text(x2 - 14, y1 + 26, anchor='e', text=core.fmt_size(g['size_mb']),
                          fill=INK, font=('Microsoft YaHei UI', 13, 'bold'), tags=tag)
            # 勾选
            bx1, by1, bx2, by2 = x2 - 40, y2 - 24, x2 - 16, y2 - 2
            rounded_rect(c, bx1, by1, bx2, by2, 6,
                         fill=(col if checked else '#FFFFFF'),
                         outline=('#D5DBE8' if not checked else col), tags=tag)
            if checked:
                c.create_line(bx1 + 5, (by1 + by2) / 2, bx1 + 9, by2 - 5,
                              fill='white', width=2, tags=tag)
                c.create_line(bx1 + 9, by2 - 5, bx2 - 5, by1 + 4,
                              fill='white', width=2, tags=tag)
            c.tag_bind(tag, '<Button-1>', lambda e, idx=i: self._toggle_card(idx))
            y += base_h + 12

    # ================= 交互 =================
    def _set_passes(self):
        v = self.passes_var.get()
        self.passes = 3 if '3' in v else 7
        self._redraw_all()

    def _on_wheel(self, e):
        self.scroll_y = max(0, min(self.scroll_y + (e.delta / 120) * 30, max(0, len(self.groups) * 90 - 200)))
        self._redraw_all()

    def _clear_hover(self, kind):
        if kind == 'seg':
            if self.hover_seg is not None:
                self.hover_seg = None
                self._start_anim()
        else:
            if self.hover_card is not None:
                self.hover_card = None
                self._start_anim()

    def _on_motion_donut(self, e):
        if not self.groups:
            return
        dx = e.x - self.cx
        dy = e.y - self.cy
        d = math.hypot(dx, dy)
        seg = None
        if self.r_i <= d <= self.r_o * 1.1:
            ang = math.atan2(dy, dx)
            if ang < -math.pi / 2:
                ang += math.pi * 2
            start = -math.pi / 2
            total = self.total_mb or 1
            for i, g in enumerate(self.groups):
                frac = g['size_mb'] / total
                end = start + frac * math.pi * 2
                if start <= ang <= end or (i == len(self.groups) - 1 and ang >= start):
                    seg = i
                    break
                start = end
        if seg != self.hover_seg:
            self.hover_seg = seg
            self._start_anim()

    def _on_motion_cards(self, e):
        idx = None
        groups = self.groups
        y = 26 - self.scroll_y
        for i in range(len(groups)):
            if y <= e.y <= y + self.card_h and 8 <= e.x <= self.canvas_cards.winfo_width() - 8:
                idx = i
                break
            y += self.card_h + 12
        if idx != self.hover_card:
            self.hover_card = idx
            self._start_anim()

    def _toggle_card(self, idx):
        g = self.groups[idx]
        self.checked[g['name']] = not self.checked.get(g['name'], True)
        self._redraw_all()

    # ================= 动画引擎 =================
    def _start_anim(self):
        if not self.anim_running:
            self.anim_running = True
            self._animate()

    def _animate(self):
        changed = False
        n = len(self.groups)
        for i in range(n):
            goal = 1.10 if self.hover_seg == i else 1.0
            cur = self.seg_scale.get(i, 1.0)
            nxt = cur + (goal - cur) * 0.25
            if abs(nxt - goal) < 0.005:
                nxt = goal
            self.seg_scale[i] = nxt
            if abs(nxt - goal) > 0.001:
                changed = True
        for i in range(n):
            goal = 1.06 if self.hover_card == i else 1.0
            cur = self.card_anim.get(i, 1.0)
            nxt = cur + (goal - cur) * 0.25
            if abs(nxt - goal) < 0.005:
                nxt = goal
            self.card_anim[i] = nxt
            if abs(nxt - goal) > 0.001:
                changed = True
        self._draw_donut()
        self._draw_cards()
        if changed:
            self.root.after(16, self._animate)
        else:
            self.anim_running = False

    # ================= 扫描 =================
    def do_scan(self):
        if self.scanning:
            return
        self.scanning = True
        self.scanbar.pack(fill='x', padx=16, pady=(10, 0))
        self._scan_bounce(0)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_bounce(self, n):
        if not self.scanning:
            self.scanbar.pack_forget()
            return
        W = max(self.root.winfo_width(), 800)
        w = int(W * 0.22)
        x = int(W * (0.5 + 0.5 * math.sin(n / 12)) - w * 0.5)
        self.scanbar_fill.place(x=x, y=0, width=w, relheight=1)
        self.root.after(24, self._scan_bounce, n + 1)

    def _scan_worker(self):
        targets = core.scan()
        self.q.put(('scan_done', targets))

    # ================= 进程 / 清理 =================
    def do_kill(self):
        self.q.put(('toast', '正在结束相关进程…'))
        threading.Thread(target=self._kill_worker, daemon=True).start()

    def _kill_worker(self):
        killed = core.terminate_processes()
        self.q.put(('kill_done', killed))

    def _ask_confirm(self):
        groups = [g for g in self.groups if self.checked.get(g['name'], True)]
        if not groups:
            self.q.put(('toast', '请先勾选要清理的目标'))
            return
        if self.cleaning:
            return
        total = sum(g['size_mb'] for g in groups)
        win = tk.Toplevel(self.root)
        win.title('确认清理')
        win.configure(bg=CARD)
        win.transient(self.root)
        win.grab_set()
        w, h = 440, 300
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry('%dx%d+%d+%d' % (w, h, x, y))
        tk.Label(win, text='确认执行安全清理？', bg=CARD, fg=INK, font=FONT_B).pack(anchor='w', padx=20, pady=(18, 6))
        box = tk.Frame(win, bg='#FBFCFE', highlightbackground=LINE, highlightthickness=1)
        box.pack(fill='both', expand=True, padx=20, pady=4)
        for g in groups:
            tk.Label(box, text='• %s —— %s（%d 个目标）' % (g['name'], core.fmt_size(g['size_mb']), g['targets']),
                     bg='#FBFCFE', fg=INK2, font=FONT_S, anchor='w').pack(fill='x', padx=12, pady=2)
        tk.Label(box, text='合计约 %s\n将执行随机数据覆写 %d 次 + 清零后删除，不可恢复！' % (core.fmt_size(total), self.passes),
                 bg='#FBFCFE', fg=DANGER, font=FONT_S, anchor='w').pack(fill='x', padx=12, pady=(8, 2))
        btns = tk.Frame(win, bg=CARD)
        btns.pack(fill='x', padx=20, pady=12)
        b1 = tk.Button(btns, text='取消', command=win.destroy, bg='#EEF1F7', fg=INK2,
                       relief='flat', font=FONT_S, activebackground='#E3E8F2', padx=14, pady=4)
        b1.pack(side='right')
        b2 = tk.Button(btns, text='确认并开始', command=lambda: self._start_clean(win),
                       bg=DANGER, fg='white', relief='flat', font=FONT_B,
                       activebackground=DANGER_DK, padx=14, pady=4)
        b2.pack(side='right', padx=(0, 8))

    def _start_clean(self, confirm_win):
        confirm_win.destroy()
        self.cleaning = True
        self.cancel_evt.clear()
        groups = [g for g in self.groups if self.checked.get(g['name'], True)]
        paths = []
        for g in groups:
            paths.extend(g['paths'])
        self._open_progress()
        threading.Thread(target=self._clean_worker, args=(paths,), daemon=True).start()

    def _open_progress(self):
        win = tk.Toplevel(self.root)
        win.title('正在安全清理')
        win.configure(bg=CARD)
        win.transient(self.root)
        win.grab_set()
        w, h = 460, 240
        x = self.root.winfo_x() + (self.root.winfo_width() - w) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - h) // 2
        win.geometry('%dx%d+%d+%d' % (w, h, x, y))
        win.protocol('WM_DELETE_WINDOW', lambda: None)
        self.prog_win = win

        head = tk.Frame(win, bg=CARD)
        head.pack(fill='x', padx=20, pady=(18, 10))
        self.prog_title = tk.Label(head, text='正在准备清理…', bg=CARD, fg=INK, font=FONT_B)
        self.prog_title.pack(anchor='w')
        self.prog_sub = tk.Label(head, text='', bg=CARD, fg=INK3, font=FONT_S)
        self.prog_sub.pack(anchor='w', pady=(2, 0))

        bar_bg = tk.Frame(win, bg='#EEF1F7', height=10)
        bar_bg.pack(fill='x', padx=20)
        self.prog_bar = tk.Frame(bar_bg, bg=PRIMARY, width=0, height=10)
        self.prog_bar.pack(side='left', fill='y')

        sub_bg = tk.Frame(win, bg='#EEF1F7', height=6)
        sub_bg.pack(fill='x', padx=20, pady=(8, 0))
        self.prog_subbar = tk.Frame(sub_bg, bg=GREEN, width=0, height=6)
        self.prog_subbar.pack(side='left', fill='y')

        self.prog_pct = tk.Label(win, text='0%', bg=CARD, fg=PRIMARY, font=FONT_B)
        self.prog_pct.pack(anchor='w', padx=20, pady=(6, 0))
        self.prog_file = tk.Label(win, text='', bg=CARD, fg=INK3, font=('Microsoft YaHei UI', 8), anchor='e')
        self.prog_file.pack(fill='x', padx=20, pady=(4, 0))

        btns = tk.Frame(win, bg=CARD)
        btns.pack(fill='x', padx=20, pady=12)
        bc = tk.Button(btns, text='取消清理', command=self._cancel_clean,
                       bg='#EEF1F7', fg=INK2, relief='flat', font=FONT_S,
                       activebackground='#E3E8F2', padx=12, pady=4)
        bc.pack(side='right')

    def _cancel_clean(self):
        self.cancel_evt.set()

    def _clean_worker(self, paths):
        targets = [t for t in core.scan() if t['path'] in set(paths)]
        total = len(targets)
        results = []
        for i, t in enumerate(targets):
            if self.cancel_evt.is_set():
                results.append({'path': t['path'], 'ok': False, 'cancel': True})
                break
            self.q.put(('clean_item', i + 1, total, t['app']))
            idx, total_n = i + 1, total

            def cb(fp, cur, alln):
                # 限流：每 40 个文件或最后一个才推送，避免消息风暴卡 UI
                if alln == 0:
                    return
                if cur % 40 == 0 or cur == alln:
                    self.q.put(('clean_file', idx, total_n, cur, alln))

            ok = core.secure_delete_target(t, self.passes, progress_cb=cb)
            results.append({'path': t['path'], 'ok': ok})
        self.q.put(('clean_done', results))

    # ================= 队列轮询 =================
    def _poll(self):
        try:
            while True:
                msg = self.q.get_nowait()
                self._handle(msg)
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _handle(self, msg):
        kind = msg[0]
        if kind == 'scan_done':
            self.targets = msg[1]
            self.groups = core.group_targets(self.targets)
            self.total_mb = sum(g['size_mb'] for g in self.groups)
            for g in self.groups:
                self.checked.setdefault(g['name'], True)
            self.scanning = False
            self.scanbar.pack_forget()
            self._redraw_all()
            if not self.groups:
                self._toast('未发现可清理的数据')
            else:
                self._toast('扫描完成：%d 个目标，共 %s' % (len(self.targets), core.fmt_size(self.total_mb)))
        elif kind == 'kill_done':
            killed = msg[1]
            self._toast('已结束进程：' + '、'.join(killed[:5]) + (' 等' if len(killed) > 5 else '') if killed else '未检测到相关进程')
        elif kind == 'toast':
            self._toast(msg[1])
        elif kind == 'clean_item':
            if hasattr(self, 'prog_win'):
                try:
                    self.prog_title.config(text='正在安全覆写：' + msg[3])
                    self.prog_sub.config(text='第 %d / %d 项' % (msg[1], msg[2]))
                except tk.TclError:
                    pass
        elif kind == 'clean_file':
            if hasattr(self, 'prog_win'):
                try:
                    cur, total, fcur, fall = msg[1], msg[2], msg[3], msg[4]
                    bw = int(400 * 0.6)
                    self.prog_bar.config(width=int(bw * cur / total) if total else 0)
                    self.prog_pct.config(text='%d%%' % (cur * 100 // total if total else 0))
                    if fall:
                        self.prog_subbar.config(width=int(bw * fcur / fall))
                except tk.TclError:
                    pass
        elif kind == 'clean_done':
            results = msg[1]
            ok = sum(1 for r in results if r.get('ok'))
            fail = sum(1 for r in results if not r.get('ok'))
            self.cleaning = False
            self._close_progress()
            self._toast('清理完成：成功 %d，失败 %d' % (ok, fail))
            self.do_scan()

    def _close_progress(self):
        try:
            if hasattr(self, 'prog_win'):
                self.prog_win.destroy()
        except tk.TclError:
            pass

    def _toast(self, text):
        """底部轻提示。"""
        try:
            if hasattr(self, '_toast_win') and self._toast_win.winfo_exists():
                self._toast_win.destroy()
            w = tk.Toplevel(self.root)
            w.overrideredirect(True)
            w.configure(bg=INK)
            tk.Label(w, text=text, bg=INK, fg='white', font=FONT_S,
                     padx=18, pady=9).pack()
            w.update_idletasks()
            x = self.root.winfo_x() + (self.root.winfo_width() - w.winfo_width()) // 2
            y = self.root.winfo_y() + self.root.winfo_height() - 70
            w.geometry('+%d+%d' % (x, y))
            w.lift()
            self._toast_win = w
            self.root.after(2800, lambda: w.destroy() if w.winfo_exists() else None)
        except tk.TclError:
            pass

    def _on_close(self):
        self.root.destroy()


def _dbg(msg):
    """写入诊断日志（定位 GUI 启动阶段问题）。"""
    try:
        base = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base, 'app_debug.log'), 'a', encoding='utf-8') as f:
            f.write('[%s] %s\n' % (time.strftime('%H:%M:%S'), msg))
    except Exception:
        pass


def resource_path(rel):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    _dbg('=== 启动 ===')
    try:
        root = tk.Tk()
        _dbg('Tk 根窗口已创建')
        OffboardGUI(root)
        _dbg('界面构建完成，进入主循环')
        root.mainloop()
        _dbg('主循环退出')
    except Exception as e:
        import traceback
        _dbg('异常: %r\n%s' % (e, traceback.format_exc()))
        raise


if __name__ == '__main__':
    main()
