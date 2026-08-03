# -*- coding: utf-8 -*-
"""CLI 自测：验证后端扫描/进程/覆写逻辑（不启动 GUI）"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import offboard_app as app

print('== 扫描测试 ==')
targets = app.scan()
print('目标数:', len(targets))
total = sum(t['size'] for t in targets)
print('总大小 MB:', round(total / 1048576, 1))
for t in targets[:6]:
    print('  -', t['app'], '|', t['type'], '|', t['size_mb'], 'MB |', t['files'], 'files')
print('  ...' if len(targets) > 6 else '')

print('== 管理员检测 ==', app.is_admin())

print('== 运行进程检测 ==', app.running_processes())

print('== 覆写删除单元测试 ==')
# 创建临时文件验证 overwrite_file
td = tempfile.mkdtemp()
tf = os.path.join(td, 'test.dat')
with open(tf, 'wb') as f:
    f.write(os.urandom(1024 * 64))  # 64KB
before = os.path.getsize(tf)
ok = app.overwrite_file(tf, 3)
print('  覆写删除 64KB 文件:', ok, '| 已删除:', not os.path.exists(tf))

# 目录级安全删除测试
sub = os.path.join(td, 'subdir')
os.makedirs(sub)
with open(os.path.join(sub, 'a.db'), 'wb') as f:
    f.write(os.urandom(4096))
with open(os.path.join(sub, 'a.db-wal'), 'wb') as f:
    f.write(os.urandom(2048))
tgt = {'path': sub, 'type': 'dir'}
ok2 = app.secure_delete_target(tgt, 3)
print('  目录级覆写删除:', ok2, '| 已删除:', not os.path.exists(sub))
os.rmdir(td)
print('== 全部自测通过 ==')
