# -*- coding:utf-8 -*-
"""DevOps 默认巡检分段脚本资产(2026-09-16 新增)。

YAML 配置链路移除后,默认巡检脚本随代码发布;lifespan 在
``InspectionScriptService.preload_all`` 之后调用 ``seed_default_groups``
幂等播种(只插不改,保留人工编辑)。

结构契约:
    DEFAULT_INSPECTION_GROUPS: list[dict],每组::
        {
          "name": str,               # 组唯一标识(对应 inspection_scripts.name)
          "display_name": str,
          "platform": "linux" | "windows",
          "version": str,
          "inspection_parser": "json",
          "inspection_fields": list[dict],   # 字段规则(key/name_zh/unit/direction/warn/crit[/ssd_warn/ssd_crit])
          "segments": list[dict],            # 有序分段::
              {"segment_key": str, "display_name": str,
               "sort_order": int, "script": str}
        }

注意:脚本原文从 2026-08-15 版 inspection_scripts.yaml 逐行平移,
采集逻辑零改动,仅按「一段输出一个顶层 JSON object」重新组织输出语句。
"""
from __future__ import annotations

_LINUX_DISK_USAGE_SCRIPT = r"""#!/bin/bash
set -u
# 磁盘使用率分段:df -P 采集各分区使用率 + df -i 采集 inode 最大使用率。
# 不依赖 lsblk(老内核 / sandbox / cgroup 受限环境 lsblk 不可用);
# 直接从 df -P 第一列设备名按 Linux 命名规则推断 host_disk / partition。
# host_disk 命名空间与 disk-io 段对齐(/proc/diskstats 物理盘名),
# 保证 merge_inspection_fragments 后同 mount 的 usage + io 元素能正确分组:
#   - 物理盘正则:sd/vd/xvd/nvme/mmcblk/zram/dm-/loop/md/drbd
#   - 虚拟/网络设备(overlay/tmpfs/fuse.mergerfs/127.0.0.1:/vol/none 等) → hd="_orphan_"
#     (与 ops_report._server_disk_inventory_rows 的 _orphan_ 虚拟组语义对齐)
#   - 未识别但仍含设备名的元素 → hd=dev,part=""(保留兜底供未来新规则扩展)
DISKS=$(df -P | awk '
  BEGIN { sep="" }
  NR==1 || $1 ~ /^(tmpfs|devtmpfs|squashfs|sysfs|proc|cgroup|nsfs|autofs|fusectl|configfs|debugfs|tracefs|ramfs|mqueue|binfmt_misc|hugetlbfs|pstore|bpf)/ {next}
  NF < 6 {next}
  $5 !~ /^[0-9]+%?$/ {next}
  {
    gsub(/%/, "", $5)
    dev=$1; if (dev ~ /^\/dev\//) dev=substr(dev, 6)
    if (dev ~ /^(sd|vd|xvd)[a-z]+[0-9]+$/) {
      hd=substr(dev, 1, length(dev)-1); part=dev
    } else if (dev ~ /^nvme[0-9]+n[0-9]+p[0-9]+$/) {
      p=index(dev, "p"); hd=substr(dev, 1, p-1); part=dev
    } else if (dev ~ /^mmcblk[0-9]+p[0-9]+$/) {
      p=index(dev, "p"); hd=substr(dev, 1, p-1); part=dev
    } else if (dev ~ /^zram[0-9]+$/) {
      hd="zram"; part=dev
    } else if (dev ~ /^dm-[0-9]+$/) {
      hd=dev; part=""
    } else if (dev ~ /^loop[0-9]+$/) {
      hd=dev; part=""
    } else if (dev ~ /^md[0-9]+$/) {
      hd=dev; part=""
    } else if (dev ~ /^drbd[0-9]+$/) {
      hd=dev; part=""
    } else if (dev ~ /^(overlay|nsfs|autofs|fusectl|configfs|debugfs|hugetlbfs|mqueue|pstore|ramfs|securityfs|selinuxfs|squashfs|tracefs|none)$/ || dev ~ /^fuse\./ || dev ~ /^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+:/) {
      hd="_orphan_"; part=$6
    } else {
      hd=dev; part=""
    }
    printf "%s{\"mount\":\"%s\",\"host_disk\":\"%s\",\"partition\":\"%s\",\"disk_index\":0,\"disk_used_pct\":%s}", sep, $6, hd, part, $5
    sep=","
  }'
)
INODE_MAX=$(df -i 2>/dev/null | awk '
  NR==1 || $1 ~ /^(tmpfs|devtmpfs|overlay|squashfs|sysfs|proc|cgroup|nsfs|autofs|fusectl|configfs|debugfs|tracefs|ramfs|mqueue|binfmt_misc|hugetlbfs|pstore|bpf)/ {next}
  { gsub(/%/, "", $5); if($5+0>max) max=$5 }
  END { print max+0 }')
printf '{"disks":%s,"inode_used_pct":%s}\n' "[${DISKS}]" "$INODE_MAX"
"""

_LINUX_DISK_IO_SCRIPT = r"""#!/bin/bash
set -u
# 磁盘 IO 分段:读 /proc/diskstats 两次(间隔 1s),计算每块整盘的
# io_util_pct(=Δio_ms/10, 封顶100) 与 io_await_ms(=Δ读写ms/Δ读写次数);
# 介质探测走 /sys/block/<dev>/queue/rotational (1=hdd, 0=ssd),读取失败兜底 hdd。
IO_DEV_RE=' (sd[a-z]+|vd[a-z]+|xvd[a-z]+|nvme[0-9]+n[0-9]+|mmcblk[0-9]+) '
IO_S1=$(grep -E "$IO_DEV_RE" /proc/diskstats)
sleep 1
IO_S2=$(grep -E "$IO_DEV_RE" /proc/diskstats)
DEV_TYPES=$(for p in /sys/block/*; do
  d=${p##*/}
  case "$d" in
    sd*|vd*|xvd*|nvme[0-9]*n[0-9]*|mmcblk[0-9]*)
      rot=$(cat "$p/queue/rotational" 2>/dev/null || echo 1)
      if [ "$rot" = "0" ]; then t=ssd; else t=hdd; fi
      printf '%s:%s\n' "$d" "$t" ;;
  esac
done)
DISKS_IO=$(
  { printf '%s\n' "$DEV_TYPES" | awk '$0!=""{print "T", $0}'
    printf '%s\n' "$IO_S1" | awk '$0!=""{print "S1", $0}'
    printf '%s\n' "$IO_S2" | awk '$0!=""{print "S2", $0}'
  } | awk '
    $1=="T"  { split($2, kv, ":"); dtype[kv[1]]=kv[2]; next }
    $1=="S1" { io1[$4]=$14; rw1[$4]=$5+$9; t1[$4]=$8+$12; next }
    {
      dev=$4
      if (!(dev in io1)) next
      d_io=$14-io1[dev]; d_rw=($5+$9)-rw1[dev]; d_t=($8+$12)-t1[dev]
      util=d_io/10; if (util>100) util=100; if (util<0) util=0
      awaitms=(d_rw>0)? d_t/d_rw : 0
      mt=(dev in dtype)? dtype[dev] : "hdd"
      hd=dev; part=""
      label=dev "[" toupper(mt) "]"
      printf "%s{\"mount\":\"%s\",\"host_disk\":\"%s\",\"partition\":\"%s\",\"disk_index\":0,\"io_util_pct\":%.1f,\"io_await_ms\":%.1f,\"disk_type\":\"%s\"}", sep, label, hd, part, util, awaitms, mt
      sep=","
    }'
)
printf '{"disks":%s}\n' "[${DISKS_IO}]"
"""

_LINUX_MEMORY_SCRIPT = r"""#!/bin/bash
set -u
# 内存分段:mem_used_pct 用 available 而非 used(used 含 buff/cache);
# swap_used_pct 在 Swap total=0 时兜底 0。
MEM=$(free | awk '/Mem:/ {printf "%.0f", ($2-$7)/$2 * 100}')
SWAP=$(free | awk '/Swap:/ {if($2>0) printf "%.0f", $3/$2*100; else print 0}')
printf '{"mem_used_pct":%s,"swap_used_pct":%s}\n' "$MEM" "$SWAP"
"""

_LINUX_CPU_SCRIPT = r"""#!/bin/bash
set -u
# CPU 分段:/proc/stat 双采样(间隔 1s)计算 cpu_idle_pct / cpu_iowait_pct;
# 老版 POSIX 兼容(避免 bash4+ 进程替换),用临时文件 + 两份 cat。
PROCSTAT_T1=$(mktemp); PROCSTAT_T2=$(mktemp)
cat /proc/stat > "$PROCSTAT_T1"
sleep 1
cat /proc/stat > "$PROCSTAT_T2"
CPU_STATS=$(awk '
  BEGIN { t1u=0; t1i=0; t1w=0; t1t=0; done1=0; done2=0 }
  NR==FNR && /^cpu / {
    for (i=2;i<=11;i++) t1t+=$i
    t1i=$5+$6; t1w=$6; t1u=t1t-t1i; done1=1; next
  }
  NR!=FNR && /^cpu / && done1 {
    t2t=0; for (i=2;i<=11;i++) t2t+=$i
    t2i=$5+$6; t2w=$6; t2u=t2t-t2i
    du=t2u-t1u; di=t2i-t1i; dw=t2w-t1w; dt=du+di
    if (dt>0) {
      printf "%.1f %.1f", di/dt*100, dw/dt*100
    } else {
      printf "0 0"
    }
    done2=1
  }
' "$PROCSTAT_T1" "$PROCSTAT_T2")
rm -f "$PROCSTAT_T1" "$PROCSTAT_T2"
CPU_IDLE=$(echo "$CPU_STATS" | awk '{print $1}')
CPU_IOWAIT=$(echo "$CPU_STATS" | awk '{print $2}')
LOAD=$(cat /proc/loadavg | awk '{print $1}')
printf '{"cpu_idle_pct":%s,"cpu_iowait_pct":%s,"load_1m":%s}\n' "$CPU_IDLE" "$CPU_IOWAIT" "$LOAD"
"""

_LINUX_WEB_SERVER_SCRIPT = r"""#!/bin/bash
set -u
# Web 服务器分段(2026-09-16 晚新增):扫描本机所有 Tomcat 实例,
# 列出每个 Web 应用的状态 + 进程级 CPU/内存 + 端口 + worker 数 + 简易健康度。
#
# 扫描策略:
#   1) 常见安装路径枚举(/opt /usr/local /var/lib /home /root /srv),
#      找含 catalina.sh 的目录作为 CATALINA_HOME;
#   2) systemd unit 兜底(systemctl list-unit-files | grep -i tomcat);
#   3) 重复的 path 去重(同一 Tomcat 被多次发现时按 path 唯一)。
#
# 端口发现:从 server.xml 解析 <Connector port="N" ...> 的第一个 port 属性;
# 缺失时 fallback 8080。
#
# 应用枚举:ls $CATALINA_HOME/webapps/ 目录(排除 ROOT 与目录外的 war 源文件),
# 对每个应用查进程是否存在(JPS 不可用时退到 ps -ef | grep 拿 tomcat pid)。
#
# 指标采集:进程级 CPU/内存用 ps -o pcpu,rss -p <pid>;QPS/响应时间无
# JMX 时降级 0(null/0 不算异常,与 nginx access log 解析留待后续扩展)。
#
# 输出形态(扁平化 web_apps 数组,评估器走 _ARRAY_EXPANSION_KEYS 路径):
#   {"web_apps":[
#     {"app_name":"ROOT","server_type":"tomcat","host":"tomcat@8080",
#      "port":8080,"status":"running","worker_count":200,
#      "web_app_qps":0.0,"web_app_avg_response_ms":0.0,
#      "web_app_cpu_pct":3.2,"web_app_mem_mb":512,
#      "jvm_heap_used_pct":null},
#     ...
#   ]}
#
# 元素键名与 inspection_fields 规则 key 一致(web_app_*),便于评估器按
# _expand_array 路径对每个元素重复评估同一条规则。
# 仅使用老版 POSIX 语法(避免 bash4+ 进程替换),与既有约束一致。
APPS_JSON=""
SEP=""
# 路径枚举:在常见安装根找 catalina.sh
CANDIDATES=$(for d in /opt /usr/local /var/lib /home /root /srv; do
  if [ -d "$d" ]; then
    find "$d" -maxdepth 5 -name catalina.sh -type f 2>/dev/null
  fi
done)
# systemd 兜底(若存在)
if command -v systemctl >/dev/null 2>&1; then
  while read -r unit; do
    [ -z "$unit" ] && continue
    exec_path=$(systemctl show "$unit" 2>/dev/null | grep -i '^ExecStart=' | head -1 | sed -e 's/^ExecStart=//' -e 's/ .*//')
    if [ -n "$exec_path" ]; then
      # 形如 /opt/tomcat/bin/catalina.sh → 退到 CATALINA_HOME
      bin_dir=$(dirname "$exec_path" 2>/dev/null)
      home_dir=$(dirname "$bin_dir" 2>/dev/null)
      if [ -f "$home_dir/bin/catalina.sh" ]; then
        echo "$home_dir/bin/catalina.sh"
      fi
    fi
  done <<< "$(systemctl list-unit-files 2>/dev/null | awk '/[Tt]omcat/{print $1}')"
fi
TOMCATS=$(printf '%s\n' "$CANDIDATES" | sort -u)
TOMCAT_COUNT=0
APP_COUNT=0
for cat_sh in $TOMCATS; do
  CATALINA_HOME=$(dirname "$(dirname "$cat_sh")")
  [ -d "$CATALINA_HOME/webapps" ] || continue
  # 端口发现:server.xml 第一个 Connector 的 port 属性(简单 awk 正则)
  PORT=$(awk 'tolower($0) ~ /<connector/ {
    match($0, /port="[0-9]+"/); if (RSTART) { print substr($0, RSTART+6, RLENGTH-7); exit }
  }' "$CATALINA_HOME/conf/server.xml" 2>/dev/null)
  PORT=${PORT:-8080}
  # tomcat 进程 PID:ps -ef 找包含 catalina.home 路径的进程
  PID=$(ps -ef 2>/dev/null | awk -v home="$CATALINA_HOME" '$0 ~ home && $0 ~ /catalina/ && $0 !~ /awk/ {print $2; exit}')
  # 进程级 CPU/内存(RSS KB → MB)
  if [ -n "$PID" ] && [ "$PID" != "0" ]; then
    PROC_LINE=$(ps -o pcpu= -o rss= -p "$PID" 2>/dev/null | tr -s ' ')
    CPU_PCT=$(echo "$PROC_LINE" | awk '{print $1+0}')
    MEM_MB=$(echo "$PROC_LINE" | awk '{printf "%.0f", $2/1024}')
    STATUS="running"
  else
    CPU_PCT="0"
    MEM_MB="0"
    STATUS="stopped"
  fi
  HOST="tomcat@${PORT}"
  # 应用枚举:webapps/ 下每个子目录名(排除 ROOT 之外的非应用如 work / docs);
  # 简化策略:只取目录,且目录里有 WEB-INF/web.xml 的才视为 Web 应用。
  for app_dir in "$CATALINA_HOME/webapps"/*; do
    [ -d "$app_dir" ] || continue
    name=$(basename "$app_dir")
    case "$name" in
      work|docs|examples|host-manager|manager) continue ;;  # 排除 tomcat 自带非业务目录
    esac
    if [ -f "$app_dir/WEB-INF/web.xml" ] || [ -d "$app_dir/WEB-INF" ]; then
      APP_COUNT=$((APP_COUNT+1))
      APP_STATUS="$STATUS"
      APP_CPU="$CPU_PCT"
      APP_MEM="$MEM_MB"
      # 简化版:每 Tomcat 所有应用共享进程级 CPU/内存;QPS/响应时间无 JMX 时固定 0
      APPS_JSON="${APPS_JSON}${SEP}{\"app_name\":\"${name}\",\"server_type\":\"tomcat\",\"host\":\"${HOST}\",\"port\":${PORT},\"status\":\"${APP_STATUS}\",\"worker_count\":200,\"web_app_qps\":0.0,\"web_app_avg_response_ms\":0.0,\"web_app_cpu_pct\":${APP_CPU},\"web_app_mem_mb\":${APP_MEM},\"jvm_heap_used_pct\":null}"
      SEP=","
    fi
  done
  TOMCAT_COUNT=$((TOMCAT_COUNT+1))
done
printf '{"web_apps":[%s],"tomcat_count":%s,"app_count":%s}\n' "$APPS_JSON" "$TOMCAT_COUNT" "$APP_COUNT"
"""

# Windows 单引号字符串中不能出现单引号,因此用 [CHAR39] 占位,在执行前替换。
# 这是为了在保持 PowerShell 兼容(避免双引号转义陷阱)的同时,允许脚本内嵌
# 含单引号的字符串(如 Replace('\', '\\') 中的反斜杠需要双写)。
_WINDOWS_QUOTE = "[CHAR39]"

_WINDOWS_DISK_USAGE_SCRIPT = r"""$diskIndexMap=@{}
try {
  gwmi Win32_DiskDrive | ForEach-Object {
    $did=[string]$_.DeviceID
    if ($did -match 'PHYSICALDRIVE(\d+)') { $diskIndexMap[$did]=[int]$Matches[1] }
    else { $diskIndexMap[$did]=-1 }
  }
} catch {}
$driveToDiskIndex=@{}
gwmi Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Where-Object { $_.Name -ne '_Total' } | ForEach-Object {
  $inst=[string]$_.Name
  if ($inst -match '^(\d+)\s') {
    $idx=[int]$Matches[1]
    $rest=$inst.Substring($Matches[0].Length)
    foreach ($p in ($rest -split '\s+')) {
      if ($p -match '^[A-Za-z]:(\[|$)') {
        $driveToDiskIndex[$p.Substring(0,2).ToUpper()] = $idx
      }
    }
  }
}
$diskParts=@()
Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -ne $null -and $_.Free -ne $null -and ($_.Used+$_.Free)-gt 0 } | ForEach-Object {
  $up=[math]::Round(($_.Used/($_.Used+$_.Free))*100, 1)
  $m=$_.Root.Replace('\','\\').Replace('"','\"')
  $d=$_.Root.Substring(0,1).ToUpper()
  $hd=''; $di=0; $pt=''
  if ($driveToDiskIndex.ContainsKey($d+':')) {
    $di=$driveToDiskIndex[$d+':']
    $hd='PHYSICALDRIVE'+$di
    $pt=$d+':'
  }
  $diskParts += '{"mount":"'+$m+'","host_disk":"'+$hd+'","partition":"'+$pt+'","disk_index":'+$di+',"disk_used_pct":'+$up+'}'
}
$inodeMax=0.0
try {
  foreach ($d in @(Get-PSDrive -PSProvider FileSystem)) {
    $dl=$d.Root.Substring(0,1)
    $info=& fsutil fsinfo ntfsinfo ($dl+':') 2>$null
    if ($info) {
      $mt=0; $mu=0
      foreach ($l in $info) {
        if ($l -match 'Mft Total\s+:\s+(\d+)') { $mt=[int]$Matches[1] }
        if ($l -match 'Mft User Mft Records\s+:\s+(\d+)') { $mu=[int]$Matches[1] }
      }
      if ($mt -gt 0) {
        $pc=[math]::Round(($mu/$mt)*100, 1)
        if ($pc -gt $inodeMax) { $inodeMax=$pc }
      }
    }
  }
} catch {}
Write-Output ('{"disks":['+($diskParts -join ',')+'],"inode_used_pct":'+$inodeMax+'}')
"""

_WINDOWS_DISK_IO_SCRIPT = r"""$mediaMap=@{}
try {
  gwmi -Namespace root\Microsoft\Windows\Storage -Class MSFT_PhysicalDisk -ErrorAction Stop | ForEach-Object {
    if ($_.MediaType -eq 4) { $mediaMap[[string]$_.DeviceId]='ssd' } else { $mediaMap[[string]$_.DeviceId]='hdd' }
  }
} catch {}
$ioParts=@()
gwmi Win32_PerfFormattedData_PerfDisk_PhysicalDisk | Where-Object { $_.Name -ne '_Total' } | ForEach-Object {
  $in=[string]$_.Name
  $dev=($in -split ' ')[0]
  $mt='hdd'
  if ($mediaMap.ContainsKey($dev)) { $mt=$mediaMap[$dev] }
  $ut=[int]$_.PercentDiskTime
  if ($ut -gt 100) { $ut=100 }
  if ($ut -lt 0) { $ut=0 }
  $aw=[math]::Round(([double]$_.AvgDiskSecPerTransfer*1000), 1)
  $lb=($in+'['+$mt.ToUpper()+']').Replace('\','\\').Replace('"','\"')
  $hd=''; $di=0
  if ($in -match '^(\d+)\s') { $di=[int]$Matches[1]; $hd='PHYSICALDRIVE'+$di }
  $ioParts += '{"mount":"'+$lb+'","host_disk":"'+$hd+'","partition":"","disk_index":'+$di+',"io_util_pct":'+$ut+',"io_await_ms":'+$aw+',"disk_type":"'+$mt+'"}'
}
Write-Output ('{"disks":['+($ioParts -join ',')+']}')
"""

_WINDOWS_MEMORY_SCRIPT = r"""$os=gwmi Win32_OperatingSystem
$mem=[math]::Round((($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize)*100, 1)
$sw=0.0
try {
  $pf=@(gwmi Win32_PageFileUsage)
  $al=0; $us=0
  foreach ($p in $pf) { $al+=[int]$p.AllocatedBaseSize; $us+=[int]$p.CurrentUsage }
  if ($al -gt 0) {
    $sw=[math]::Round(($us/$al)*100, 1)
    if ($sw -lt 0) { $sw=0 }
    if ($sw -gt 100) { $sw=100 }
  }
} catch {}
Write-Output ('{"mem_used_pct":'+$mem+',"swap_used_pct":'+$sw+'}')
"""

_WINDOWS_CPU_SCRIPT = r"""$proc=gwmi Win32_Processor
$cpu=($proc | Measure-Object -Property LoadPercentage -Average).Average
$iw=0.0
try {
  $ps=@(gwmi Win32_PerfFormattedData_PerfOS_Processor | Where-Object { $_.Name -ne '_Total' })
  if ($ps.Count -gt 0) {
    $si=0.0; $sd=0.0
    foreach ($p in $ps) { $si+=[double]$p.PercentInterruptTime; $sd+=[double]$p.PercentDPCTime }
    $iw=[math]::Round(($si+$sd)/$ps.Count, 1)
    if ($iw -lt 0) { $iw=0 }
    if ($iw -gt 100) { $iw=100 }
  }
} catch {}
Write-Output ('{"cpu_used_pct":'+[int]$cpu+',"cpu_iowait_pct":'+$iw+'}')
"""

# 2026-09-16 晚:Windows web-server 段(JS 复合 PowerShell 字符串允许单引号),
# 扫描 IIS Site + AppPool + WebApplication,以及 Tomcat(服务或注册表路径)。
# 扁平化 web_apps 数组,走评估器 _ARRAY_EXPANSION_KEYS 路径。
_WINDOWS_WEB_SERVER_SCRIPT = r"""$appsJson=@()
$sep=''
# === IIS 部分 ===
$iisOk=$false
try {
  Import-Module WebAdministration -ErrorAction Stop
  $iisOk=$true
} catch {}
if ($iisOk) {
  try {
    $totalQps=0.0
    try { $totalQps=[double](Get-Counter -Counter '\Web Service(_Total)\Current Connections' -ErrorAction SilentlyContinue).CounterSamples[0].CookedValue } catch {}
    $sites=@(Get-Website -ErrorAction SilentlyContinue)
    foreach ($s in $sites) {
      $siteName=[string]$s.Name
      $bindings=[string]$s.Bindings
      $portMatch=[regex]::Match($bindings, ':(\d+)\b')
      $port=if ($portMatch.Success) { [int]$portMatch.Groups[1].Value } else { 80 }
      $state=[string]$s.State
      $status=if ($state -eq 'Started') { 'running' } else { 'stopped' }
      $webApps=@(Get-WebApplication -Site $siteName -ErrorAction SilentlyContinue)
      $appNames=@()
      if ($webApps.Count -gt 0) {
        foreach ($wa in $webApps) { $appNames += [string]$wa.Path.TrimStart('/') }
      }
      if ($appNames.Count -eq 0) { $appNames = @($siteName) }
      $pools=@(Get-WebAppPoolState -Name $siteName -ErrorAction SilentlyContinue)
      $workerCount=if ($pools.Count -gt 0) { $pools.Count } else { 1 }
      $procs=@()
      try { $procs=@(Get-Process -Name w3wp -ErrorAction SilentlyContinue) } catch {}
      $cpuSum=0.0; $memSum=0L; $procCount=0
      foreach ($pp in $procs) {
        try { $cpuSum+=[double]$pp.CPU; $memSum+=[int64]$pp.WorkingSet64; $procCount++ } catch {}
      }
      $appCpu=0.0; $appMem=0
      if ($procCount -gt 0) { $appCpu=[math]::Round($cpuSum/$procCount, 1); $appMem=[int]([math]::Round($memSum/$procCount/1MB)) }
      $appQps=[math]::Round($totalQps, 1)
      $appResp=0.0
      try {
        $resp=[double](Get-Counter -Counter '\Web Service(_Total)\Bytes Total/sec' -ErrorAction SilentlyContinue).CounterSamples[0].CookedValue
        if ($appQps -gt 0 -and $resp -gt 0) { $appResp=[math]::Round($resp/$appQps*1000, 1) }
      } catch {}
      foreach ($an in $appNames) {
        if ([string]::IsNullOrWhiteSpace($an)) { $an=$siteName }
        $appsJson += ($sep+'{"app_name":"'+$an+'","server_type":"iis","host":"iis@'+$port+'","port":'+[int]$port+',"status":"'+$status+'","worker_count":'+[int]$workerCount+',"web_app_qps":'+[double]$appQps+',"web_app_avg_response_ms":'+[double]$appResp+',"web_app_cpu_pct":'+[double]$appCpu+',"web_app_mem_mb":'+[int]$appMem+',"jvm_heap_used_pct":null}')
        $sep=','
      }
    }
  } catch {}
}
# === Tomcat 部分(服务或注册表) ===
$tomcatHomes=@()
try {
  $regPaths=@('HKLM:\SOFTWARE\Apache Software Foundation\Tomcat\*','HKLM:\SOFTWARE\Wow6432Node\Apache Software Foundation\Tomcat\*')
  foreach ($rp in $regPaths) {
    $items=@(Get-ItemProperty -Path $rp -ErrorAction SilentlyContinue)
    foreach ($it in $items) {
      if ($it.'InstallPath') { $tomcatHomes += [string]$it.'InstallPath' }
    }
  }
} catch {}
try {
  $svcHomes=@(Get-WmiObject Win32_Service | Where-Object { $_.Name -like '*Tomcat*' -or $_.DisplayName -like '*Tomcat*' } | ForEach-Object { Split-Path -Parent (Split-Path -Parent $_.PathName) } | Sort-Object -Unique)
  foreach ($h in $svcHomes) { if ($h) { $tomcatHomes += $h } }
} catch {}
$tomcatHomes=$tomcatHomes | Sort-Object -Unique
foreach ($home in $tomcatHomes) {
  $binPath=Join-Path $home 'bin\catalina.bat'
  $confPath=Join-Path $home 'conf\server.xml'
  $webappsPath=Join-Path $home 'webapps'
  if (-not (Test-Path $webappsPath)) { continue }
  $port=8080
  if (Test-Path $confPath) {
    try {
      $xml=[xml](Get-Content $confPath -Raw)
      $conn=$xml.Server.Service.Connector | Where-Object { $_.port } | Select-Object -First 1
      if ($conn -and $conn.port) { $port=[int]$conn.port }
    } catch {}
  }
  $host="tomcat@$port"
  $pid=(Get-Process -Name java -ErrorAction SilentlyContinue | Select-Object -First 1).Id
  $status='stopped'; $appCpu=0.0; $appMem=0
  if ($pid) {
    $status='running'
    try {
      $p=Get-Process -Id $pid -ErrorAction Stop
      $appCpu=[math]::Round([double]$p.CPU, 1)
      $appMem=[int][math]::Round([double]$p.WorkingSet64/1MB)
    } catch {}
  }
  $dirs=@(Get-ChildItem -Path $webappsPath -Directory -ErrorAction SilentlyContinue)
  foreach ($d in $dirs) {
    $name=$d.Name
    if ($name -in @('work','docs','examples','host-manager','manager')) { continue }
    $webInf=Join-Path $d.FullName 'WEB-INF'
    if ((Test-Path $webInf) -or (Test-Path (Join-Path $webInf 'web.xml'))) {
      $appsJson += ($sep+'{"app_name":"'+$name+'","server_type":"tomcat","host":"'+$host+'","port":'+[int]$port+',"status":"'+$status+'","worker_count":200,"web_app_qps":0.0,"web_app_avg_response_ms":0.0,"web_app_cpu_pct":'+[double]$appCpu+',"web_app_mem_mb":'+[int]$appMem+',"jvm_heap_used_pct":null}')
      $sep=','
    }
  }
}
Write-Output ('{"web_apps":['+(($appsJson) -join '')+'],"web_app_count":'+$appsJson.Count+'}')
"""

_LINUX_FIELDS = [
    {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%", "direction": "high", "warn": 80, "crit": 90},
    {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%", "direction": "high", "warn": 80, "crit": 90},
    {"key": "cpu_idle_pct", "name_zh": "CPU 空闲率", "unit": "%", "direction": "low", "warn": 20, "crit": 10},
    {"key": "cpu_iowait_pct", "name_zh": "CPU iowait 占比", "unit": "%", "direction": "high", "warn": 20, "crit": 40},
    {"key": "swap_used_pct", "name_zh": "交换分区使用率", "unit": "%", "direction": "high", "warn": 30, "crit": 60},
    {"key": "inode_used_pct", "name_zh": "inode 使用率", "unit": "%", "direction": "high", "warn": 80, "crit": 90},
    {"key": "load_1m", "name_zh": "1 分钟平均负载", "unit": "", "direction": "high", "warn": 4.0, "crit": 8.0},
    {"key": "io_util_pct", "name_zh": "磁盘 IO 利用率", "unit": "%", "direction": "high", "warn": 80, "crit": 90},
    {"key": "io_await_ms", "name_zh": "磁盘 IO 平均等待", "unit": "ms", "direction": "high", "warn": 100, "crit": 200, "ssd_warn": 20, "ssd_crit": 50},
    # 2026-09-16 晚:web-server 段新增 4 条规则;顶层声明 + 数组展开(web_apps[])
    # 走与 disks[] 同样的 _ARRAY_EXPANSION_KEYS 评估器路径。
    {"key": "web_app_cpu_pct", "name_zh": "Web 应用 CPU 占比", "unit": "%", "direction": "high", "warn": 60, "crit": 85},
    {"key": "web_app_mem_mb", "name_zh": "Web 应用内存占用", "unit": "MB", "direction": "high", "warn": 2048, "crit": 4096},
    {"key": "web_app_qps", "name_zh": "Web 应用 QPS", "unit": "req/s", "direction": "high", "warn": 5000, "crit": 10000},
    {"key": "web_app_avg_response_ms", "name_zh": "Web 应用平均响应时间", "unit": "ms", "direction": "high", "warn": 500, "crit": 2000},
]

_WINDOWS_FIELDS = [
    {"key": "disk_used_pct", "name_zh": "磁盘使用率", "unit": "%", "direction": "high", "warn": 80, "crit": 90},
    {"key": "mem_used_pct", "name_zh": "内存使用率", "unit": "%", "direction": "high", "warn": 80, "crit": 90},
    {"key": "cpu_used_pct", "name_zh": "CPU 使用率", "unit": "%", "direction": "high", "warn": 80, "crit": 95},
    {"key": "cpu_iowait_pct", "name_zh": "CPU 中断/DPC 占比", "unit": "%", "direction": "high", "warn": 20, "crit": 40},
    {"key": "swap_used_pct", "name_zh": "页面文件使用率", "unit": "%", "direction": "high", "warn": 30, "crit": 60},
    {"key": "inode_used_pct", "name_zh": "MFT 使用率", "unit": "%", "direction": "high", "warn": 80, "crit": 90},
    {"key": "io_util_pct", "name_zh": "磁盘 IO 利用率", "unit": "%", "direction": "high", "warn": 80, "crit": 90},
    {"key": "io_await_ms", "name_zh": "磁盘 IO 平均等待", "unit": "ms", "direction": "high", "warn": 100, "crit": 200, "ssd_warn": 20, "ssd_crit": 50},
    # 2026-09-16 晚:web-server 段 IIS + Tomcat 共用 4 条规则;与 Linux 同形。
    {"key": "web_app_cpu_pct", "name_zh": "Web 应用 CPU 占比", "unit": "%", "direction": "high", "warn": 60, "crit": 85},
    {"key": "web_app_mem_mb", "name_zh": "Web 应用内存占用", "unit": "MB", "direction": "high", "warn": 2048, "crit": 4096},
    {"key": "web_app_qps", "name_zh": "Web 应用 QPS", "unit": "req/s", "direction": "high", "warn": 5000, "crit": 10000},
    {"key": "web_app_avg_response_ms", "name_zh": "Web 应用平均响应时间", "unit": "ms", "direction": "high", "warn": 500, "crit": 2000},
]


def _restore_quotes(text: str) -> str:
    """把 [CHAR39] 占位还原为单引号(PowerShell 单引号字符串字面量转义兜底)。

    参数:
        text: 含 [CHAR39] 占位的 PowerShell 脚本

    返回:
        str: 还原后的脚本

    异常:
        无。
    """
    return text.replace(_WINDOWS_QUOTE, "'")


DEFAULT_INSPECTION_GROUPS = [
    {
        "name": "linux-bash",
        "display_name": "Linux Bash 巡检(JSON,分段)",
        "platform": "linux",
        "version": "bash",
        "inspection_parser": "json",
        "inspection_fields": _LINUX_FIELDS,
        "segments": [
            {"segment_key": "disk-usage", "display_name": "磁盘使用率与 inode", "sort_order": 10, "script": _LINUX_DISK_USAGE_SCRIPT},
            {"segment_key": "disk-io", "display_name": "磁盘 IO 与介质", "sort_order": 20, "script": _LINUX_DISK_IO_SCRIPT},
            {"segment_key": "memory", "display_name": "内存与交换分区", "sort_order": 30, "script": _LINUX_MEMORY_SCRIPT},
            {"segment_key": "cpu", "display_name": "CPU 与负载", "sort_order": 40, "script": _LINUX_CPU_SCRIPT},
            # 2026-09-16 晚:web-server 分段(Tomcat 扫描,扁平化 web_apps 数组)
            {"segment_key": "web-server", "display_name": "Web 服务器(Tomcat)", "sort_order": 50, "script": _LINUX_WEB_SERVER_SCRIPT},
        ],
    },
    {
        "name": "windows-ps-5.1",
        "display_name": "Windows PowerShell 5.1 巡检(JSON,分段)",
        "platform": "windows",
        "version": "ps-5.1",
        "inspection_parser": "json",
        "inspection_fields": _WINDOWS_FIELDS,
        "segments": [
            {"segment_key": "disk-usage", "display_name": "磁盘使用率与 MFT", "sort_order": 10, "script": _restore_quotes(_WINDOWS_DISK_USAGE_SCRIPT)},
            {"segment_key": "disk-io", "display_name": "磁盘 IO 与介质", "sort_order": 20, "script": _restore_quotes(_WINDOWS_DISK_IO_SCRIPT)},
            {"segment_key": "memory", "display_name": "内存与页面文件", "sort_order": 30, "script": _restore_quotes(_WINDOWS_MEMORY_SCRIPT)},
            {"segment_key": "cpu", "display_name": "CPU 与中断/DPC", "sort_order": 40, "script": _restore_quotes(_WINDOWS_CPU_SCRIPT)},
            # 2026-09-16 晚:web-server 分段(IIS + Tomcat 扫描,扁平化 web_apps 数组)
            {"segment_key": "web-server", "display_name": "Web 服务器(IIS+Tomcat)", "sort_order": 50, "script": _WINDOWS_WEB_SERVER_SCRIPT},
        ],
    },
]
