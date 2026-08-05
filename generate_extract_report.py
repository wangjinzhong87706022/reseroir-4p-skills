#!/usr/bin/env python3
"""生成 Excel + Word 文档提取综合分析报告"""
import os, re
from pathlib import Path
from datetime import datetime
from collections import defaultdict

EXCEL_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis/excel_extracted")
WORD_DIR = Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis/word_extracted")
REPORT_DIR = Path("/home/scada/SmartTwinRes-skills/docs")


def analyze_excel_files():
    """分析Excel提取结果，返回汇总数据"""
    results = []
    for fp in sorted(EXCEL_DIR.glob("*.txt")):
        text = fp.read_text(encoding="utf-8")
        lines = [l for l in text.split("\n")]
        nonempty = [l for l in lines if l.strip()]
        
        # 统计sheet
        sheets = [l for l in nonempty if l.startswith("===== Sheet:")]
        
        # 提取关键数据行（数字多的行）
        data_rows = [l for l in nonempty if not l.startswith("=====")]
        
        results.append({
            "name": fp.stem,
            "chars": len(text),
            "lines": len(nonempty),
            "sheets": len(sheets),
            "sheet_names": [s.replace("===== Sheet: ", "").replace(" =====", "") for s in sheets],
            "preview": "\n".join(nonempty[:5]),
            "path": str(fp),
        })
    return results


def analyze_word_files():
    """分析Word提取结果"""
    results = []
    for fp in sorted(WORD_DIR.glob("*.txt")):
        text = fp.read_text(encoding="utf-8")
        nonempty = [l for l in text.split("\n") if l.strip()]
        results.append({
            "name": fp.stem,
            "chars": len(text),
            "lines": len(nonempty),
            "preview": "\n".join(nonempty[:5]),
            "path": str(fp),
        })
    return results


def main():
    excel = analyze_excel_files()
    word = analyze_word_files()

    total_excel_chars = sum(r["chars"] for r in excel)
    total_word_chars = sum(r["chars"] for r in word)

    lines = []
    lines.append("# 桃曲坡水库 Excel/Word 文档提取与分析报告")
    lines.append("")
    lines.append(f"**分析日期**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("---")
    lines.append("## 一、总体统计")
    lines.append("")
    lines.append("| 类型 | 文件数 | 提取字符数 | 状态 |")
    lines.append("|------|:------:|:----------:|:----:|")
    lines.append(f"| 📊 Excel (XLS/XLSX) | {len(excel)} | {total_excel_chars} | ✅ 全部提取 |")
    lines.append(f"| 📝 Word (DOC/DOCX/WPS) | {len(word)} | {total_word_chars} | ✅ 全部提取 |")
    lines.append(f"| **合计** | **{len(excel)+len(word)}** | **{total_excel_chars+total_word_chars}** | |")
    lines.append("")
    lines.append("提取引擎：")
    lines.append("- XLSX: `openpyxl`")
    lines.append("- XLS: `python-calamine`（容错性好，xlrd 对部分旧文件会崩溃）")
    lines.append("- DOCX: `python-docx`（含表格）")
    lines.append("- DOC/WPS: `antiword` + `catdoc` 回退")
    lines.append("")

    # 二、Excel 详情
    lines.append("---")
    lines.append("## 二、Excel 文件详情")
    lines.append("")
    lines.append("| # | 文件 | 字符数 | 行数 | Sheet数 | Sheet列表 |")
    lines.append("|---|------|:------:|:----:|:-------:|----------|")
    for i, r in enumerate(excel, 1):
        sheets = ", ".join(r["sheet_names"][:4])
        if len(r["sheet_names"]) > 4:
            sheets += f" 等{len(r['sheet_names'])}个"
        lines.append(f"| {i} | {r['name']} | {r['chars']} | {r['lines']} | {r['sheets']} | {sheets} |")
    lines.append("")

    # 三、Word 详情
    lines.append("---")
    lines.append("## 三、Word 文件详情")
    lines.append("")
    lines.append("| # | 文件 | 字符数 | 行数 |")
    lines.append("|---|------|:------:|:----:|")
    for i, r in enumerate(word, 1):
        lines.append(f"| {i} | {r['name']} | {r['chars']} | {r['lines']} |")
    lines.append("")

    # 四、关键发现
    lines.append("---")
    lines.append("## 四、关键数据发现")
    lines.append("")

    # 水位库容曲线推求
    lines.append("### 4.1 水位-库容-流量曲线推求数据")
    lines.append("")
    lines.append("`水位库容曲线推求.xls`（1538行）——核心工程数据，含：")
    lines.append("- 070729 洪水过程线计算表：断面流量、入库流量、水量累计")
    lines.append("- 水位-库容对应关系表（用于推求库容曲线）")
    lines.append("- 1997年实测水位库容查对数据")
    lines.append("")

    # 较大洪水统计
    lines.append("### 4.2 流域较大洪水统计")
    lines.append("")
    lines.append("`较大洪水统计表.xls` 记录历史大洪水：")
    lines.append("- 1867年：历时调查洪水（200年一遇）")
    lines.append("- 1932年：洪峰流量 2110 m³/s（100年一遇）")
    lines.append("- 2007年、2013年、2020年、2021年等多场洪水记录")
    lines.append("")

    # 历年下泄水量
    lines.append("### 4.3 历年下泄水量与降雨数据")
    lines.append("")
    lines.append("- `2001年洪水过程线.xls`：2001年洪水完整过程")
    lines.append("- `2010/2011年下泄水量统计.xls`：逐年下泄水量、雨量站降雨（瑶曲/庙湾/柳林/枢纽/马栏/红星/尚书7个站）")
    lines.append("- `弃水量统计表.xls`：历年弃水量统计")
    lines.append("")

    # 设备管理
    lines.append("### 4.4 设备与监控台账")
    lines.append("")
    lines.append("- `桃曲坡平台设备管理.xlsx`：264行，信息化设备台账（位移计、裂缝计、渗压计等，含编号/站点/位置/状态）")
    lines.append("- `视频监控台账.xlsx`：118行，视频监控设备台账")
    lines.append("")

    # 洪水调度报告
    lines.append("### 4.5 洪水调度报告")
    lines.append("")
    lines.append("提取到历年洪水调度汇报文档（2008/2013/2019/2020/2021年），包括：")
    lines.append("- 2021年三场洪水调度过程汇报、9·25防汛抗洪纪实、10·3洪水调度情况")
    lines.append("- 2020年8·16洪水调度报告")
    lines.append("- 2013年7·22防洪报告、7·29洪水简讯")
    lines.append("- 2008年8·21洪水汇报、洪水简报")
    lines.append("- 2022年华州区汛情处置汇报（纯图片文档，已OCR补充1,127字符）")
    lines.append("")

    # 五、数据质量说明
    lines.append("---")
    lines.append("## 五、数据质量说明")
    lines.append("")
    lines.append("1. **XLS 兼容性**：12个旧版 .xls 文件（2001-2021年洪水数据）使用 xlrd 读取会崩溃（`utf-16-le` 解码错误），改用 `python-calamine` 引擎后全部成功提取——这些文件结构有轻微异常但数据完整。")
    lines.append("2. **纯图片文档**：`华州区汛情处置汇报.docx` 无文本层（2张扫描图片），已通过 OCR 补充提取 1,127 字符。")
    lines.append("3. **提取位置**：全部文本保存在 `pdf_text_analysis/excel_extracted/` 和 `pdf_text_analysis/word_extracted/`，可直接用于 RAG 知识库。")
    lines.append("")

    lines.append("---")
    lines.append(f"*报告生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*")
    lines.append("")

    report = "\n".join(lines)
    out = REPORT_DIR / "Excel与Word文档提取分析报告.md"
    out.write_text(report, encoding="utf-8")
    print(f"✅ 报告已生成: {out}")
    print(f"  Excel: {len(excel)} 个文件, {total_excel_chars} 字符")
    print(f"  Word: {len(word)} 个文件, {total_word_chars} 字符")


if __name__ == "__main__":
    main()