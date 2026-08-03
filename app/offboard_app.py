# -*- coding: utf-8 -*-
"""
OffboardCleaner 核心引擎（无 GUI 依赖）
离职数据安全清理 —— 扫描 / 进程管理 / 安全覆写删除 / 空闲空间覆写
界面层由 offboard_gui.py（Tkinter）调用。
"""
import os
import sys
import stat
import time
import subprocess

# ============================ 目标清单（白名单） ============================
def _home():
    return os.path.expanduser('~')

def _appdata():
    return os.environ.get('APPDATA', os.path.join(_home(), 'AppData', 'Roaming'))

def _localappdata():
    return os.environ.get('LOCALAPPDATA', os.path.join(_home(), 'AppData', 'Local'))

def _documents():
    d = os.path.join(_home(), 'Documents')
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r'Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders')
        val, _ = winreg.QueryValueEx(key, 'Personal')
        winreg.CloseKey(key)
        val = val.replace('%USERPROFILE%', _home())
        if os.path.isdir(val):
            d = val
    except Exception:
        pass
    return d

APP_TARGETS = [
    ('微信（新版数据）',         os.path.join(_appdata(), 'Tencent', 'xwechat')),
    ('微信（配置）',             os.path.join(_appdata(), 'Tencent', 'WeChat')),
    ('微信（旧版聊天记录）',     os.path.join(_documents(), 'WeChat Files')),
    ('微信（聊天文件）',         os.path.join(_documents(), 'xwechat_files')),
    ('QQ（配置/数据）',          os.path.join(_appdata(), 'Tencent', 'QQ')),
    ('QQ（聊天记录）',           os.path.join(_documents(), 'Tencent Files')),
    ('企业微信（聊天记录/文件）', os.path.join(_documents(), 'WXWork')),
    ('企业微信（配置）',         os.path.join(_appdata(), 'Tencent', 'WXWork')),
]

BROWSER_FILE_NAMES = [
    'Login Data', 'Login Data-journal', 'Login Data For Account',
    'Local State',
    'History', 'History-journal', 'Visited Links',
    'Cookies', 'Cookies-journal', 'Network\\Cookies', 'Network\\Cookies-journal',
    'Web Data', 'Web Data-journal', 'Web Data Lock',
]

BROWSER_ROOTS = [
    os.path.join(_localappdata(), 'Google', 'Chrome', 'User Data'),
    os.path.join(_localappdata(), 'Microsoft', 'Edge', 'User Data'),
]
BROWSER_PROFILES = ['Default', 'Profile 1', 'Profile 2', 'Profile 3']

PROC_NAMES = ['WeChat', 'Weixin', 'WeChatAppEx', 'WeChatApp', 'WeixinAppEx',
              'QQ', 'QQExternal', 'QQProtect', 'QQMusic',
              'WXWork', 'WXWorkUpdate', 'WXWorkWeb',
              'chrome', 'msedge']

# ============================ 基础工具 ============================
def size_mb(n):
    return round(n / (1024 * 1024), 1)

def fmt_size(mb):
    if mb >= 1024:
        return '%.2f GB' % (mb / 1024)
    return '%g MB' % (round(mb * 10) / 10)

def dir_size(path):
    total = 0
    try:
        for root, _dirs, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    except OSError:
        pass
    return total

def dir_file_count(path):
    cnt = 0
    try:
        for _root, _dirs, files in os.walk(path):
            cnt += len(files)
    except OSError:
        pass
    return cnt

def is_admin():
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False

# ============================ 扫描 ============================
def scan():
    """返回存在且可清理的目标列表。"""
    targets = []
    for app_name, path in APP_TARGETS:
        if os.path.isdir(path):
            sz = dir_size(path)
            targets.append({'app': app_name, 'path': path, 'type': 'dir',
                            'size': sz, 'size_mb': size_mb(sz),
                            'files': dir_file_count(path)})
        elif os.path.isfile(path):
            sz = os.path.getsize(path)
            targets.append({'app': app_name, 'path': path, 'type': 'file',
                            'size': sz, 'size_mb': size_mb(sz), 'files': 1})

    for root in BROWSER_ROOTS:
        if not os.path.isdir(root):
            continue
        browser = 'Chrome' if 'Chrome' in root else 'Edge'
        for profile in BROWSER_PROFILES:
            pdir = os.path.join(root, profile)
            if not os.path.isdir(pdir):
                continue
            for fname in BROWSER_FILE_NAMES:
                fp = os.path.join(pdir, fname)
                if os.path.isfile(fp):
                    sz = os.path.getsize(fp)
                    targets.append({'app': '%s / %s' % (browser, profile), 'path': fp,
                                    'type': 'file', 'size': sz,
                                    'size_mb': size_mb(sz), 'files': 1})
    return targets


def group_targets(targets):
    """按应用聚合：{name: {'size_mb','targets','paths':[]}}，用于扇形图。"""
    groups = {}
    order = []
    for t in targets:
        key = t['app'].split(' / ')[0] if t['type'] == 'file' else t['app'].split('（')[0]
        if key not in groups:
            groups[key] = {'name': key, 'size_mb': 0.0, 'targets': 0, 'paths': []}
            order.append(key)
        groups[key]['size_mb'] += t['size_mb']
        groups[key]['targets'] += 1
        groups[key]['paths'].append(t['path'])
    groups = [groups[k] for k in order]
    groups.sort(key=lambda g: g['size_mb'], reverse=True)
    return groups

# ============================ 进程管理 ============================
def running_processes():
    found = []
    proc_lower = [p.lower() for p in PROC_NAMES]
    try:
        out = subprocess.run(['tasklist', '/FO', 'CSV', '/NH'],
                             capture_output=True, timeout=20,
                             encoding='gbk', errors='replace').stdout
        for line in out.splitlines():
            name = line.split('","')[0].strip('"')
            if name and name.lower().endswith('.exe'):
                base = name[:-4].lower()
                if base in proc_lower and name not in found:
                    found.append(name)
    except Exception:
        pass
    return found


def terminate_processes():
    killed = []
    for p in PROC_NAMES:
        try:
            subprocess.run(['taskkill', '/F', '/IM', p + '.exe', '/T'],
                           capture_output=True, timeout=15)
            killed.append(p + '.exe')
        except Exception:
            pass
    time.sleep(1.5)
    return killed

# ============================ 安全覆写删除 ============================
def _clear_attrs(path):
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def overwrite_file(path, passes):
    """单文件：随机数据覆盖 passes 次 + 全零 1 次，然后删除。"""
    try:
        _clear_attrs(path)
        length = os.path.getsize(path)
        if length > 0:
            with open(path, 'r+b', buffering=0) as f:
                buf = bytearray(1024 * 1024)
                for _ in range(passes):
                    f.seek(0)
                    remaining = length
                    while remaining > 0:
                        chunk = buf[:min(len(buf), remaining)]
                        chunk[:] = os.urandom(len(chunk))
                        f.write(chunk)
                        remaining -= len(chunk)
                    f.flush()
                    os.fsync(f.fileno())
                f.seek(0)
                remaining = length
                zero = bytearray(1024 * 1024)
                while remaining > 0:
                    c = min(len(zero), remaining)
                    f.write(zero[:c])
                    remaining -= c
                f.flush()
                os.fsync(f.fileno())
        os.remove(path)
        return True
    except OSError:
        return False


def secure_delete_target(target, passes, progress_cb=None):
    """删除目标（目录/文件）。目录：递归覆写所有文件后删目录树。"""
    path = target['path']
    if target.get('type') == 'dir':
        try:
            mode = os.lstat(path).st_mode
            if stat.S_ISLNK(mode):
                os.rmdir(path)
                return True
        except OSError:
            return False
        all_files = []
        try:
            for root, _dirs, files in os.walk(path):
                for f in files:
                    all_files.append(os.path.join(root, f))
        except OSError:
            pass
        total = len(all_files)
        ok = True
        for i, fp in enumerate(all_files):
            if progress_cb:
                progress_cb(fp, i + 1, total)
            if not overwrite_file(fp, passes):
                ok = False
        if ok:
            try:
                for root, dirs, files in os.walk(path, topdown=False):
                    for d in dirs:
                        _clear_attrs(os.path.join(root, d))
                    for f in files:
                        _clear_attrs(os.path.join(root, f))
                _clear_attrs(path)
                for root, dirs, files in os.walk(path, topdown=False):
                    for d in dirs:
                        try:
                            os.rmdir(os.path.join(root, d))
                        except OSError:
                            pass
                    for f in files:
                        try:
                            os.remove(os.path.join(root, f))
                        except OSError:
                            pass
                os.rmdir(path)
            except OSError:
                ok = False
        return ok
    else:
        if progress_cb:
            progress_cb(path, 1, 1)
        return overwrite_file(path, passes)


def wipe_free_space():
    drive = os.path.splitdrive(os.path.expanduser('~'))[0] + '\\'
    try:
        r = subprocess.run(['cipher', '/w:' + drive], capture_output=True, timeout=600)
        return r.returncode == 0
    except Exception:
        return False
