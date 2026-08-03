<#
================================================================================
 OffboardCleaner.ps1  ——  离职数据安全清理工具
--------------------------------------------------------------------------------
 功能：安全擦除微信 / QQ / 企业微信本地聊天记录，
       以及 Chrome / Edge 浏览器保存的密码与浏览记录（Cookies / History）。
       擦除方式：对每个文件执行【随机数据覆盖 N 次 + 全零覆盖 1 次】后删除，
       可有效阻止常规数据恢复工具（Recuva、WinHex、EaseUS 等）恢复内容。

 用法：
   扫描清单（默认，只读不删）:
     powershell -ExecutionPolicy Bypass -File OffboardCleaner.ps1 -Scan

   执行安全擦除（需输入 DELETE 确认）:
     powershell -ExecutionPolicy Bypass -File OffboardCleaner.ps1 -Execute

   交互菜单模式（双击"启动清理工具.bat"进入）:
     powershell -ExecutionPolicy Bypass -File OffboardCleaner.ps1 -Interactive

   高级参数:
     -Passes 7           覆盖次数（默认 3，越大越慢越彻底）
     -KillProcess        自动结束微信/QQ/企业微信/浏览器进程后再清理
     -WipeFreeSpace      清理后用 cipher /w 覆写磁盘空闲空间（需管理员，仅对机械硬盘有效）
     -LogFile 路径       自定义日志文件位置

 重要说明：
   1. 操作不可逆！执行前请确认已无需要保留的数据。
   2. 仅清理本机本地数据；微信/QQ 的云端与漫游记录需在应用内另行删除。
   3. 固态硬盘(SSD)因磨损均衡机制，覆写无法保证物理级擦除。
      彻底方案：全盘启用 BitLocker 加密并删除恢复密钥 / 使用厂商 Secure Erase。
   4. 若系统开启了"系统还原/卷影副本"，删除的文件可能残留在 VSS 快照，
      可在"磁盘清理→清理系统文件→更多选项→系统还原"中清除。
   5. 企业/公司电脑请先确认符合公司信息安全与离职交接政策。
================================================================================
#>
[CmdletBinding()]
param(
    [switch]$Scan,          # 仅扫描并列出目标（默认行为，只读）
    [switch]$Execute,       # 执行安全擦除（需输入 DELETE 确认）
    [switch]$Interactive,   # 交互菜单模式
    [switch]$KillProcess,   # 自动结束相关应用进程
    [switch]$WipeFreeSpace, # 擦除后运行 cipher /w 覆写空闲空间
    [int]$Passes = 3,       # 随机覆盖次数
    [string]$LogFile = ""   # 日志文件（默认: 脚本同目录 OffboardCleaner_<时间戳>.log）
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

# ============================ 目标清单（白名单） ============================
# 仅允许清理以下明确定义的路径，杜绝模糊删除。
$AppTargets = @(
    # ---- 微信 ----
    [PSCustomObject]@{ App = '微信(新版4.x数据)';        Path = "$env:APPDATA\Tencent\xwechat" },
    [PSCustomObject]@{ App = '微信(配置)';               Path = "$env:APPDATA\Tencent\WeChat" },
    [PSCustomObject]@{ App = '微信(旧版聊天记录)';       Path = "$env:USERPROFILE\Documents\WeChat Files" },
    [PSCustomObject]@{ App = '微信(新版聊天记录文件)';   Path = "$env:USERPROFILE\Documents\xwechat_files" },
    # ---- QQ ----
    [PSCustomObject]@{ App = 'QQ(配置/本地数据)';        Path = "$env:APPDATA\Tencent\QQ" },
    [PSCustomObject]@{ App = 'QQ(聊天记录)';             Path = "$env:USERPROFILE\Documents\Tencent Files" },
    # ---- 企业微信 ----
    [PSCustomObject]@{ App = '企业微信(聊天记录/文件)';  Path = "$env:USERPROFILE\Documents\WXWork" },
    [PSCustomObject]@{ App = '企业微信(配置)';           Path = "$env:APPDATA\Tencent\WXWork" }
)

# 浏览器：按文件级清理（密码 / 历史 / Cookie / 自动填充），不动书签与扩展。
$BrowserFileNames = @(
    'Login Data','Login Data-journal','Login Data For Account',          # 保存的密码
    'Local State',                                                        # 含密码加密密钥(DPAPI包装)，删除后旧密码永久无法解密
    'History','History-journal','Visited Links',                          # 浏览历史
    'Cookies','Cookies-journal','Network\Cookies','Network\Cookies-journal', # Cookie
    'Web Data','Web Data-journal','Web Data Lock'                         # 自动填充表单
)
$BrowserRoots = @(
    "$env:LOCALAPPDATA\Google\Chrome\User Data",
    "$env:LOCALAPPDATA\Microsoft\Edge\User Data"
)
$BrowserProfiles = @('Default','Profile 1','Profile 2','Profile 3')

# 相关应用进程名（用于 -KillProcess）
$ProcNames = @('WeChat','Weixin','WeChatAppEx','WeChatApp','WeixinAppEx',
               'QQ','QQExternal','QQProtect','QQMusic',
               'WXWork','WXWorkUpdate','WXWorkWeb',
               'chrome','msedge')

# ============================ 日志 ============================
if (-not $LogFile) { $LogFile = Join-Path $PSScriptRoot ("OffboardCleaner_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.log') }

function Write-Log {
    param([string]$Message, [string]$Level = 'INFO')
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format 'HH:mm:ss'), $Level, $Message
    Write-Host $line
    Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue
}

function Write-Warn { Write-Log -Message $args[0] -Level 'WARN' }

# ============================ 辅助函数 ============================
function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-ProcessRunning {
    $found = @()
    foreach ($n in $ProcNames) {
        if (Get-Process -Name $n -ErrorAction SilentlyContinue) { $found += $n }
    }
    return $found
}

function Get-DirSize {
    param([string]$Path)
    try {
        $sum = (Get-ChildItem -LiteralPath $Path -Recurse -Force -File -ErrorAction SilentlyContinue |
                Measure-Object -Property Length -Sum).Sum
        if ($sum) { return [math]::Round($sum / 1MB, 1).ToString() + ' MB' }
        return '0 MB'
    } catch { return '?' }
}

function Get-DirFileCount {
    param([string]$Path)
    try {
        $c = @(Get-ChildItem -LiteralPath $Path -Recurse -Force -File -ErrorAction SilentlyContinue).Count
        return $c
    } catch { return 0 }
}

function Clear-ItemAttributes {
    param([System.IO.FileSystemInfo]$Item)
    try {
        $attrs = $Item.Attributes
        $attrs = $attrs -band (-bnot [System.IO.FileAttributes]::ReadOnly)
        $attrs = $attrs -band (-bnot [System.IO.FileAttributes]::Hidden)
        $attrs = $attrs -band (-bnot [System.IO.FileAttributes]::System)
        $Item.Attributes = $attrs
    } catch { }
}

# 覆写单个文件：随机数据 Passes 次 + 全零 1 次，然后删除
function Write-OverwriteFile {
    param([string]$Path, [int]$Passes)
    try {
        $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
        if ($item.PSIsContainer) { return $false }
        $length = $item.Length

        if ($length -gt 0) {
            $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open,
                                          [System.IO.FileAccess]::Write,
                                          [System.IO.FileShare]::None)
            try {
                $rng    = [System.Security.Cryptography.RandomNumberGenerator]::Create()
                $buf    = New-Object byte[] (1024 * 1024)   # 1MB 块
                $bufLen = $buf.Length

                for ($p = 1; $p -le $Passes; $p++) {
                    $fs.Position = 0
                    $remaining   = $length
                    while ($remaining -gt 0) {
                        $chunk = [int][Math]::Min($bufLen, $remaining)
                        $rng.GetBytes($buf, 0, $chunk)
                        $fs.Write($buf, 0, $chunk)
                        $remaining -= $chunk
                    }
                    $fs.Flush($true)          # 强制写入物理磁盘
                }
                # 最后全零覆盖
                $fs.Position = 0
                $remaining   = $length
                [Array]::Clear($buf, 0, $bufLen)
                while ($remaining -gt 0) {
                    $chunk = [int][Math]::Min($bufLen, $remaining)
                    $fs.Write($buf, 0, $chunk)
                    $remaining -= $chunk
                }
                $fs.Flush($true)
            } finally { $fs.Close() }
        }
        Clear-ItemAttributes $item
        Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
        return $true
    } catch {
        Write-Log -Message ("  文件覆盖失败: {0}  ->  {1}" -f $Path, $_.Exception.Message) -Level 'WARN'
        return $false
    }
}

# 安全删除目录：递归覆盖其中所有文件后删除目录树（跳过重解析点防误删链接目标）
function Remove-TargetDirectory {
    param([string]$Path, [int]$Passes)
    $root = Get-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
    if (-not $root) { return $true }

    if ($root.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
        # 符号链接/目录联接：只删链接本身，绝不递归进入链接目标
        try { Remove-Item -LiteralPath $Path -Force -ErrorAction Stop; return $true }
        catch { Write-Log -Message ("  删除链接失败: {0}" -f $Path) -Level 'WARN'; return $false }
    }

    $files = @(Get-ChildItem -LiteralPath $Path -Recurse -Force -File -ErrorAction SilentlyContinue)
    $total = $files.Count
    $done  = 0
    foreach ($f in $files) {
        $done++
        Write-Progress -Activity '安全覆写文件' -Status $f.FullName -PercentComplete ($done * 100 / [Math]::Max(1, $total))
        $null = Write-OverwriteFile -Path $f.FullName -Passes $Passes
    }
    Write-Progress -Activity '安全覆写文件' -Completed

    # 清只读/隐藏属性后删除目录树
    Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue | ForEach-Object {
        Clear-ItemAttributes $_
    }
    try {
        Clear-ItemAttributes $root
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return $true
    } catch {
        Write-Log -Message ("  目录删除失败: {0}  ->  {1}" -f $Path, $_.Exception.Message) -Level 'WARN'
        return $false
    }
}

# 收集全部存在的目标
function Get-ExistingTargets {
    $list = @()
    foreach ($t in $AppTargets) {
        if (Test-Path -LiteralPath $t.Path) {
            $isDir = (Get-Item -LiteralPath $t.Path -Force).PSIsContainer
            if ($isDir) {
                $list += [PSCustomObject]@{
                    App = $t.App; Path = $t.Path; Type = '目录'
                    Size = (Get-DirSize $t.Path); Files = (Get-DirFileCount $t.Path)
                }
            } else {
                $sz = (Get-Item -LiteralPath $t.Path -Force).Length
                $list += [PSCustomObject]@{
                    App = $t.App; Path = $t.Path; Type = '文件'
                    Size = [math]::Round($sz / 1KB, 1).ToString() + ' KB'; Files = 1
                }
            }
        }
    }
    foreach ($root in $BrowserRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        foreach ($profile in $BrowserProfiles) {
            $profDir = Join-Path $root $profile
            if (-not (Test-Path -LiteralPath $profDir)) { continue }
            foreach ($fname in $BrowserFileNames) {
                $fp = Join-Path $profDir $fname
                if (Test-Path -LiteralPath $fp) {
                    $sz = (Get-Item -LiteralPath $fp -Force).Length
                    $list += [PSCustomObject]@{
                        App = (Split-Path $root -Leaf) + " / " + $profile
                        Path = $fp; Type = '文件'
                        Size = [math]::Round($sz / 1KB, 1).ToString() + ' KB'; Files = 1
                    }
                }
            }
        }
    }
    return $list
}

# ============================ 扫描（只读） ============================
function Invoke-Scan {
    Write-Log '================ 扫描结果（只读，未删除任何数据） ================'
    $targets = Get-ExistingTargets
    if ($targets.Count -eq 0) {
        Write-Log '未发现可清理的目标（相关应用可能未安装或数据已不存在）。'
        return @()
    }
    $totalMB = 0.0
    $i = 0
    foreach ($t in $targets) {
        $i++
        $sizeMB = 0.0
        if ($t.Size -match '^([\d.]+) MB$') { $sizeMB = [double]$Matches[1] }
        elseif ($t.Size -match '^([\d.]+) KB$') { $sizeMB = [double]$Matches[1] / 1024 }
        $totalMB += $sizeMB
        Write-Host ("  {0,3}. [{1}]  {2}" -f $i, $t.App, $t.Type) -ForegroundColor Cyan
        Write-Host ("       {0}" -f $t.Path) -ForegroundColor Gray
        Write-Host ("       大小: {0}    文件数: {1}" -f $t.Size, $t.Files) -ForegroundColor Gray
        Write-Log ("目标: {0} | {1} | {2} | {3} 个文件" -f $t.App, $t.Path, $t.Size, $t.Files)
    }
    Write-Log ("共 {0} 个目标，累计约 {1} MB（浏览器目标含密码/历史/Cookie 文件）" -f $targets.Count, [math]::Round($totalMB, 1))
    return $targets
}

# ============================ 执行安全擦除 ============================
function Invoke-Execute {
    Write-Log '================ 安全擦除开始 ================'
    $targets = Get-ExistingTargets
    if ($targets.Count -eq 0) { Write-Log '没有需要清理的目标。'; return }

    # 1) 进程检查
    $running = Get-ProcessRunning
    if ($running.Count -gt 0) {
        Write-Warn ("检测到正在运行的进程: {0}" -f ($running -join ', '))
        if ($KillProcess) {
            foreach ($n in $running) {
                Stop-Process -Name $n -Force -ErrorAction SilentlyContinue
                Write-Log ("已结束进程: {0}" -f $n)
            }
            Start-Sleep -Seconds 2
        } else {
            Write-Warn '请先手动关闭以上应用后重新执行；或使用 -KillProcess 参数自动结束进程。'
            return
        }
    }

    # 2) 打印清单并要求确认
    Write-Log '以下目标将被【永久安全删除】（覆写后删除，不可恢复）：'
    foreach ($t in $targets) {
        Write-Host ("  - [{0}] {1}  ({2})" -f $t.App, $t.Path, $t.Size) -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "⚠⚠ 此操作不可逆！请输入 DELETE 以继续，或直接回车取消：" -ForegroundColor Red
    $ans = Read-Host '确认'
    if ($ans -ne 'DELETE') { Write-Log '已取消，未删除任何数据。'; return }

    # 3) 逐个执行
    $ok = 0; $fail = 0
    foreach ($t in $targets) {
        Write-Log ("处理: {0}" -f $t.Path)
        if ($t.Type -eq '目录') {
            if (Remove-TargetDirectory -Path $t.Path -Passes $Passes) {
                Write-Log ("  完成: 目录已覆写并删除"); $ok++
            } else { $fail++ }
        } else {
            if (Write-OverwriteFile -Path $t.Path -Passes $Passes) {
                Write-Log ("  完成: 文件已覆写并删除"); $ok++
            } else { $fail++ }
        }
    }

    # 4) 可选：覆写空闲空间
    if ($WipeFreeSpace) {
        if (Test-IsAdmin) {
            $drive = (Split-Path -Path $env:USERPROFILE -Qualifier) + '\'
            Write-Log ("正在用 cipher /w 覆写空闲空间: {0}（可能需要较长时间）" -f $drive)
            cipher /w:$drive
            Write-Log 'cipher /w 完成。'
        } else {
            Write-Warn 'cipher /w 需要管理员权限，已跳过。请以管理员身份运行并加 -WipeFreeSpace 参数。'
        }
    }

    Write-Log ("安全擦除结束：成功 {0} 项，失败 {1} 项。日志: {2}" -f $ok, $fail, $LogFile)
    Write-Host ("`n==== 完成：成功 {0} 项 / 失败 {1} 项 ====" -f $ok, $fail) -ForegroundColor Green
    if ($fail -gt 0) {
        Write-Host '存在失败项（通常为文件被占用），请关闭相关应用后重试。' -ForegroundColor Red
    }
}

# ============================ 交互菜单 ============================
function Invoke-Interactive {
    Write-Host ''
    Write-Host '==============================================' -ForegroundColor Cyan
    Write-Host '  离职数据安全清理工具  OffboardCleaner' -ForegroundColor Cyan
    Write-Host '  覆盖次数: ' -NoNewline; Write-Host $Passes -ForegroundColor Yellow
    Write-Host '==============================================' -ForegroundColor Cyan
    while ($true) {
        Write-Host ''
        Write-Host '  1. 扫描并显示清理清单（只读）' -ForegroundColor White
        Write-Host '  2. 结束相关进程（微信/QQ/企业微信/浏览器）' -ForegroundColor White
        Write-Host '  3. 执行安全擦除（永久删除，需确认 DELETE）' -ForegroundColor Red
        Write-Host '  4. 覆写磁盘空闲空间 cipher /w（需管理员，机械硬盘适用）' -ForegroundColor White
        Write-Host '  0. 退出' -ForegroundColor White
        $c = Read-Host '  请选择'
        switch ($c) {
            '1' { $null = Invoke-Scan }
            '2' {
                $running = Get-ProcessRunning
                if ($running.Count -eq 0) { Write-Log '没有检测到相关进程在运行。' }
                else {
                    foreach ($n in $running) {
                        Stop-Process -Name $n -Force -ErrorAction SilentlyContinue
                        Write-Log ("已结束进程: {0}" -f $n)
                    }
                }
            }
            '3' { Invoke-Execute }
            '4' {
                if (Test-IsAdmin) {
                    $drive = (Split-Path -Path $env:USERPROFILE -Qualifier) + '\'
                    Write-Log ("cipher /w 覆写空闲空间: {0}（耗时较长）" -f $drive)
                    cipher /w:$drive
                } else {
                    Write-Warn '需要管理员权限。请右键脚本"以管理员身份运行"。'
                }
            }
            '0' { Write-Log '已退出。'; return }
            default { Write-Host '无效输入' -ForegroundColor Red }
        }
    }
}

# ============================ 入口 ============================
Write-Host '==============================================' -ForegroundColor Cyan
Write-Host ' 离职数据安全清理工具 OffboardCleaner  v1.0' -ForegroundColor Cyan
Write-Host (' 覆写次数: {0}  |  日志: {1}' -f $Passes, $LogFile) -ForegroundColor DarkGray
Write-Host '==============================================' -ForegroundColor Cyan

if (-not (Test-IsAdmin)) {
    Write-Warn '当前非管理员权限。普通清理可执行；cipher /w 覆写空闲空间需管理员。'
}

if ($Interactive) { Invoke-Interactive }
elseif ($Execute)  { Invoke-Execute }
else               { $null = Invoke-Scan }   # 默认：只读扫描
