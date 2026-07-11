#!/usr/bin/env python3
"""Evaluate simulation skill outputs against 4 binary criteria for 12 selected questions."""
import json, os, re, sys

SELECTED = [14, 17, 24, 26, 38, 40, 44, 45, 50, 56, 62, 74, 1, 11, 46, 66, 42]
RESULTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'results')

def load_output(qid):
    path = os.path.join(RESULTS_DIR, f'Q{qid}.txt')
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()

def eval_e1(text):
    """E1: Data correctness - contains actual numerical values"""
    if not text: return False, "无输出"
    # Look for water levels, flow rates, percentages
    nums = re.findall(r'\d+\.?\d*\s*(m³/s|m|mm|%)', text)
    return len(nums) >= 3, f"包含{len(nums)}个数值" if len(nums) >= 3 else f"仅{len(nums)}个数值"

def eval_e2(text):
    """E2: Safety constraint reference"""
    if not text: return False, "无输出"
    patterns = ['汛限', '安全泄量', '下游.*安全', '防洪.*约束', '超过.*水位', '超限',
                '水位.*约束', '安全.*水位', '设计洪水位', '462.88', '保证水位']
    hits = [p for p in patterns if re.search(p, text)]
    return len(hits) > 0, f"引用{len(hits)}处安全约束" if hits else "未引用安全约束"

def eval_e3(text):
    """E3: Structure completeness"""
    if not text: return False, "无输出"
    # Check for structured sections
    sections = len(re.findall(r'#{1,3}\s|【.*?】|一、|二、|三、|四、|调度|洪水|结果|报告|结论', text))
    return sections >= 3, f"包含{sections}个结构标记" if sections >= 3 else f"仅{sections}个结构标记"

def eval_e4(text):
    """E4: Knowledge citation - at least one regulation/standard"""
    if not text: return False, "无输出"
    patterns = ['防洪法', '防汛条例', 'GB\s*\d+', 'SL\s*\d+', '调度规程', '防洪标准',
                '水库大坝.*条例', '水文.*规范', '调度.*条例', '大坝安全.*条例',
                '《.*法》', '《.*条例》', '《.*标准》', '《.*规范》', '《.*规程》']
    hits = [p for p in patterns if re.search(p, text)]
    return len(hits) > 0, f"引用{len(hits)}处法规标准" if hits else "未引用任何法规标准"

def main():
    results = []
    total = 0
    max_score = len(SELECTED) * 4
    eval_counts = {'E1': 0, 'E2': 0, 'E3': 0, 'E4': 0}

    for qid in SELECTED:
        text = load_output(qid)
        e1, n1 = eval_e1(text)
        e2, n2 = eval_e2(text)
        e3, n3 = eval_e3(text)
        e4, n4 = eval_e4(text)
        score = sum([e1, e2, e3, e4])
        total += score
        eval_counts['E1'] += int(e1)
        eval_counts['E2'] += int(e2)
        eval_counts['E3'] += int(e3)
        eval_counts['E4'] += int(e4)
        results.append({
            'qid': qid,
            'scores': {'E1': e1, 'E2': e2, 'E3': e3, 'E4': e4},
            'notes': {'E1': n1, 'E2': n2, 'E3': n3, 'E4': n4},
            'score': score
        })

    pass_rate = round(total / max_score * 100, 1)

    print(f"=== 12题评估 ===")
    for r in results:
        flags = ' '.join(f"{'✅' if v else '❌'}{k}" for k, v in r['scores'].items())
        print(f"Q{r['qid']}: {flags} = {r['score']}/4")
    print(f"\n总分: {total}/{max_score} = {pass_rate}%")
    print(f"E1: {eval_counts['E1']}/12 | E2: {eval_counts['E2']}/12 | E3: {eval_counts['E3']}/12 | E4: {eval_counts['E4']}/12")

    # Output JSON for results.json update
    output = {
        'total': total,
        'max_score': max_score,
        'pass_rate': pass_rate,
        'eval_counts': eval_counts,
        'details': results
    }

    out_path = os.path.join(os.path.dirname(__file__), 'last-eval.json')
    with open(out_path, 'w') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return total, max_score, pass_rate

if __name__ == '__main__':
    main()
