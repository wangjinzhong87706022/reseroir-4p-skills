#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval-txt.py — 预报 skill txt 结果轻量评分(6 维, 仿 simulation eval_e1-e4 + E5/E6)

针对 hermes 真实输出 txt(非 eval.py 的自包含模式),6 个二元维度:
  E1 数据正确性:  含 ≥3 个数值(降雨/流量/水位/百分比) — 单位含 mm/h, m³/s, m/s, m, mm, %
  E2 安全与置信:  提及汛限/安全泄量/超限/估算值/±20%/置信度/设计洪水位/校核 等
  E3 结构完整:    含 ≥3 个结构标记(预报蓝图标记: 【依据】/【分析】/【校验与依据】/预报解读/影响估算/多源/趋势/精度/结论/建议)
  E4 知识引用:    引用 ≥1 条法规/标准/条例 (《...》/GB/T 22482/SL xxx/防洪法/水文情报预报规范/水库大坝条例)
  E5 多源对齐:    (仅多源融合类) ≥2 源名 + 时间窗/对齐/预见期/置信
  E6 置信标注:    (仅水库影响/趋势预测类) 含估算值/置信度/高/中/低

  评分: E1+E2+E3+E4 始终计入; E5 仅多源融合题计入; E6 仅水库影响/趋势预测题计入。
  分类依据: 文件名关键字 (多源/融合/NMC/和风 → E5; 影响/趋势/水位/洪峰 → E6)。
"""
import os, re, glob

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

# ---- 分类: 由文件名推断是否需要 E5 / E6 ----
E5_KEYS = ('多源', '融合', 'NMC', '和风', '分歧', '对比', '源', 'Q3_', 'Q11', 'Q12', 'Q14', 'Q38')
E6_KEYS = ('影响', '趋势', '水位', '洪峰', '涨', '退水', '削峰', 'Q2_', 'Q6', 'Q7', 'Q16', 'Q17', 'Q18', 'Q19', 'Q20', 'Q36', 'Q40')


def classify(fname):
    """根据文件名返回 (need_e5, need_e6)。"""
    return (any(k in fname for k in E5_KEYS), any(k in fname for k in E6_KEYS))


def e1(t):
    nums = re.findall(r'\d+\.?\d*\s*(mm/h|mm|m³/s|m/s|m|%)', t)
    return len(nums) >= 3, f"{len(nums)}个数值"


def e2(t):
    pats = ['估算值', '±20%', '置信度', '汛限', '超限', '安全泄量', '未超限', '设计洪水位', '校核']
    hits = [p for p in pats if p in t]
    return len(hits) > 0, f"引用{len(hits)}处安全/置信"


def e3(t):
    marks = len(re.findall(r'【依据】|【分析】|【校验与依据】|预报解读|影响估算|多源|趋势|精度|结论|建议', t))
    return marks >= 3, f"{marks}个结构标记"


def e4(t):
    pats = [r'《[^》]*》', r'GB/T\s*22482', r'SL\s*\d+', r'防洪法', r'水文情报预报规范', r'水库大坝.*条例']
    hits = [p for p in pats if re.search(p, t)]
    return len(hits) > 0, f"引用{len(hits)}类法规/标准"


def e5(t):
    """多源对齐: ≥2 源名 AND 时间窗/对齐/预见期/置信。"""
    src_pats = ['和风', 'NMC', '分区', '模型', '168h', '30d', '24h']
    src_hits = sum(1 for p in src_pats if p in t)
    align = re.search(r'时间窗|对齐|预见期|置信', t)
    ok = src_hits >= 2 and bool(align)
    return ok, f"源{src_hits}+{'对齐' if align else '无对齐'}"


def e6(t):
    """置信标注: 含估算值/置信度/高/中/低。"""
    ok = bool(re.search(r'估算值|置信度|高|中|低', t))
    return ok, "有置信标注" if ok else "无置信标注"


def main():
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "Q*.txt")))
    if not files:
        print("无结果文件")
        return
    total = 0
    mx = 0
    dims = {'E1': 0, 'E2': 0, 'E3': 0, 'E4': 0, 'E5': 0, 'E6': 0}
    n = 0
    n_e5 = 0  # 适用 E5 的题数
    n_e6 = 0  # 适用 E6 的题数

    print(f"{'题':<24} E1 E2 E3 E4 E5 E6  分")
    print("-" * 52)
    for f in files:
        t = open(f, encoding='utf-8', errors='ignore').read()
        if len(t) < 100:  # 跳过垃圾文件
            continue
        n += 1
        fname = os.path.basename(f)
        need_e5, need_e6 = classify(fname)
        v = [e1(t)[0], e2(t)[0], e3(t)[0], e4(t)[0]]
        sc = sum(v)
        total += sc
        mx += 4
        for i, k in enumerate(['E1', 'E2', 'E3', 'E4']):
            dims[k] += v[i]

        e5_flag = '—'
        if need_e5:
            n_e5 += 1
            v5 = e5(t)[0]
            dims['E5'] += int(v5)
            sc += int(v5)
            total += int(v5)
            mx += 1
            e5_flag = '✅' if v5 else '❌'

        e6_flag = '—'
        if need_e6:
            n_e6 += 1
            v6 = e6(t)[0]
            dims['E6'] += int(v6)
            sc += int(v6)
            total += int(v6)
            mx += 1
            e6_flag = '✅' if v6 else '❌'

        denom = 4 + (1 if need_e5 else 0) + (1 if need_e6 else 0)
        name = fname.replace('.txt', '')[:22]
        print(f"{name:<24} {'✅' if v[0] else '❌'} {'✅' if v[1] else '❌'} "
              f"{'✅' if v[2] else '❌'} {'✅' if v[3] else '❌'} {e5_flag} {e6_flag}  {sc}/{denom}")
    print("-" * 52)
    print(f"总分: {total}/{mx} = {total / mx * 100:.1f}%" if mx else "无有效结果")
    print(f"  E1: {dims['E1']}/{n}  E2: {dims['E2']}/{n}  E3: {dims['E3']}/{n}  E4: {dims['E4']}/{n}")
    print(f"  E5: {dims['E5']}/{n_e5} (多源融合类)  E6: {dims['E6']}/{n_e6} (水库影响/趋势类)")


if __name__ == '__main__':
    main()
