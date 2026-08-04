# -*- coding: utf-8 -*-
"""
OffboardCleaner —— Tkinter 现代化 UI + 弹性动画引擎 v2.0
环形扇形图（生长弧+径向偏移）| 左侧彩条卡片 | 光泽进度条 | 弹簧缓动
"""
import math, os, sys, time, threading, queue, tkinter as tk
from tkinter import ttk
import offboard_app as core

# ==================== 配色系统 ====================
BG        = '#EDF0F5'
CARD      = '#FFFFFF'
LINE      = '#E8ECF2'
INK       = '#1C2333'
INK2      = '#5B6C8A'
INK3      = '#93A5C0'
PRIMARY   = '#4F7CFF'
DANGER    = '#F04747'
DANGER_DK = '#D93A3A'
GREEN     = '#1FBF75'
ORANGE    = '#DA8A00'
ACCENT    = '#7B61FF'
FONT      = ('Microsoft YaHei UI', 10)
FONT_S    = ('Microsoft YaHei UI', 9)
FONT_B    = ('Microsoft YaHei UI', 10, 'bold')
FONT_L    = ('Microsoft YaHei UI', 20, 'bold')
APP_COLORS = {
    '微信': '#07C160', 'QQ': '#12B7F5', '企业微信': '#1E6FFF',
    'Chrome': '#FBBC04', 'Edge': '#0F6CBD',
    '钉钉': '#0089FF', '飞书': '#3370FF',
    '夸克': '#F94A4A', '豆包': '#6C4EF0',
}

def app_color(name):
    for k, v in APP_COLORS.items():
        if k in name: return v
    return '#9AA5B1'

# ==================== Canvas 工具函数 ====================
def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1+r,y1, x2-r,y1, x2,y1, x2,y1+r, x2,y2-r, x2,y2, x2-r,y2,
           x1+r,y2, x1,y2, x1,y2-r, x1,y1+r, x1,y1]
    return canvas.create_polygon(pts, smooth=True, **kw)

def donut_seg(cx, cy, r_o, r_i, a0, a1, steps=36):
    """密集顶点环形段，支持圆角效果。"""
    pts = []
    for i in range(steps+1):
        a = a0 + (a1-a0)*i/steps
        pts += [cx+r_o*math.cos(a), cy+r_o*math.sin(a)]
    for i in range(steps+1):
        a = a1 - (a1-a0)*i/steps
        pts += [cx+r_i*math.cos(a), cy+r_i*math.sin(a)]
    return pts

def lerp_c(c1, c2, t):
    """两色插值（#RRGGBB 格式）。"""
    r = lambda c: int(c[1:3],16); g = lambda c: int(c[3:5],16); b = lambda c: int(c[5:7],16)
    c = lambda v: max(0,min(255,int(v)))
    return '#%02X%02X%02X' % (c(r(c1)+(r(c2)-r(c1))*t),
                               c(g(c1)+(g(c2)-g(c1))*t),
                               c(b(c1)+(b(c2)-b(c1))*t))

# ==================== 弹簧动画辅助 ====================
def spring_tick(cur, vel, goal, stiffness=0.18, damping=0.75):
    """弹簧物理单步。返回 (新位置, 新速度)。"""
    force = (goal - cur) * stiffness
    vel2  = (vel + force) * damping
    cur2  = cur + vel2
    return cur2, vel2

# ==================== 主界面类 ====================
class OffboardGUI:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        self.cancel_evt = threading.Event()
        # 数据
        self.targets = []; self.groups = []; self.total_mb = 0.0
        self.checked = {}; self.passes = 3
        self.scanning = False; self.cleaning = False
        # 交互
        self.hover_seg = None; self.hover_card = None
        self.scroll_y = 0
        # 动画变量
        self.seg_offset = {}   # 段径向偏移（像素）
        self.seg_offset_v = {}
        self.card_scale = {}   # 卡片缩放
        self.card_scale_v = {}
        self.center_alpha = 0.0; self.center_alpha_v = 0.0
        self.enter_grow = {}   # 生长弧：0→1
        self.enter_grow_v = {}
        self.anim_running = False
        # 光泽进度条
        self.shimmer_offset = 0.0
        self.bar_cur = {}      # 进度条当前宽度
        self.bar_cur_v = {}
        self.bar_goal = {}     # 进度条目标宽度
        # 尺寸
        self.cx = 250; self.cy = 320
        self.r_o = 122; self.r_i = 68; self.card_h = 82
        # 构建 UI
        self._build()
        self.root.after(100, self._poll)
        self.root.after(200, self.do_scan)

    # ==================== UI 构建 ====================
    def _build(self):
        self.root.title('OffboardCleaner · 离职数据安全清理')
        self.root.geometry('980x710')
        self.root.minsize(920, 640)
        self.root.configure(bg=BG)
        try: self.root.iconbitmap(resource_path('icon.ico'))
        except: pass
        # Header
        hd = tk.Frame(self.root, bg=PRIMARY, height=64)
        hd.pack(fill='x'); hd.pack_propagate(False)
        self.canvas_hd = tk.Canvas(hd, height=64, bg=PRIMARY, highlightthickness=0)
        self.canvas_hd.pack(fill='x')
        # 主体
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=18, pady=(16,0))
        # 左：环形图
        left = tk.Frame(body, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        left.pack(side='left', fill='both', expand=True)
        self.canvas_donut = tk.Canvas(left, bg=CARD, highlightthickness=0)
        self.canvas_donut.pack(fill='both', expand=True, padx=8, pady=4)
        # 右：卡片
        right = tk.Frame(body, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        right.pack(side='right', fill='both', expand=True, padx=(16,0))
        self.canvas_cards = tk.Canvas(right, bg=CARD, highlightthickness=0)
        self.canvas_cards.pack(fill='both', expand=True, padx=10, pady=(6,0))
        # 控制栏
        ctrl = tk.Frame(right, bg=CARD)
        ctrl.pack(fill='x', padx=10, pady=12)
        tk.Label(ctrl, text='覆写', bg=CARD, fg=INK2, font=FONT_S).pack(side='left')
        self.passes_var = tk.StringVar(value='3')
        cmb = ttk.Combobox(ctrl, textvariable=self.passes_var, values=('3 次', '7 次'),
                           state='readonly', width=6, font=FONT_S)
        cmb.pack(side='left', padx=(4,0))
        cmb.bind('<<ComboboxSelected>>', lambda e: self._set_passes())
        self.btn_kill = tk.Button(ctrl, text='结束进程', command=self.do_kill, bg='#F2F4F8',
                                  fg=INK2, relief='flat', font=FONT_S, padx=10, pady=5,
                                  cursor='hand2', activebackground='#E3E7F0')
        self.btn_kill.pack(side='left', padx=(12,0))
        self.btn_clean = tk.Button(ctrl, text='开始清理', command=self._ask_confirm, bg=DANGER,
                                   fg='white', relief='flat', font=FONT_B, padx=18, pady=5,
                                   cursor='hand2', activebackground=DANGER_DK)
        self.btn_clean.pack(side='right')
        # 扫描条
        self.scanbar = tk.Frame(self.root, bg='#DCE3EF', height=4)
        self.scanbar_fill = tk.Frame(self.scanbar, bg=PRIMARY, width=0)
        # 事件
        self.canvas_donut.bind('<Motion>', self._on_motion_donut)
        self.canvas_donut.bind('<Leave>', lambda e: self._clear_hover('seg'))
        self.canvas_cards.bind('<Motion>', self._on_motion_cards)
        self.canvas_cards.bind('<Leave>', lambda e: self._clear_hover('card'))
        self.canvas_cards.bind('<MouseWheel>', self._on_wheel)
        self.canvas_donut.bind('<MouseWheel>', self._on_wheel)
        self.root.protocol('WM_DELETE_WINDOW', self._on_close)

    # ==================== Header 绘制 ====================
    def _draw_header(self):
        c = self.canvas_hd; c.delete('all'); W = max(c.winfo_width(), 300)
        # 右上角装饰弧线
        c.create_arc(W-80, -40, W+60, 120, start=-30, extent=180, fill='#6B9AFF',
                     outline='', stipple='gray25')
        # 标题区
        c.create_text(26, 18, anchor='w', text='OffboardCleaner', fill='white',
                      font=('Microsoft YaHei UI', 15, 'bold'))
        c.create_text(26, 42, anchor='w', text='扫码后逐项覆写清零，离职不留痕',
                      fill='#B8D0FF', font=('Microsoft YaHei UI', 9))
        # Logo 图标
        c.create_oval(12, 14, 52, 54, fill='', outline='white', width=2.5)
        c.create_text(32, 34, text='✦', fill='white', font=('Arial', 14))
        # 右上按钮区
        admin = core.is_admin()
        bx = W - 110
        c.create_oval(bx-20, 16, bx-4, 40, fill='#5BF59B' if admin else '#FFC746', outline='')
        c.create_text(bx-12, 28, text='✓' if admin else '!', fill=PRIMARY if admin else ORANGE,
                      font=('Arial', 10, 'bold'))
        c.create_text(bx+6, 28, anchor='w', text='管理员' if admin else '用户权限', fill='white',
                      font=('Microsoft YaHei UI', 9, 'bold'))
        btn_x = bx + 74
        c.create_rectangle(btn_x-2, 14, btn_x+68, 42, fill='#3360DD', outline='',
                           tags=('rescan',))
        c.create_text(btn_x+33, 28, text='⟳ 重新扫描', fill='white', font=FONT_S, tags=('rescan',))
        c.tag_bind('rescan', '<Button-1>', lambda e: self.do_scan())

    # ==================== 环形图绘制 ====================
    def _draw_donut(self):
        c = self.canvas_donut; c.delete('all')
        W = max(c.winfo_width(), 260); H = max(c.winfo_height(), 260)
        self.cx = W/2; self.cy = H/2 - 4
        ro, ri = self.r_o, self.r_i
        groups = self.groups
        if not groups:
            c.create_text(self.cx, self.cy-16, text='暂无数据', fill=INK3, font=FONT_B)
            return
        total = self.total_mb or 1
        start_angle = -math.pi/2
        n = len(groups)

        for i, g in enumerate(groups):
            frac = g['size_mb']/total
            full_sweep = frac * math.pi*2
            if i == n-1: full_sweep = math.pi*2 - (start_angle+math.pi/2)
            if full_sweep > math.pi*1.998: full_sweep = math.pi*1.998
            # 生长弧：0→1 动画
            gt = self.enter_grow.get(i, 1.0)
            sweep = full_sweep * gt
            # 径向偏移（悬停）
            offset = self.seg_offset.get(i, 0.0)
            seg_ro = ro + offset*12
            seg_ri = ri + offset*8
            end = start_angle + sweep
            col = app_color(g['name'])
            # 发光外环（仅 hover 时）
            if offset > 0.5:
                glow_ro = seg_ro+6; glow_ri = seg_ri-4
                pts_g = donut_seg(self.cx, self.cy, glow_ro, glow_ri, start_angle, end, 24)
                c.create_polygon(pts_g, fill='', outline=col, width=1,
                                 stipple='gray50', tags=('seg','segg%d'%i))
            # 实心段
            pts = donut_seg(self.cx, self.cy, seg_ro, seg_ri, start_angle, end, 44)
            c.create_polygon(pts, fill=col, outline=CARD, width=1.5,
                             tags=('seg','seg%d'%i))
            start_angle = end

        # 中央信息（弹性缩放）
        ca = max(0.0, min(1.0, self.center_alpha))
        # 总量
        if ca < 0.9:
            alpha = 1.0 - ca
            fill_c = lerp_c(INK, INK3, ca)
            fsize = int(24 - ca*5)
            c.create_text(self.cx, self.cy-10, text=core.fmt_size(total),
                          fill=fill_c, font=('Microsoft YaHei UI', fsize, 'bold'),
                          tags='ct')
            if ca < 0.5:
                c.create_text(self.cx, self.cy+14, text='待清理', fill=INK3,
                              font=FONT_S, tags='ct')
        # 悬停应用信息
        if ca > 0.05 and self.hover_seg is not None and self.hover_seg < n:
            g = groups[self.hover_seg]
            pct = max(1, round(g['size_mb']/total*100))
            fill_h = lerp_c(INK2, app_color(g['name']), ca)
            fs = int(12 + ca*4)
            c.create_text(self.cx, self.cy-4,
                          text='%s\n%s · %d%%'%(g['name'],core.fmt_size(g['size_mb']),pct),
                          fill=fill_h, font=('Microsoft YaHei UI', fs, 'bold'),
                          tags='ch')

        # 图例
        ly = H - 44
        c.create_text(12, ly-12, anchor='w', text='悬停查看占比', fill=INK3,
                      font=('Microsoft YaHei UI', 8), tags='legend')
        x0 = 12
        for i, g in enumerate(groups):
            col = app_color(g['name']); pct = max(1, round(g['size_mb']/total*100))
            c.create_rectangle(x0, ly, x0+10, ly+10, fill=col, outline='', tags='legend')
            txt = '%s %s · %d%%'%(g['name'],core.fmt_size(g['size_mb']),pct)
            c.create_text(x0+16, ly+5, anchor='w', text=txt, fill=INK2,
                          font=('Microsoft YaHei UI', 8), tags='legend')
            x0 += 128
            if x0 > W-120: x0 = 12; ly += 20

    # ==================== 卡片绘制 ====================
    def _draw_cards(self):
        c = self.canvas_cards; c.delete('all')
        W = max(c.winfo_width(), 300); H = max(c.winfo_height(), 200)
        c.create_text(14, 4, anchor='w', text='清理目标', fill=INK2, font=FONT_S)
        groups = self.groups
        if not groups:
            c.create_text(W/2, H/2, text='暂无数据', fill=INK3, font=FONT_B); return
        card_w = W - 28
        y0 = 26 - self.scroll_y
        for i, g in enumerate(groups):
            bh = self.card_h
            sc = self.card_scale.get(i, 1.0)
            # 进入动画 y 偏移（scale<1→从下方"浮"上来）
            y_enter = (1-sc)*24
            x1=8; y1=y0+y_enter; x2=x1+card_w; y2=y1+bh
            if y2<-20 or y1>H+20: y0+=bh+12; continue
            col = app_color(g['name'])
            checked = self.checked.get(g['name'], True)
            tag = 'card%d'%i
            # 卡片底（带微妙圆角阴影）
            r2 = rounded_rect(c, x1, y1, x2, y2, 14, fill=CARD, outline=LINE, width=1, tags=tag)
            # 左侧彩条
            c.create_rectangle(x1+3, y1+14, x1+9, y2-14, fill=col, outline='', tags=tag)
            # 应用图标
            rounded_rect(c, x1+18, y1+18, x1+56, y2-18, 12, fill=col, outline='', tags=tag)
            c.create_text(x1+37, (y1+y2)//2, text=g['name'][0], fill='white',
                          font=('Microsoft YaHei UI', 14, 'bold'), tags=tag)
            # 文字区域
            c.create_text(x1+68, y1+22, anchor='w', text=g['name'], fill=INK, font=FONT_B,
                          tags=tag)
            c.create_text(x1+68, y1+44, anchor='w',
                          text='%d 个目标 · 覆写 %d 次'%(g['targets'],self.passes),
                          fill=INK3, font=('Microsoft YaHei UI', 8), tags=tag)
            c.create_text(x1+68, y1+62, anchor='w',
                          text='数据: %s'%core.fmt_size(g['size_mb']), fill=INK2, font=FONT_S,
                          tags=tag)
            # 右侧操作区
            bx = x2 - 110
            # 卸载按钮
            c.create_rectangle(bx, y1+32, bx+52, y1+54, fill='#FFF0F0', outline='#F5C0C0',
                               tags='uin%d'%i)
            c.create_text(bx+26, y1+43, text='卸载', fill=DANGER,
                          font=('Microsoft YaHei UI', 8, 'bold'), tags='uin%d'%i)
            c.tag_bind('uin%d'%i, '<Button-1>', lambda e, idx=i: self._uninstall_card(idx))
            # 勾选开关
            cx1,cy1,cx2,cy2 = bx+64, y1+32, bx+108, y1+54
            rounded_rect(c, cx1-1, cy1-1, cx2+1, cy2+1, 8,
                         fill=(lerp_c(col,'#FFF',0.85) if checked else '#F8F8F8'),
                         outline=col if checked else '#D5DBE8',
                         width=1.5, tags=tag)
            c.create_text((cx1+cx2)//2, (cy1+cy2)//2, text='✓' if checked else '○',
                          fill=col if checked else INK3,
                          font=('Arial', 11, 'bold'), tags=tag)
            c.tag_bind(tag, '<Button-1>', lambda e, idx=i: self._toggle_card(idx))
            y0 += bh + 12

    # ==================== 交互 ====================
    def _set_passes(self):
        self.passes = 3 if '3' in self.passes_var.get() else 7

    def _on_wheel(self, e):
        mx = max(0, len(self.groups)*95-220)
        self.scroll_y = max(0, min(self.scroll_y+(e.delta/120)*30, mx))

    def _clear_hover(self, kind):
        if kind=='seg': self.hover_seg=None; self._start_anim()
        else: self.hover_card=None; self._start_anim()

    def _on_motion_donut(self, e):
        if not self.groups: return
        dx=e.x-self.cx; dy=e.y-self.cy; d=math.hypot(dx,dy)
        seg=None
        if self.r_i-4 <= d <= self.r_o+15:
            ang=math.atan2(dy,dx)
            if ang<-math.pi/2: ang+=math.pi*2
            s=-math.pi/2; total=self.total_mb or 1
            for i,g in enumerate(self.groups):
                fr=g['size_mb']/total; end=s+fr*math.pi*2
                if s<=ang<=end or (i==len(self.groups)-1 and ang>=s): seg=i; break
                s=end
        if seg!=self.hover_seg: self.hover_seg=seg; self._start_anim()

    def _on_motion_cards(self, e):
        idx=None; y=26-self.scroll_y
        for i in range(len(self.groups)):
            if y<=e.y<=y+self.card_h and 8<=e.x<=self.canvas_cards.winfo_width()-8: idx=i; break
            y+=self.card_h+12
        if idx!=self.hover_card: self.hover_card=idx; self._start_anim()

    def _toggle_card(self, idx):
        self.checked[self.groups[idx]['name']]=not self.checked.get(self.groups[idx]['name'],True)

    def _uninstall_card(self, idx):
        n=self.groups[idx]['name']; self._toast('正在卸载 %s…'%n)
        threading.Thread(target=lambda: self.q.put(('uninstall_done',n,core.uninstall_app(n))),
                        daemon=True).start()

    # ==================== 动画引擎（ease-out · 收敛 · 短时长） ====================
    def _start_anim(self):
        if not self.anim_running: self.anim_running=True; self._animate()

    def _ease_out(self, t):
        """三次 ease-out。t ∈ [0,1] → [0,1]（速度递减）。"""
        return 1 - (1 - t) ** 3

    def _tick_to(self, key, vel_attr, goal, t_inc, threshold):
        """通用平滑插值到 goal，自动夹紧收敛。"""
        cur = getattr(self, key)
        vel = getattr(self, vel_attr)
        if abs(cur - goal) < threshold:
            cur = goal; vel = 0
        else:
            # ease-out 累进
            cur += (goal - cur) * t_inc
        setattr(self, key, cur)
        setattr(self, vel_attr, vel)

    def _animate(self):
        now=time.time(); n=len(self.groups)
        still_active = False

        # ---- 进入动画：生长弧（一次性短时长） ----
        enter_t = getattr(self, '_enter_time', 0)
        if enter_t:
            elapsed = now - enter_t
            ENTER_DUR = 0.35  # 全部完成不超过 0.35s
            all_done = True
            for i in range(n):
                delay = i * 0.025          # stagger 缩短到 25ms/段
                t = (elapsed - delay) / ENTER_DUR
                if t < 0:   v = 0.0
                elif t > 1: v = 1.0
                else:       v = self._ease_out(t)
                self.enter_grow[i] = v
                self.enter_grow_v[i] = 0
                if v < 0.999: all_done = False
            if all_done: self._enter_time = 0

        # ---- 段偏移（悬停 / 快速收敛） ----
        for i in range(n):
            goal = 2.5 if self.hover_seg == i else 0.0
            cur = self.seg_offset.get(i, 0.0)
            vel = self.seg_offset_v.get(i, 0.0)
            new_cur = cur + (goal - cur) * 0.35   # 大步插值 → 快速到位
            if abs(new_cur - goal) < 0.01:
                new_cur = goal; vel = 0
            else: vel = (goal - cur) * 0.35
            self.seg_offset[i] = new_cur; self.seg_offset_v[i] = vel
            if abs(new_cur - goal) > 0.005: still_active = True

        # ---- 卡片缩放 ----
        for i in range(n):
            goal = 1.025 if self.hover_card == i else 1.0
            cur = self.card_scale.get(i, 1.0)
            vel = self.card_scale_v.get(i, 0.0)
            new_cur = cur + (goal - cur) * 0.35
            if abs(new_cur - goal) < 0.002:
                new_cur = goal; vel = 0
            else: vel = (goal - cur) * 0.35
            self.card_scale[i] = new_cur; self.card_scale_v[i] = vel
            if abs(new_cur - goal) > 0.002: still_active = True

        # ---- 中央信息淡入淡出 ----
        goal_a = 1.0 if (self.hover_seg is not None and not enter_t) else 0.0
        cur_a = self.center_alpha; vel_a = self.center_alpha_v
        new_a = cur_a + (goal_a - cur_a) * 0.35
        if abs(new_a - goal_a) < 0.005: new_a = goal_a; vel_a = 0
        else: vel_a = (goal_a - cur_a) * 0.35
        self.center_alpha = new_a; self.center_alpha_v = vel_a
        if abs(new_a - goal_a) > 0.005: still_active = True

        # ---- 进度条平滑 ----
        for k in list(self.bar_goal.keys()):
            cur = self.bar_cur.get(k, 0)
            goal = self.bar_goal[k]
            new_cur = cur + (goal - cur) * 0.35
            if abs(new_cur - goal) < 1:
                new_cur = goal
            self.bar_cur[k] = new_cur; self.bar_cur_v[k] = (goal - cur) * 0.35
            if abs(new_cur - goal) > 1: still_active = True
            try:
                if k == 'main' and hasattr(self, 'prog_bar') and self.prog_bar.winfo_exists():
                    self.prog_bar.config(width=int(new_cur))
                elif k == 'sub' and hasattr(self, 'prog_subbar') and self.prog_subbar.winfo_exists():
                    self.prog_subbar.config(width=int(new_cur))
            except: pass

        self._draw_donut(); self._draw_cards()

        # 判定是否继续帧循环
        if enter_t or still_active:
            self.root.after(16, self._animate)
        else:
            self.anim_running = False

    # ==================== 扫描 ====================
    def do_scan(self):
        if self.scanning: return
        self.scanning=True; self.scanbar.pack(fill='x', padx=18, pady=(10,0))
        self._scan_bounce(0)
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_bounce(self, n):
        if not self.scanning: self.scanbar.pack_forget(); return
        W=max(self.root.winfo_width(),800); w=int(W*0.18)
        x=int(W*(0.5+0.5*math.sin(n/14))-w*0.5)
        self.scanbar_fill.place(x=x,y=0,width=w,relheight=1)
        self.root.after(24, self._scan_bounce, n+1)

    def _scan_worker(self):
        self.q.put(('scan_done', core.scan()))

    # ==================== 进程/清理（保持兼容） ====================
    def do_kill(self):
        self._toast('正在结束相关进程…')
        threading.Thread(target=lambda: self.q.put(('kill_done', core.terminate_processes())),
                        daemon=True).start()

    def _ask_confirm(self):
        gs=[g for g in self.groups if self.checked.get(g['name'],True)]
        if not gs: self._toast('请先勾选要清理的目标'); return
        if self.cleaning: return
        total=sum(g['size_mb'] for g in gs)
        win=tk.Toplevel(self.root); win.title('确认清理'); win.configure(bg=CARD)
        win.transient(self.root); win.grab_set()
        w,h=440,280
        win.geometry('%dx%d+%d+%d'%(w,h,
            self.root.winfo_x()+(self.root.winfo_width()-w)//2,
            self.root.winfo_y()+(self.root.winfo_height()-h)//2))
        tk.Label(win,text='确认执行安全清理？',bg=CARD,fg=INK,font=FONT_B).pack(anchor='w',padx=20,pady=(16,4))
        box=tk.Frame(win,bg='#FAFBFC',highlightbackground=LINE,highlightthickness=1)
        box.pack(fill='both',expand=True,padx=20,pady=4)
        for g in gs:
            tk.Label(box,text='• %s —— %s（%d 个目标）'%(g['name'],core.fmt_size(g['size_mb']),g['targets']),
                     bg='#FAFBFC',fg=INK2,font=FONT_S,anchor='w').pack(fill='x',padx=10,pady=2)
        tk.Label(box,text='合计 %s · 覆写 %d 次后删除，不可恢复！'%(core.fmt_size(total),self.passes),
                 bg='#FAFBFC',fg=DANGER,font=FONT_S,anchor='w').pack(fill='x',padx=10,pady=(8,2))
        btns=tk.Frame(win,bg=CARD); btns.pack(fill='x',padx=20,pady=12)
        tk.Button(btns,text='取消',command=win.destroy,bg='#F2F4F8',fg=INK2,
                  relief='flat',font=FONT_S,padx=14,pady=4).pack(side='right')
        tk.Button(btns,text='确认并开始',command=lambda:self._start_clean(win),
                  bg=DANGER,fg='white',relief='flat',font=FONT_B,padx=14,pady=4).pack(side='right',padx=(0,8))

    def _start_clean(self, w):
        w.destroy(); self.cleaning=True; self.cancel_evt.clear()
        gs=[g for g in self.groups if self.checked.get(g['name'],True)]
        paths=[]; [paths.extend(g['paths']) for g in gs]
        self._open_progress()
        threading.Thread(target=self._clean_worker, args=(paths,), daemon=True).start()

    def _open_progress(self):
        win=tk.Toplevel(self.root); win.title('正在安全清理'); win.configure(bg=CARD)
        win.transient(self.root); win.grab_set()
        w,h=460,230
        win.geometry('%dx%d+%d+%d'%(w,h,
            self.root.winfo_x()+(self.root.winfo_width()-w)//2,
            self.root.winfo_y()+(self.root.winfo_height()-h)//2))
        win.protocol('WM_DELETE_WINDOW',lambda:None); self.prog_win=win
        head=tk.Frame(win,bg=CARD); head.pack(fill='x',padx=20,pady=(16,8))
        self.prog_title=tk.Label(head,text='准备…',bg=CARD,fg=INK,font=FONT_B)
        self.prog_title.pack(anchor='w')
        self.prog_sub=tk.Label(head,text='',bg=CARD,fg=INK3,font=FONT_S)
        self.prog_sub.pack(anchor='w',pady=(2,0))
        # 进度条容器
        bar_bg=tk.Frame(win,bg='#ECF0F5',height=12)
        bar_bg.pack(fill='x',padx=20)
        self.prog_bar=tk.Frame(bar_bg,bg=PRIMARY,width=0,height=12)
        self.prog_bar.pack(side='left',fill='y')
        sub_bg=tk.Frame(win,bg='#ECF0F5',height=6)
        sub_bg.pack(fill='x',padx=20,pady=(6,0))
        self.prog_subbar=tk.Frame(sub_bg,bg=GREEN,width=0,height=6)
        self.prog_subbar.pack(side='left',fill='y')
        self.prog_pct=tk.Label(win,text='0%',bg=CARD,fg=PRIMARY,font=FONT_B)
        self.prog_pct.pack(anchor='w',padx=20,pady=(4,0))
        btns=tk.Frame(win,bg=CARD); btns.pack(fill='x',padx=20,pady=10)
        tk.Button(btns,text='取消',command=self._cancel_clean,bg='#F2F4F8',fg=INK2,
                  relief='flat',font=FONT_S,padx=12,pady=4).pack(side='right')

    def _cancel_clean(self): self.cancel_evt.set()

    def _clean_worker(self, paths):
        targets=[t for t in core.scan() if t['path'] in set(paths)]
        total=len(targets); results=[]
        for i,t in enumerate(targets):
            if self.cancel_evt.is_set(): results.append({'path':t['path'],'ok':False,'cancel':True}); break
            self.q.put(('clean_item',i+1,total,t['app']))
            idx,tn=i+1,total
            def cb(fp,cur,alln):
                if alln==0: return
                if cur%40==0 or cur==alln: self.q.put(('clean_file',idx,tn,cur,alln))
            ok=core.secure_delete_target(t,self.passes,progress_cb=cb)
            results.append({'path':t['path'],'ok':ok})
        self.q.put(('clean_done',results))

    # ==================== 队列轮询 ====================
    def _poll(self):
        try:
            while True: self._handle(self.q.get_nowait())
        except queue.Empty: pass
        self.root.after(100, self._poll)

    def _handle(self, msg):
        kind=msg[0]
        if kind=='scan_done':
            self.targets=msg[1]; self.groups=core.group_targets(self.targets)
            self.total_mb=sum(g['size_mb'] for g in self.groups)
            for g in self.groups: self.checked.setdefault(g['name'],True)
            self.scanning=False; self.scanbar.pack_forget()
            # 重置动画状态（轻度入场，避免夸张）
            for i in range(len(self.groups)):
                self.enter_grow[i]=0.0
                self.seg_offset[i]=0.0
                self.card_scale[i]=0.92          # 几乎全尺寸入场
            self._enter_time=time.time()
            self.center_alpha=0.0
            self._start_anim()
            if not self.groups: self._toast('未发现可清理数据')
        elif kind=='kill_done':
            k=msg[1]
            self._toast('已结束: '+(','.join(k[:5])+('等'if len(k)>5 else '') if k else '无相关进程'))
        elif kind=='uninstall_done':
            n,r=msg[1],msg[2]
            self._toast('%s: %s'%(n,r.get('message','完成') if r['status']=='ok' else '失败'))
        elif kind=='toast': self._toast(msg[1])
        elif kind=='clean_item':
            try:
                if hasattr(self,'prog_win') and self.prog_win.winfo_exists():
                    self.prog_title.config(text='正在覆写: '+msg[3])
                    self.prog_sub.config(text='第 %d/%d 项'%(msg[1],msg[2]))
            except: pass
        elif kind=='clean_file':
            try:
                if hasattr(self,'prog_win') and self.prog_win.winfo_exists():
                    cur,total,fcur,fall=msg[1],msg[2],msg[3],msg[4]
                    bw=400*0.6
                    self.bar_goal['main']=int(bw*cur/total) if total else 0
                    self.prog_pct.config(text='%d%%'%(cur*100//total if total else 0))
                    if fall: self.bar_goal['sub']=int(bw*fcur/fall)
                    self._start_anim()
            except: pass
        elif kind=='clean_done':
            results=msg[1]; ok=sum(1 for r in results if r.get('ok'))
            fail=sum(1 for r in results if not r.get('ok'))
            self.cleaning=False; self._close_progress()
            self.bar_goal.clear(); self._toast('完成: %d 成功, %d 失败'%(ok,fail))
            self.do_scan()

    def _close_progress(self):
        try:
            if hasattr(self,'prog_win'): self.prog_win.destroy()
        except: pass

    def _toast(self, text):
        try:
            if hasattr(self,'_tw') and self._tw.winfo_exists(): self._tw.destroy()
            w=tk.Toplevel(self.root); w.overrideredirect(True); w.configure(bg=ink_dark(INK))
            tk.Label(w,text=text,bg=ink_dark(INK),fg='white',font=FONT_S,padx=20,pady=10).pack()
            w.update_idletasks()
            x=self.root.winfo_x()+(self.root.winfo_width()-w.winfo_width())//2
            y=self.root.winfo_y()+self.root.winfo_height()-72
            w.geometry('+%d+%d'%(x,y+26)); w.lift(); self._tw=w
            self._toast_slide(w, y, 0)
            self.root.after(2800, lambda: w.destroy() if w.winfo_exists() else None)
        except: pass

    def _toast_slide(self, w, ty, step):
        if not w.winfo_exists(): return
        try:
            cy=w.winfo_y(); ny=cy+(ty-cy)*0.32
            if abs(ny-ty)<1: ny=ty
            w.geometry('+%d+%d'%(w.winfo_x(),int(ny)))
            if abs(ny-ty)>0.5: w.after(16,lambda:self._toast_slide(w,ty,step+1))
        except: pass

    def _on_close(self): self.root.destroy()


def ink_dark(hexc):
    r=int(hexc[1:3],16)//3; g=int(hexc[3:5],16)//3; b=int(hexc[5:7],16)//3
    return '#%02X%02X%02X'%(r,g,b)

def _dbg(msg):
    try:
        base=os.path.dirname(sys.executable) if getattr(sys,'frozen',False) else os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(base,'app_debug.log'),'a',encoding='utf-8')as f:
            f.write('[%s] %s\n'%(time.strftime('%H:%M:%S'),msg))
    except: pass

def resource_path(rel):
    base=getattr(sys,'_MEIPASS',os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base,rel)

def main():
    try: import ctypes; ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except: pass
    _dbg('=== 启动 ===')
    try:
        root=tk.Tk(); _dbg('Tk 根窗口已创建')
        OffboardGUI(root); _dbg('界面构建完成，进入主循环')
        root.mainloop(); _dbg('主循环退出')
    except Exception as e:
        import traceback; _dbg('异常: %r\n%s'%(e,traceback.format_exc())); raise

if __name__=='__main__':
    main()
