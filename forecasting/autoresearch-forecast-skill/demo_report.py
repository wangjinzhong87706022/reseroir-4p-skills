#!/usr/bin/env python3
"""读 demo.sh 产出的 snapshot/scenario 文件,组装 demo-report.md。
用法: python3 demo_report.py <results_dir>
不连 DB(只读文件 + 写 md)。"""
import sys, os, re

RES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'results')

# 场景元数据(与 demo.sh 配置表一致)
SC = [
    (1, "正常水情", "默认窗口", "今天值班，看看三岔水库当前水情和未来24h降雨，会不会有问题？", "基线:三段蓝图正常解读三岔水位+168h预报"),
    (2, "暴雨来袭", "--scenario demo_flow", "这场暴雨会不会让水位超汛限？要不要提前预泄？", "安全校验【距汛限】+防洪优先建议(核心价值)"),
    (3, "多源冲突", "--inject-fault source_disagree", "和风报120mm、分区报60mm，该信哪个源？", "识别四源分歧+保守取大+低置信标注"),
    (4, "预报陈旧", "--inject-fault stale_forecast", "未来24小时雨情怎么样？", "主动提示'预报已过期,仅供参考'(健壮性)"),
    (5, "复位", "--purge-mock", "—", "清场,循环演示"),
]


def read(p):
    try:
        return open(p, encoding='utf-8').read().strip()
    except Exception:
        return "(无)"


def extract_val(snap_text, key):
    """从快照表格行提取值(匹配 'key | value' 行)。"""
    for line in snap_text.splitlines():
        if key in line and '|' in line:
            parts = [x.strip() for x in line.split('|')]
            if len(parts) >= 3 and parts[1].strip():
                return parts[2].strip()
    return "N/A"


# ---- 报告组装 ----
out = ["# 预报 Skill 端到端 Demo 报告\n",
       f"> 生成: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]

snap1 = read(f"{RES}/demo-snapshot-1.txt")
snap2 = read(f"{RES}/demo-snapshot-2.txt")

for n, name, sim, q, point in SC:
    snap = read(f"{RES}/demo-snapshot-{n}.txt")
    scen = read(f"{RES}/demo-scenario-{n}.txt")
    is_stall = ("STALL" in scen or "端点" in scen) and "OK" not in scen.split("\n")[-1]
    out.append(f"\n## 场景{n}: {name}\n")
    out.append(f"- **模拟器**: `{sim}`\n- **skill 问题**: {q}\n- **看点**: {point}\n")
    if name != "复位":
        out.append(f"\n### 数据快照\n```\n{snap or '(无快照)'}\n```\n")
        tag = " ⚠️ 端点 stall,未取到解读" if is_stall else ""
        out.append(f"\n### AI 解读{tag}\n```\n{scen or '(无输出)'}\n```\n")
    else:
        out.append("\n(清场复位,无解读)\n")

# ---- 正常 vs 暴雨 对比(场景1 vs 场景2)----
out.append("\n## 正常 vs 暴雨 对比(场景1 vs 场景2)\n")
out.append("| 指标 | 场景1 正常 | 场景2 暴雨 |\n|---|---|---|")
for label, key in [("当前水位", "当前水位"), ("水位峰值24h", "水位峰值24h"),
                   ("24h预报降雨mm", "24h预报降雨"), ("24h实测降雨mm", "24h实测降雨")]:
    out.append(f"| {label} | {extract_val(snap1, key)} | {extract_val(snap2, key)} |")
out.append(f"| 预警 | {extract_val(snap1, '预警')} | {extract_val(snap2, '预警')} |")
out.append(f"| 汛限 | {extract_val(snap1, '汛限水位')} | {extract_val(snap2, '汛限水位')} |")
out.append("\n> 一眼看暴雨场景下数据 + AI 判断的差异(演示核心张力)。\n")

report = os.path.join(RES, 'demo-report.md')
open(report, 'w', encoding='utf-8').write("\n".join(out))
print(f"报告已写: {report}")
