# -*- coding: utf-8 -*-
"""生成 OffboardCleaner 扁平化图标：蓝色渐变圆角方块 + 白色分段环形图"""
from PIL import Image, ImageDraw

SIZE = 256
img = Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))
d = ImageDraw.Draw(img)

# 垂直渐变背景（#3B6FF5 -> #5A9CFF）
for y in range(SIZE):
    t = y / SIZE
    r = int(59 + (90 - 59) * t)
    g = int(111 + (156 - 111) * t)
    b = int(245 + (255 - 245) * t)
    d.line([(0, y), (SIZE, y)], fill=(r, g, b, 255))

# 圆角裁剪
mask = Image.new('L', (SIZE, SIZE), 0)
ImageDraw.Draw(mask).rounded_rectangle([8, 8, SIZE - 8, SIZE - 8], radius=54, fill=255)
img = Image.composite(img, Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0)), mask)

# 白色分段环形图（4 段，透明度递减，段间留缝）
d2 = ImageDraw.Draw(img)
cx = cy = SIZE // 2
r1, r2 = 92, 54
start = -90
for alpha in (255, 228, 200, 172):
    d2.pieslice([cx - r1, cy - r1, cx + r1, cy + r1], start + 3, start + 87,
                fill=(255, 255, 255, alpha))
    start += 90

# 中心小圆点强调
d2.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], fill=(255, 255, 255, 255))

img.save(r'C:\Users\Administrator\WorkBuddy\2026-08-03-09-16-48\offboard-cleaner\app\icon.ico',
         sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print('icon.ico 生成完成')
