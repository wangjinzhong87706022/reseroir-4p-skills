#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval-txt.py — 预案 skill txt 结果轻量评分(仿 simulation eval_e1-e4)

针对 hermes 真实输出 txt(非 eval.py 的自包含模式),4 个二元维度:
  E1 数据正确性: 含 ≥3 个数值(水位/流量/降雨/百分比)
  E2 安全约束:   提及汛限/安全泄量/超限/安全余量等
  E3 结构完整:   含 ≥3 个结构标记(【】/一二三/方案A/调度目标等)
  E4 知识引用:   引用 ≥1 条法规/标准/调度规则
"""
import os, re, sys, glob

RESULTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "results")

def load(name):
    p = os.path.join(RESULTS_DIR, name)
    return open(p, encoding='utf-8', errors='ignore').read() if os.path.exists(p) else ""

def e1(t):
    nums = re.findall(r'\d+\.?\d*\s*(m³/s|m|mm|%|万m³)', t)
    return len(nums) >= 3, f"{len(nums)}个数值"

def e2(t):
    pats = ['汛限', '安全泄量', '超限', '安全余量', '未超限', '设计洪水位', '校核', '保证水位']
    hits = [p for p in pats if p in t]
    return len(hits) > 0, f"引用{len(hits)}处安全约束"

def e3(t):
    marks = len(re.findall(r'【.*?】|一、|二、|三、|方案[ABC]|防洪优先|综合平衡|兴利|调度目标|调度模式|风险提示|结论|建议', t))
    return marks >= 3, f"{marks}个结构标记"

def e4(t):
    pats = [r'《[^》]*》', r'GB\s*\d+', r'SL\s*\d+', r'防洪法', r'防汛条例', r'水库大坝.*条例', r'根据调度规则', r'依据.*规则', r'GB\s*\d']
    hits = [p for p in pats if re.search(p, t)]
    return len(hits) > 0, f"引用{len(hits)}类法规/规则"

def main():
    files = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.txt")))
    if not files:
        print("无结果文件"); return
    total = 0; mx = 0
    dims = {'E1':0,'E2':0,'E3':0,'E4':0}; n=0
    print(f"{'题':<24} E1 E2 E3 E4  分")
    print("-"*44)
    for f in files:
        t = open(f, encoding='utf-8', errors='ignore').read()
        if len(t) < 100:  # 跳过垃圾文件
            continue
        n += 1
        v = [e1(t)[0], e2(t)[0], e3(t)[0], e4(t)[0]]
        sc = sum(v); total += sc; mx += 4
        for i,k in enumerate(['E1','E2','E3','E4']):
            dims[k] += v[i]
        name = os.path.basename(f).replace('.txt','')[:22]
        print(f"{name:<24} {'✅' if v[0] else '❌'} {'✅' if v[1] else '❌'} {'✅' if v[2] else '❌'} {'✅' if v[3] else '❌'}  {sc}/4")
    print("-"*44)
    print(f"总分: {total}/{mx} = {total/mx*100:.1f}%" if mx else "无有效结果")
    for k in ['E1','E2','E3','E4']:
        print(f"  {k}: {dims[k]}/{n}")

if __name__ == '__main__':
    main()
