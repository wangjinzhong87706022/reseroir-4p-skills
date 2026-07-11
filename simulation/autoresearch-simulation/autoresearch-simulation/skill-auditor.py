#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
skill-auditor.py — SkillEvolver 风格的 5 项 skill 过拟合审计器

对 SkillEvolver (arXiv:2605.10500) 提出的 5 类部署/过拟合风险做规则化检查:
  C1 self-contained   引用的文件是否真实存在(fresh agent 不会拿到幽灵依赖)
  C2 hardcoded-const  实例特定常量是否被硬编码进规则/模板(换水库/换文件名就废)
  C3 param-axis       是否引导查询参数轴,而非照抄字面量
  C4 entry-point      主入口/触发描述是否对 fresh agent 明显
  C5 silent-bypass    是否存在绕过关键步骤(查询/校验/引用)的措辞

用法:
  python3 skill-auditor.py [skill_dir]
  python3 skill-auditor.py /path/to/SmartTwinRes-skills/simulation

设计原则: 纯规则 + 启发式,不调 LLM,可重复. 每项给 pass/warn/fail 并列证据.
"""
import os
import re
import sys
from collections import Counter

# ---------- 阈值配置(可按 skill 特性调整) ----------
HARDCODED_MIN_REPEAT = 2          # 同一浮点常量重复出现 >= N 次才算"硬编码嫌疑"
SELF_CONTAINED_RE = re.compile(
    r'`?([a-zA-Z0-9_./-]+\.(?:md|py|sh|sql|json|yaml|yml|txt))`?'
)
# 实例特定物理量(水库专属)——出现在模板/规则里就是过拟合
INSTANCE_VALUE_HINTS = {
    '汛限': '汛限水位(应从 model_config / att_res_flse_lim 查询)',
    '安全泄量': '下游安全泄量(应从 config 查询)',
    '设计洪水位': '设计洪水位(应从 config 查询)',
    '起调水位': '起调水位(应由用户或实时水情决定)',
}
# 正向"参数轴"信号: 引导动态查询而非照抄
PARAM_AXIS_GOOD = [
    '--type config', '--type flood_limit', '--type current_water_level',
    '系统配置值', '从数据库', '查询', '读取', '动态', '兜底', 'fl_low_lim_lev',
]
# 绕过类措辞
BYPASS_WORDS = ['跳过', '省略', '可以不', '无需', '可选', '不必', '略过']
CRITICAL_WORDS = ['校验', '引用', '安全', '查询', '法规', '依据', '第3段', '第三段']


def read_skill(skill_dir):
    path = os.path.join(skill_dir, 'SKILL.md')
    with open(path, encoding='utf-8') as f:
        return f.read(), path


def split_frontmatter(text):
    """返回 (frontmatter_str, body_str)"""
    m = re.match(r'^---\n(.*?)\n---\n(.*)', text, re.DOTALL)
    if m:
        return m.group(1), m.group(2)
    return '', text


# ============================================================
# C1 self-contained: 引用文件是否都存在
# ============================================================
def check_self_contained(body, skill_dir):
    refs = Counter(SELF_CONTAINED_RE.findall(body))
    # 过滤明显是 URL / 代码内字符串的(含 http 或 纯库名)
    findings = []
    missing = []
    for ref, cnt in refs.items():
        if 'http' in ref or ref.startswith('scripts/query') == False and '/' not in ref and '.' not in ref:
            # 单纯文件名也保留,只跳过明显 URL
            if 'http' in ref:
                continue
        # 解析为相对 skill_dir 的路径
        candidate = os.path.normpath(os.path.join(skill_dir, ref))
        exists = os.path.exists(candidate)
        # 仅报告"看起来像本 skill 内部资源"的引用
        looks_internal = (
            ref.startswith('scripts/') or ref.startswith('references/')
            or ref.startswith('templates/') or ref.startswith('tests/')
            or ref.startswith('models/') or ref.startswith('data/')
            or ref in ('db-config.md',)  # 根级 md
        )
        if looks_internal:
            findings.append((ref, cnt, exists, candidate))
            if not exists:
                missing.append(ref)
    status = 'pass' if not missing else 'fail'
    return {
        'check': 'C1 self-contained',
        'status': status,
        'detail': findings,
        'missing': missing,
        'summary': f"检查 {len(findings)} 个内部引用,缺失 {len(missing)} 个",
    }


# ============================================================
# C2 hardcoded-const: 区分"规则类"与"示例类"字面量
#   规则类(prescriptive): 出现在 模板/安全校验/参考值/必须/不能/距汛限 等上下文
#                          —— fresh agent 会照抄进输出,换水库就错 -> FAIL
#   示例类(example):      出现在 curl JSON / curl 输入参数 / 标注"示例"处
#                          —— 仅演示输入格式 -> 仅 note,不 FAIL
# ============================================================
PRESCRIPTIVE_MARKERS = re.compile(
    r'(必须|不能|不得超过|不得|距汛限|安全校验|参考值|参考值来源|依据|约束|距.*水位)'
)
EXAMPLE_MARKERS = re.compile(r'(curl|--data|-d\s|param_values|"flood_limit_level"|"safe_drainage"|"initial_water")')


def _classify_float_occurrences(body):
    """返回 {value: {'prescriptive': n, 'example': n, 'lines': []}}.

    分类逻辑(按优先级):
      1. 数值在【安全校验/法规依据】输出模板块内 + 是具体值(非 XX 占位) -> prescriptive
         (这种块会被 fresh agent 照抄进输出)
      2. 数值在围栏代码块(curl/示例/格式模板)内 -> example
      3. 数值在 markdown 表格行内 -> example
      4. 否则看邻近行: 命中规则词 -> prescriptive;命中示例词 -> example;都没有 -> prescriptive(保守)
    """
    lines = body.splitlines()
    # 预计算每行是否在围栏块内,以及所在块是否是"输出模板"类型
    in_fence = [False] * len(lines)
    block_is_output_template = [False] * len(lines)
    depth = 0
    cur_block_is_tpl = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('```'):
            if depth == 0:
                depth = 1
                # 判断这个块是否输出模板(后续几行含 安全校验/法规依据/【依据】)
                look = ' '.join(lines[i:i + 8])
                cur_block_is_tpl = bool(re.search(r'(安全校验|法规依据|【依据】|【校验|【分析】)', look))
            else:
                depth = 0
                cur_block_is_tpl = False
            in_fence[i] = depth > 0
            block_is_output_template[i] = cur_block_is_tpl
        else:
            in_fence[i] = depth > 0
            block_is_output_template[i] = cur_block_is_tpl

    tally = {}
    for i, line in enumerate(lines):
        ctx = ' '.join(lines[max(0, i - 1):i + 2])
        is_table_row = line.lstrip().startswith('|') and '|' in line.lstrip()[1:]
        for m in re.finditer(r'(?<![\w.])(\d{2,4}\.\d{1,3})', line):
            v = m.group(1)
            if float(v) < 10.0:
                continue
            tally.setdefault(v, {'prescriptive': 0, 'example': 0, 'lines': []})
            if in_fence[i] and block_is_output_template[i]:
                tally[v]['prescriptive'] += 1
                tally[v]['lines'].append(i + 1)
            elif in_fence[i] or is_table_row:
                tally[v]['example'] += 1
            elif PRESCRIPTIVE_MARKERS.search(ctx):
                tally[v]['prescriptive'] += 1
                tally[v]['lines'].append(i + 1)
            elif EXAMPLE_MARKERS.search(ctx):
                tally[v]['example'] += 1
            else:
                tally[v]['prescriptive'] += 1
                tally[v]['lines'].append(i + 1)
    return tally


def check_hardcoded_consts(body):
    tally = _classify_float_occurrences(body)
    # 规则类风险: prescriptive 出现 >=1 次即危险(被照抄进输出)
    prescriptive_risk = {v: d for v, d in tally.items() if d['prescriptive'] >= 1}
    # 示例类: 仅记录
    example_only = {v: d['example'] for v, d in tally.items()
                    if d['prescriptive'] == 0 and d['example'] >= 1}

    # 敏感凭证硬编码(DB 密码明文)
    creds = []
    # -p 口令: 必须是独立flag(前面是空白/行首),排除 --plan-id 里的 -p
    for m in re.finditer(r'(?<![\w-])-p\S{4,}', body):
        if '$' not in m.group(0):
            creds.append('检测到明文 DB 口令(应改用 $SRM_DB_PASSWORD 环境变量)')
            break
    if re.search(r'password\s*[=:]\s*[\'"]?[A-Za-z0-9]', body, re.I):
        if not re.search(r'password\s*[=:]\s*[\'"]?\$', body, re.I):
            creds.append('检测到明文 password 赋值(应改用环境变量)')

    risk_items = []
    for v, d in sorted(prescriptive_risk.items(), key=lambda x: -(x[1]['prescriptive'])):
        risk_items.append(f"'{v}' 规则类出现 {d['prescriptive']} 次 (行 {d['lines']})——会被照抄进输出")
    example_notes = [f"'{v}' 示例类 {c} 次(curl 输入,已标注示例,可接受)" for v, c in example_only.items()]

    status = 'fail' if (risk_items or creds) else 'pass'
    return {
        'check': 'C2 hardcoded-const',
        'status': status,
        'prescriptive_risk': prescriptive_risk,
        'example_only': example_only,
        'credentials': creds,
        'risk_items': risk_items,
        'example_notes': example_notes,
        'summary': (f"规则类硬编码 {len(risk_items)} 项 + 示例类 {len(example_notes)} 项"
                    f" + 凭证 {len(creds)} 项"),
    }


# ============================================================
# C3 param-axis: 查询引导 vs 字面量照抄 的信号比
# ============================================================
def check_param_axis(body):
    good_hits = [sig for sig in PARAM_AXIS_GOOD if sig in body]
    # 参数轴正向引用: "查询 --type xxx" / "系统配置值" / "--type config/flood_limit" 出现次数
    query_refs = len(re.findall(r'查询\s*`?--type\s*\w+`?', body))
    config_refs = body.count('系统配置值') + body.count('--type config') + body.count('--type flood_limit')
    total_param_refs = query_refs + config_refs
    # 字面量水位(坏信号)——仅 prose 中的(排除示例块)
    lit_water = len(re.findall(r'(?<![<])\d{3}\.\d{1,3}\s*m(?![³m])', body))
    ratio = total_param_refs / max(lit_water, 1)
    status = 'pass' if (len(good_hits) >= 3 and total_param_refs >= 3) else 'warn'
    return {
        'check': 'C3 param-axis',
        'status': status,
        'query_signals_found': good_hits,
        'param_query_refs': total_param_refs,
        'literal_water_level_refs': lit_water,
        'signal_ratio': round(ratio, 2),
        'summary': f"查询引导信号 {len(good_hits)} 个, 参数查询引用 {total_param_refs} 次 vs 字面水位 {lit_water} 次 (比 {ratio:.2f})",
    }


# ============================================================
# C4 entry-point: description 触发度 + 顶部 TL;DR
# ============================================================
def check_entry_point(frontmatter, body):
    desc_m = re.search(r'description:\s*["\']?(.*?)["\']?\s*\n', frontmatter)
    desc = desc_m.group(1) if desc_m else ''
    # 触发关键词密度: 动词 + 业务名词
    trigger_verbs = ['生成', '解读', '对比', '构建', '分析', '查询', '评估', '预演', '提取']
    verb_hits = [v for v in trigger_verbs if v in desc]
    # 顶部 60 行是否有醒目主入口(⛔ / TL;DR / 输出蓝图 / 执行规范 / 工作流)
    head = '\n'.join(body.splitlines()[:60])
    has_top_landmark = any(m in head for m in ['⛔', '输出蓝图', '执行规范', 'TL;DR', '工作流', '速查卡'])

    issues = []
    if len(desc) < 15:
        issues.append(f"description 过短({len(desc)}字),fresh agent 难以据此触发")
    if len(verb_hits) < 2:
        issues.append(f"description 触发动词不足(仅 {verb_hits}),建议显式命名任务与陷阱(SkillEvolver virtualhome 案例: 改写 description 后触发率 0→5/5)")
    if not has_top_landmark:
        issues.append("顶部 60 行缺少醒目主入口标记(⛔/输出蓝图/速查卡)")

    status = 'pass' if not issues else 'warn'
    return {
        'check': 'C4 entry-point',
        'status': status,
        'description': desc,
        'trigger_verbs_hit': verb_hits,
        'top_landmark': has_top_landmark,
        'issues': issues,
        'summary': f"description {len(desc)}字,触发动词 {len(verb_hits)},顶部主入口 {'有' if has_top_landmark else '无'}",
    }


# ============================================================
# C5 silent-bypass: 绕过措辞是否靠近关键步骤
# ============================================================
def _is_negated_or_enforcing(line, word):
    """判断 word 在 line 中是否被否定/强制(即其实是反绕过规则)."""
    # 否定前缀紧挨 word(如 "不做跳过" "不能省略" "无需"自身除外——'无需'已是绕过)
    idx = line.find(word)
    if idx > 0:
        pre = line[max(0, idx - 3):idx]
        if re.search(r'(不|无(?!需)|非|未|勿|没|禁止|不能|不得|别)', pre):
            return True
    # 同行有强强制语(说明该绕过词是被约束的对象,非放行)
    if re.search(r'(必须|必填|硬性|都要|逐一|不得|不能省|都要包含|绝不)', line):
        return True
    return False


def check_silent_bypass(body):
    lines = body.splitlines()
    risky = []
    for i, line in enumerate(lines):
        hit = [b for b in BYPASS_WORDS if b in line]
        if not hit:
            continue
        ctx = ' '.join(lines[max(0, i - 2):i + 3])
        if not any(c in ctx for c in CRITICAL_WORDS):
            continue  # 绕过词不靠近关键步骤,不报
        # 每个命中的绕过词都看是否被否定/强制;全部被否定才算安全
        if all(_is_negated_or_enforcing(line, w) for w in hit):
            continue  # 反绕过规则,不报
        risky.append((i + 1, line.strip()))
    status = 'fail' if risky else 'pass'
    return {
        'check': 'C5 silent-bypass',
        'status': status,
        'risky_lines': risky,
        'summary': f"{len(risky)} 处绕过措辞靠近关键步骤",
    }


def status_icon(s):
    return {'pass': '✅', 'warn': '⚠️ ', 'fail': '❌'}[s]


def main():
    skill_dir = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # 默认指回 simulation skill 根
    if not os.path.exists(os.path.join(skill_dir, 'SKILL.md')):
        skill_dir = os.path.join(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))), 'simulation')
    text, path = read_skill(skill_dir)
    frontmatter, body = split_frontmatter(text)

    print(f"═══════════════════════════════════════════════════════════")
    print(f"  SkillEvolver 5-Check Auditor")
    print(f"  目标: {path}")
    print(f"═══════════════════════════════════════════════════════════\n")

    checks = [
        check_self_contained(body, skill_dir),
        check_hardcoded_consts(body),
        check_param_axis(body),
        check_entry_point(frontmatter, body),
        check_silent_bypass(body),
    ]

    for r in checks:
        print(f"{status_icon(r['status'])} {r['check']}  [{r['status'].upper()}]")
        print(f"    {r['summary']}")
        # 细节
        if r['check'] == 'C1 self-contained' and r['missing']:
            print(f"    缺失文件: {r['missing']}")
        if r['check'] == 'C2 hardcoded-const':
            for it in r['risk_items'][:8]:
                print(f"    • ❌ {it}")
            for c in r['credentials']:
                print(f"    • 🔐 {c}")
            for it in r.get('example_notes', [])[:5]:
                print(f"    • ⚪ {it}")
        if r['check'] == 'C3 param-axis':
            print(f"    查询信号: {r['query_signals_found']}")
        if r['check'] == 'C4 entry-point':
            print(f"    description: \"{r['description'][:80]}\"")
            for it in r['issues']:
                print(f"    • {it}")
        if r['check'] == 'C5 silent-bypass':
            for ln, txt in r['risky_lines']:
                print(f"    • L{ln}: {txt[:70]}")
        print()

    # 总评
    weights = {'pass': 0, 'warn': 1, 'fail': 2}
    total = sum(weights[r['status']] for r in checks)
    print(f"───────────────────────────────────────────────────────────")
    if total == 0:
        verdict = "🟢 通过: 未发现明显过拟合/部署风险"
    elif total <= 3:
        verdict = "🟡 轻度风险: 存在可改进点,建议修复 warn 项"
    else:
        verdict = "🔴 高风险: 存在硬编码/绕过类问题,部署到 fresh agent 大概率掉分"
    print(f"  总评: {verdict}  (风险分 {total}/10)")
    print(f"───────────────────────────────────────────────────────────")


if __name__ == '__main__':
    main()
