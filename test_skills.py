#!/usr/bin/env python3
"""
SmartTwinRes Skills 自动化测试框架

支持多个 Skill 的端到端测试：
- forecasting（预报）- 数据库已配置
- early-warning（预警）- 需要 SRM_DB_* 环境变量
- plan-generation（预案）- 需要 SRM_DB_* 环境变量
- simulation（预演）- 需要 SRM_DB_* 环境变量

用法：
    python3 test_skills.py --list
    python3 test_skills.py --skill forecasting --timeout 300
    python3 test_skills.py --skill early-warning --timeout 300
    python3 test_skills.py --all --timeout 300
"""

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional, List

# =============================================================================
# 路径配置（使用统一的路径管理）
# =============================================================================
# 将 lib/ 目录添加到 Python 路径
sys.path.insert(0, str(Path(__file__).parent / "lib"))

from paths import (
    PROJECT_ROOT,
    SKILLS_DIR,
    RESULTS_DIR,
    LOGS_DIR,
    get_skill_dir,
    ensure_dirs
)

# 确保必需的目录存在
ensure_dirs()

# Hermes 超时设置
HERMES_TIMEOUT = 300  # 5分钟超时

# =============================================================================
# Skill 定义
# =============================================================================

@dataclass
class SkillDefinition:
    """Skill 定义"""
    id: str
    name: str
    description: str
    skill_dir: Path
    enabled: bool = True


SKILLS = [
    SkillDefinition(
        id="forecasting",
        name="预报系统",
        description="降雨预报、水情查询、汛限水位、气象预警",
        skill_dir=get_skill_dir("forecasting"),
        enabled=True
    ),
    SkillDefinition(
        id="plan-generation",
        name="预案生成",
        description="调度预案、形势研判、方案对比",
        skill_dir=get_skill_dir("plan-generation"),
        enabled=True  # builtin skill
    ),
    SkillDefinition(
        id="simulation",
        name="预演模拟",
        description="多方案对比、虚拟场景、结果解读",
        skill_dir=get_skill_dir("simulation"),
        enabled=True  # builtin skill
    ),
    SkillDefinition(
        id="early-warning",
        name="智能预警",
        description="告警分析、风险定级、预警规则",
        skill_dir=get_skill_dir("early-warning"),
        enabled=True
    ),
    SkillDefinition(
        id="diagnosis-verification",
        name="诊断核验",
        description="数据质量检查、8Phase 诊断、6 层核验",
        skill_dir=get_skill_dir("diagnosis-verification"),
        enabled=True
    ),
    SkillDefinition(
        id="supervisor",
        name="四预编排",
        description="场景路由、七步编排、仲裁闭环",
        skill_dir=get_skill_dir("supervisor"),
        enabled=True
    ),
]

# =============================================================================
# 测试用例定义
# =============================================================================

@dataclass
class TestCase:
    """单个测试用例"""
    id: str
    skill_id: str
    description: str
    question: str
    expected_keywords: List[str]
    timeout: int = HERMES_TIMEOUT

    def to_dict(self):
        return asdict(self)


# Forecasting 测试用例（已验证）
FORECASTING_TESTS = [
    TestCase("F1", "forecasting", "查询当前水位", "查询三岔水库当前水位（只返回数值）",
             ["462", "水位", "m"], 60),
    TestCase("F2", "forecasting", "未来24小时降雨预报", "未来24小时三岔水库流域的逐时降雨预报情况如何？",
             ["mm", "降雨", "预报", "逐时"], 120),
    TestCase("F3", "forecasting", "查询汛限水位", "当前三岔水库的汛限水位是多少？",
             ["汛限", "水位"], 60),
    TestCase("F4", "forecasting", "查询气象预警", "当前有哪些气象预警？",
             ["预警"], 120),
    TestCase("F5", "forecasting", "数据时效性检查", "当前预报数据的时效性如何？",
             ["时效", "陈旧", "时效性"], 120),
    TestCase("F6", "forecasting", "综合查询", "综合分析三岔水库当前水情和未来24小时降雨情况",
             ["水位", "降雨", "汛限", "预警", "综合"], 120),
]

# Plan-Generation 测试用例（待验证）
PLAN_GENERATION_TESTS = [
    TestCase("PG1", "plan-generation", "查询当前水情", "三岔水库当前水情怎么样？",
             ["水位", "入库", "出库"], 120),
    TestCase("PG2", "plan-generation", "查询汛限水位", "当前汛限水位是多少？",
             ["汛限", "水位"], 120),
    TestCase("PG3", "plan-generation", "生成调度预案", "根据当前情况生成一个调度预案",
             ["预案", "调度", "方案"], 180),  # 预案生成可能需要更长时间
]

# Simulation 测试用例（待验证）
SIMULATION_TESTS = [
    TestCase("SIM1", "simulation", "查询当前水位和配置", "查询三岔水库当前水位和系统配置",
             ["水位", "配置"], 120),
    TestCase("SIM2", "simulation", "查询历史洪水", "查询历史洪水记录",
             ["历史", "洪水"], 120),
]

# 所有测试用例
ALL_TESTS = FORECASTING_TESTS + PLAN_GENERATION_TESTS + SIMULATION_TESTS

# =============================================================================
# 测试执行器
# =============================================================================

class SkillTestRunner:
    """Skill 测试执行器"""

    def __init__(self, timeout: int = HERMES_TIMEOUT):
        self.timeout = timeout
        self.results = []

    def run_test_case(self, test_case: TestCase, skill: SkillDefinition) -> dict:
        """执行单个测试用例"""
        print(f"\n{'='*80}")
        print(f"[{test_case.id}] {test_case.description}")
        print(f"Skill: {skill.name}")
        print(f"问题: {test_case.question}")
        print(f"超时: {test_case.timeout}s")
        print(f"{'='*80}\n")

        start_time = time.time()

        try:
            # 构建命令
            cmd = [
                "hermes", "chat", "-q",
                test_case.question,
                "--skills", test_case.skill_id,
                "-Q"  # 静默模式
            ]

            # 执行命令
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=test_case.timeout,
                cwd=str(skill.skill_dir)
            )

            elapsed = time.time() - start_time

            # 解析输出
            output = result.stdout.strip()
            stderr = result.stderr.strip()

            # 验证结果
            verification = self._verify_output(test_case, output)

            test_result = {
                "id": test_case.id,
                "skill_id": test_case.skill_id,
                "description": test_case.description,
                "question": test_case.question,
                "status": "PASS" if verification["all_passed"] else "FAIL",
                "elapsed_seconds": round(elapsed, 2),
                "output": output[:500] + "..." if len(output) > 500 else output,
                "expected_keywords": test_case.expected_keywords,
                "keyword_checks": verification["keyword_checks"],
                "all_keywords_found": verification["all_keywords_found"],
                "exit_code": result.returncode,
                "stderr": stderr[:200] if stderr else None
            }

            # 打印结果
            self._print_result(test_result, verification)

            return test_result

        except subprocess.TimeoutExpired:
            elapsed = time.time() - start_time
            print(f"❌ 超时！({test_case.timeout}s)")
            return {
                "id": test_case.id,
                "skill_id": test_case.skill_id,
                "description": test_case.description,
                "question": test_case.question,
                "status": "TIMEOUT",
                "elapsed_seconds": round(elapsed, 2),
                "output": None,
                "error": f"Command timed out after {test_case.timeout}s"
            }
        except Exception as e:
            elapsed = time.time() - start_time
            print(f"❌ 异常: {e}")
            return {
                "id": test_case.id,
                "skill_id": test_case.skill_id,
                "description": test_case.description,
                "question": test_case.question,
                "status": "ERROR",
                "elapsed_seconds": round(elapsed, 2),
                "error": str(e)
            }

    def _verify_output(self, test_case: TestCase, output: str) -> dict:
        """验证输出是否符合预期"""
        keyword_checks = []
        all_found = True

        for keyword in test_case.expected_keywords:
            found = keyword.lower() in output.lower()
            keyword_checks.append({
                "keyword": keyword,
                "found": found
            })
            if not found:
                all_found = False

        return {
            "keyword_checks": keyword_checks,
            "all_keywords_found": all_found,
            "all_passed": all_found
        }

    def _print_result(self, result: dict, verification: dict):
        """打印测试结果"""
        status_icon = {"PASS": "✅", "FAIL": "❌", "TIMEOUT": "⏰", "ERROR": "❌"}.get(result["status"], "❓")
        print(f"\n{status_icon} 测试结果: {result['status']}")
        print(f"⏱️  耗时: {result['elapsed_seconds']}s")

        if verification["keyword_checks"]:
            print(f"\n关键词验证:")
            for check in verification["keyword_checks"]:
                icon = "✓" if check["found"] else "✗"
                print(f"  {icon} '{check['keyword']}': {'找到' if check['found'] else '未找到'}")

        if result.get("output"):
            print(f"\n输出预览 (前300字):")
            print(result["output"][:300] + "...")

        if result.get("error"):
            print(f"\n错误: {result['error']}")

    def run_skill_tests(self, skill: SkillDefinition, tests: List[TestCase]) -> List[dict]:
        """运行单个 Skill 的所有测试"""
        print(f"\n{'#'*80}")
        print(f"# {skill.name} ({skill.id}) 自动化测试")
        print(f"# 测试用例数: {len(tests)}")
        print(f"# 超时: {self.timeout}s")
        print(f"{'#'*80}\n")

        results = []
        for i, test_case in enumerate(tests, 1):
            print(f"\n进度: [{i}/{len(tests)}]")
            result = self.run_test_case(test_case, skill)
            results.append(result)

            # 测试间隔，避免 API 限流
            if i < len(tests):
                print(f"\n等待 2s...")
                time.sleep(2)

        return results

    def run_all_tests(self) -> List[dict]:
        """运行所有 Skill 的所有测试"""
        print(f"\n{'#'*80}")
        print(f"# SmartTwinRes Skills 自动化测试套件")
        print(f"# Skill 数: {len(SKILLS)}")
        print(f"# 超时: {self.timeout}s")
        print(f"{'#'*80}\n")

        all_results = []
        for skill in SKILLS:
            if not skill.enabled:
                print(f"\n⏭️  跳过 {skill.name} ({skill.id}) - 已禁用")
                continue

            # 获取该 skill 的测试用例
            tests = [t for t in ALL_TESTS if t.skill_id == skill.id]
            if not tests:
                print(f"\n⚠️  {skill.name} ({skill.id}) - 未定义测试用例")
                continue

            results = self.run_skill_tests(skill, tests)
            all_results.extend(results)

            # Skill 之间等待
            print(f"\n等待 5s 再进行下一个 Skill...")
            time.sleep(5)

        self.results = all_results
        return all_results

    def generate_report(self, format: str = "markdown") -> str:
        """生成测试报告"""
        if not self.results:
            return "No results"

        if format == "json":
            return self._generate_json_report()
        else:
            return self._generate_markdown_report()

    def _generate_json_report(self) -> str:
        """生成 JSON 格式报告"""
        # 按 skill 分组统计
        skill_stats = {}
        for skill in SKILLS:
            skill_results = [r for r in self.results if r["skill_id"] == skill.id]
            if skill_results:
                skill_stats[skill.id] = {
                    "name": skill.name,
                    "total": len(skill_results),
                    "passed": sum(1 for r in skill_results if r["status"] == "PASS"),
                    "failed": sum(1 for r in skill_results if r["status"] == "FAIL"),
                    "timeout": sum(1 for r in skill_results if r["status"] == "TIMEOUT"),
                    "error": sum(1 for r in skill_results if r["status"] == "ERROR"),
                }

        report = {
            "test_suite": "SmartTwinRes Skills 自动化测试",
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_tests": len(self.results),
            "passed": sum(1 for r in self.results if r["status"] == "PASS"),
            "failed": sum(1 for r in self.results if r["status"] == "FAIL"),
            "timeout": sum(1 for r in self.results if r["status"] == "TIMEOUT"),
            "error": sum(1 for r in self.results if r["status"] == "ERROR"),
            "skill_stats": skill_stats,
            "results": self.results
        }
        return json.dumps(report, indent=2, ensure_ascii=False)

    def _generate_markdown_report(self) -> str:
        """生成 Markdown 格式报告"""
        # 总体统计
        total = len(self.results)
        passed = sum(1 for r in self.results if r["status"] == "PASS")
        failed = sum(1 for r in self.results if r["status"] == "FAIL")
        timeout = sum(1 for r in self.results if r["status"] == "TIMEOUT")
        error = sum(1 for r in self.results if r["status"] == "ERROR")

        lines = [
            "# SmartTwinRes Skills 自动化测试报告",
            "",
            f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**测试套件**: SmartTwinRes Skills 自动化验证",
            "",
            "---",
            "",
            "## 测试结果汇总",
            "",
            f"| 指标 | 数值 |",
            f"|------|------|",
            f"| 总测试数 | {total} |",
            f"| ✅ 通过 | {passed} |",
            f"| ❌ 失败 | {failed} |",
            f"| ⏰ 超时 | {timeout} |",
            f"| ❌ 错误 | {error} |",
            f"| **通过率** | **{passed/total*100:.1f}%** |" if total > 0 else "",
            "",
            "---",
            "",
            "## Skill 级别统计",
            "",
        ]

        # Skill 级别统计
        for skill in SKILLS:
            skill_results = [r for r in self.results if r["skill_id"] == skill.id]
            if not skill_results:
                continue

            s_total = len(skill_results)
            s_passed = sum(1 for r in skill_results if r["status"] == "PASS")
            s_failed = sum(1 for r in skill_results if r["status"] == "FAIL")
            s_timeout = sum(1 for r in skill_results if r["status"] == "TIMEOUT")

            lines.extend([
                f"### {skill.name} ({skill.id})",
                "",
                f"| 指标 | 数值 |",
                f"|------|------|",
                f"| 总测试数 | {s_total} |",
                f"| ✅ 通过 | {s_passed} |",
                f"| ❌ 失败 | {s_failed} |",
                f"| ⏰ 超时 | {s_timeout} |",
                f"| **通过率** | **{s_passed/s_total*100:.1f}%** |" if s_total > 0 else "",
                "",
            ])

        lines.extend(["---", "", "## 详细结果", ""])

        # 按 Skill 分组显示详细结果
        for skill in SKILLS:
            skill_results = [r for r in self.results if r["skill_id"] == skill.id]
            if not skill_results:
                continue

            lines.extend([
                f"### {skill.name} ({skill.id})",
                "",
            ])

            for result in skill_results:
                status_icon = {"PASS": "✅", "FAIL": "❌", "TIMEOUT": "⏰", "ERROR": "❌"}.get(result["status"], "❓")
                lines.extend([
                    f"#### {result['id']}: {result['description']} {status_icon}",
                    "",
                    f"- **状态**: {result['status']}",
                    f"- **耗时**: {result['elapsed_seconds']}s",
                    f"- **问题**: {result['question']}",
                    "",
                ])

                if result.get("expected_keywords"):
                    lines.append("**关键词验证**:")
                    lines.append("")
                    for check in result.get("keyword_checks", []):
                        icon = "✓" if check["found"] else "✗"
                        lines.append(f"- {icon} `{check['keyword']}`")
                    lines.append("")

                if result.get("output"):
                    lines.extend([
                        "**输出预览**:",
                        "",
                        "```",
                        result["output"][:500],
                        "```",
                        "",
                    ])

                if result.get("error"):
                    lines.extend([
                        f"**错误**: {result['error']}",
                        "",
                    ])

                lines.append("---")
                lines.append("")

        return "\n".join(lines)


# =============================================================================
# 主程序
# =============================================================================

def main():
    """主程序入口"""
    import argparse

    parser = argparse.ArgumentParser(description="SmartTwinRes Skills 自动化测试")
    parser.add_argument("--list", action="store_true", help="列出所有测试用例")
    parser.add_argument("--skill", help="测试指定 Skill（如 forecasting）")
    parser.add_argument("--test-case", help="运行指定测试用例（如 F1）")
    parser.add_argument("--all", action="store_true", help="测试所有 Skill")
    parser.add_argument("--timeout", type=int, default=HERMES_TIMEOUT, help="测试超时（秒）")
    parser.add_argument("--report-format", choices=["markdown", "json"], default="markdown")
    parser.add_argument("--output", help="报告输出文件路径")

    args = parser.parse_args()

    # 创建测试目录
    if not RESULTS_DIR.exists():
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    TEST_RESULTS_DIR = RESULTS_DIR
    TEST_RESULTS_DIR.mkdir(exist_ok=True)

    # 列出测试用例
    if args.list:
        print("\n所有测试用例:")
        print(f"{'ID':<8} {'Skill':<15} {'描述':<30} {'超时'}")
        print("-" * 80)
        for test in ALL_TESTS:
            skill = next(s for s in SKILLS if s.id == test.skill_id)
            print(f"{test.id:<8} {skill.name:<15} {test.description:<30} {test.timeout}s")
        sys.exit(0)

    # 运行测试
    runner = SkillTestRunner(timeout=args.timeout)

    if args.test_case:
        # 运行单个测试用例
        test_case = next((t for t in ALL_TESTS if t.id == args.test_case.upper()), None)
        if not test_case:
            print(f"❌ 未找到测试用例: {args.test_case}")
            print(f"可用用例: {', '.join(t.id for t in ALL_TESTS)}")
            sys.exit(1)
        skill = next(s for s in SKILLS if s.id == test_case.skill_id)
        results = [runner.run_test_case(test_case, skill)]
    elif args.skill:
        # 测试指定 Skill
        skill = next((s for s in SKILLS if s.id == args.skill), None)
        if not skill:
            print(f"❌ 未找到 Skill: {args.skill}")
            print(f"可用 Skill: {', '.join(s.id for s in SKILLS)}")
            sys.exit(1)
        tests = [t for t in ALL_TESTS if t.skill_id == skill.id]
        results = runner.run_skill_tests(skill, tests)
    elif args.all:
        # 测试所有 Skill
        results = runner.run_all_tests()
    else:
        # 默认只测试 forecasting（已验证的）
        skill = next(s for s in SKILLS if s.id == "forecasting")
        tests = [t for t in ALL_TESTS if t.skill_id == "forecasting"]
        print("\n💡 提示: 使用 --all 测试所有 Skill，或 --skill <name> 指定 Skill")
        results = runner.run_skill_tests(skill, tests)

    # 生成报告
    report = runner.generate_report(format=args.report_format)

    # 输出报告
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(report, encoding='utf-8')
        print(f"\n📄 报告已保存: {output_path}")
    else:
        print(f"\n{'='*80}")
        print("测试报告")
        print(f"{'='*80}")
        print(report)

    # 保存原始结果
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    json_path = TEST_RESULTS_DIR / f"skills-test-results-{timestamp}.json"
    json_path.write_text(runner._generate_json_report(), encoding='utf-8')
    print(f"📄 JSON 结果已保存: {json_path}")

    # 返回退出码
    failed_count = sum(1 for r in results if r["status"] in ["FAIL", "TIMEOUT", "ERROR"])
    sys.exit(0 if failed_count == 0 else 1)


if __name__ == "__main__":
    main()
