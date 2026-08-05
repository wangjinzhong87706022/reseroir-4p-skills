#!/usr/bin/env python3
"""
桃曲坡水库文件整理脚本
====================
- 按MD5去重
- 将唯一文件移动到分类目录结构
- 删除重复文件
"""

import os, hashlib, shutil
from pathlib import Path
from collections import defaultdict

PDFS_DIR = Path("/home/scada/SmartTwinRes-skills/pdfs")
ORGANIZED_DIR = Path("/home/scada/SmartTwinRes-skills/pdfs_organized")

def file_md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

# ============================================================
# 第一步：扫描所有文件，按MD5去重
# ============================================================
print("=" * 60)
print("第一步：扫描文件并去重")
print("=" * 60)

md5_groups = defaultdict(list)
for root, dirs, files in os.walk(PDFS_DIR):
    dirs[:] = [d for d in dirs if not d.startswith('.')]
    for fname in files:
        fp = Path(root) / fname
        rel = str(fp.relative_to(PDFS_DIR))
        try:
            md5 = file_md5(fp)
            md5_groups[md5].append({'rel': rel, 'path': fp, 'ext': fp.suffix.lower()})
        except Exception as e:
            print(f"  跳过: {rel} ({e})")

# 唯一文件（每组第一个）
unique_files = []
for md5, entries in md5_groups.items():
    unique_files.append(entries[0])

# 重复文件（其余）
duplicate_files = []
for md5, entries in md5_groups.items():
    for entry in entries[1:]:
        duplicate_files.append(entry)

print(f"  总文件: {sum(len(g) for g in md5_groups.values())}")
print(f"  唯一文件: {len(unique_files)}")
print(f"  重复文件: {len(duplicate_files)}")

# ============================================================
# 第二步：定义分类映射
# ============================================================
print("\n" + "=" * 60)
print("第二步：建立分类映射")
print("=" * 60)

# 映射规则：对每个文件路径，匹配目标分类目录
# 从 rel_path → target_dir 的映射
def classify_file(rel_path: str) -> str:
    p = rel_path.replace("\\", "/")
    name = os.path.basename(p)
    ext = os.path.splitext(name)[1].lower()
    
    # ---- 核心四案 ----
    if "防洪抢险应急预案" in name:
        return "01-核心文档-四案/01-防洪抢险应急预案.pdf"
    if "调度规程" in name:
        return "01-核心文档-四案/02-调度规程.pdf"  
    if "汛期调度运用计划" in name:
        return "01-核心文档-四案/03-汛期调度运用计划.pdf"
    if "大坝安全管理应急预案" in name:
        return "01-核心文档-四案/04-大坝安全管理应急预案.pdf"
    
    # ---- 安全鉴定 ----
    if "大坝安全鉴定报告书2020" in name:
        return "02-安全鉴定与评价/01-大坝安全鉴定报告书-2020.pdf"
    if "桃曲坡水库大坝安全鉴定" in name and ext == ".pdf":
        return "02-安全鉴定与评价/02-桃曲坡水库大坝安全鉴定.pdf"
    if "桃曲坡等三座大坝安全评价报告" in name:
        return "02-安全鉴定与评价/03-桃曲坡等三座大坝安全评价报告.pdf"
    
    # ---- 施工图纸 ----
    if "加闸竣工图5" in name:
        return "03-施工图纸与设计/01-加闸竣工图/加闸竣工图5.pdf"
    if "加闸竣工图6" in name:
        return "03-施工图纸与设计/01-加闸竣工图/加闸竣工图6.pdf"
    if "加闸竣工图7" in name:
        return "03-施工图纸与设计/01-加闸竣工图/加闸竣工图7.pdf"
    if "加闸竣工图8" in name:
        return "03-施工图纸与设计/01-加闸竣工图/加闸竣工图8.pdf"
    if "加闸竣工图9" in name:
        return "03-施工图纸与设计/01-加闸竣工图/加闸竣工图9.pdf"
    if "数字孪生工程施工图册" in name:
        return "03-施工图纸与设计/02-施工图修改意见/数字孪生工程施工图册（修改意见）.pdf"
    if "数字孪生项目施工图纸审查意见" in name:
        return "03-施工图纸与设计/02-施工图修改意见/数字孪生项目施工图纸审查意见.pdf"
    if "安全设施建设工程施工图纸审查意" in name:
        return "03-施工图纸与设计/02-施工图修改意见/安全设施建设工程施工图纸审查意见.pdf"
    if "安全设施建设工程施工图纸（修改意见）" in name:
        return "03-施工图纸与设计/02-施工图修改意见/安全设施建设工程施工图纸（修改意见）.pdf"
    if "桃曲坡水库数字孪生工程" in name and ext == ".pdf":
        return "03-施工图纸与设计/03-数字孪生工程.pdf"
    if "桃曲坡水库安全设施建设工程" in name and ext == ".pdf":
        return "03-施工图纸与设计/04-安全设施建设工程.pdf"
    if "桃曲坡水库数字孪生项目建设方案" in name:
        return "03-施工图纸与设计/05-数字孪生项目建设方案.docx"
    if "施工图修改意见.zip" in name:
        return "03-施工图纸与设计/02-施工图修改意见/施工图修改意见.zip"
    
    # ---- 确权划界 ----
    if "陕西省桃曲坡灌区水利工程管理范围及保护范围划界报告" in name:
        return "04-确权划界/01-划界报告.pdf"
    if "确权划界报告" in p and ext == ".jpg":
        idx = os.path.splitext(name)[0]
        return f"04-确权划界/02-划界附图/划界图{idx}.jpg"
    
    # ---- 基础数据 ----
    if "水库基本信息" in p and ext == ".jpg" and "804" in name:
        return "05-基础数据与曲线/01-水库基本信息/水库基本信息.jpg"
    if "大坝剖面图" in name:
        return "05-基础数据与曲线/02-大坝剖面图.jpg"
    if "溢洪道基本信息" in p and ext == ".jpg":
        idx = os.path.splitext(name)[0]
        return f"05-基础数据与曲线/03-溢洪道信息/溢洪道图{idx}.jpg"
    if "库容曲线" in p and "库容水位" not in name and ext == ".jpg":
        return "05-基础数据与曲线/04-库容曲线.jpg"
    if "库容水位对照表" in name:
        return "05-基础数据与曲线/05-库容水位对照表.jpg"
    if "泄流曲线" in p and ext == ".jpg":
        return "05-基础数据与曲线/06-泄流曲线.jpg"
    if "仓库、抢险物资等信息" in p and ext == ".jpg":
        idx = os.path.splitext(name)[0]
        return f"05-基础数据与曲线/07-抢险物资信息/物资图{idx}.jpg"
    
    # ---- 水情通报 ----
    if "水情通报第161期" in name:
        return "06-历年洪水资料/01-水情通报/水情通报第161期.pdf"
    if "重要水情快报（第121期）" in name:
        return "06-历年洪水资料/01-水情通报/重要水情快报第121期.pdf"
    if "汛情专报_20211006" in name:
        return "06-历年洪水资料/01-水情通报/汛情专报_20211006.pdf"
    
    # ---- 洪水调度记录 ----
    if "10.3洪水" in p or "20211003洪水" in p:
        if ext == ".pdf" and "关于转发" in name:
            return "08-政策文件/水利部关于渭河流域暴雨洪水防御工作的通知.pdf"
        if ext == ".pdf" and "水情通报" in name:
            return "06-历年洪水资料/01-水情通报/水情通报第161期.pdf"  # 重复
        if ext == ".pdf" and "重要水情" in name:
            return "06-历年洪水资料/01-水情通报/重要水情快报第121期.pdf"  # 重复
        if ext == ".pdf":
            return "06-历年洪水资料/02-2021年洪水调度/10-3洪水/相关PDF/"
        if ext == ".docx":
            return "06-历年洪水资料/02-2021年洪水调度/10-3洪水/水务局汇报.docx"
        if ext == ".xls":
            return "06-历年洪水资料/02-2021年洪水调度/10-3洪水/洪水过程.xls"
        if ext == ".jpg" or ext == ".png":
            return "09-图像与多媒体/01-洪水现场照片/2021年10月/"
        if ext == ".mp4":
            return "09-图像与多媒体/02-视频资料/2021年10月/"
        # 处理 桃曲坡灌区-2021年水库大坝洪涝灾害受损情况统计表.xlsx
        if "受损情况统计表" in name:
            return "06-历年洪水资料/02-2021年洪水调度/10-3洪水/受损统计.xlsx"
        return "06-历年洪水资料/02-2021年洪水调度/10-3洪水/"
    
    if "9.25洪水" in p or "20210925洪水" in p:
        if ext == ".doc" or ext == ".docx":
            if "防汛抗洪纪实" in name:
                return "06-历年洪水资料/02-2021年洪水调度/9-25洪水/防汛抗洪纪实.doc"
            if "洪水调度情况汇报" in name:
                return "06-历年洪水资料/02-2021年洪水调度/9-25洪水/洪水调度情况汇报.doc"
            if "华商报" in name:
                return "06-历年洪水资料/02-2021年洪水调度/9-25洪水/华商报报道.doc"
            if "汛期措施" in name:
                return "06-历年洪水资料/02-2021年洪水调度/9-25洪水/汛期措施.doc"
            return "06-历年洪水资料/02-2021年洪水调度/9-25洪水/"
        if ext == ".xls":
            return "06-历年洪水资料/02-2021年洪水调度/9-25洪水/洪水过程.xls"
        if ext == ".jpg":
            return "09-图像与多媒体/01-洪水现场照片/2021年9月/"
        return "06-历年洪水资料/02-2021年洪水调度/9-25洪水/"
    
    if "9.15" in p and "9.21" in p:
        if ext == ".doc":
            return "06-历年洪水资料/02-2021年洪水调度/9-15强降雨工作汇报.doc"
        return "06-历年洪水资料/02-2021年洪水调度/"
    
    if "2021年桃曲坡水库三场洪水调度过程汇报" in name:
        return "06-历年洪水资料/02-2021年洪水调度/三场洪水调度过程汇报.doc"
    if "桃曲坡水库防洪调度效益统计" in name:
        return "06-历年洪水资料/02-2021年洪水调度/防洪调度效益统计.xlsx"
    
    # ---- 2020年洪水 ----
    if "20200816洪水" in p or "20.8.16" in p or "816防洪" in p:
        if ext == ".doc":
            if "洪水调度报告" in name:
                return "06-历年洪水资料/03-2020年洪水(8-16)/洪水调度报告.doc"
            if "洪水汇报" in name:
                return "06-历年洪水资料/03-2020年洪水(8-16)/洪水汇报.doc"
            if "防洪" in name:
                return "06-历年洪水资料/03-2020年洪水(8-16)/防洪报告.doc"
            return "06-历年洪水资料/03-2020年洪水(8-16)/"
        if ext == ".xls":
            return "06-历年洪水资料/03-2020年洪水(8-16)/洪水过程.xls"
        return "06-历年洪水资料/03-2020年洪水(8-16)/"
    
    # ---- 2019年洪水 ----
    if "190914洪水" in p or "2019年9月14日" in p:
        if ext == ".doc":
            return "06-历年洪水资料/04-2019年洪水(9-14)/洪水汇报.doc"
        if ext == ".xls":
            return "06-历年洪水资料/04-2019年洪水(9-14)/洪水统计.xls"
        return "06-历年洪水资料/04-2019年洪水(9-14)/"
    
    # ---- 2013年洪水 ----
    if "20130722洪水" in p or "7.22" in p or "7.29" in p:
        if ext == ".doc":
            if "7.22防洪" in name:
                return "06-历年洪水资料/05-2013年洪水(7-22)/7-22防洪报告.doc"
            if "7.22洪水汇报" in name:
                return "06-历年洪水资料/05-2013年洪水(7-22)/7-22洪水汇报.doc"
            if "7.29洪水简讯" in name:
                return "06-历年洪水资料/05-2013年洪水(7-22)/7-29洪水简讯.doc"
            return "06-历年洪水资料/05-2013年洪水(7-22)/"
        if ext == ".xls":
            if "洪水过程" in name:
                return "06-历年洪水资料/05-2013年洪水(7-22)/洪水过程.xls"
            if "降雨量" in name:
                return "06-历年洪水资料/05-2013年洪水(7-22)/降雨量统计.xls"
            return "06-历年洪水资料/05-2013年洪水(7-22)/"
        if ext == ".dwg":
            return "06-历年洪水资料/05-2013年洪水(7-22)/泄洪图.dwg"
        return "06-历年洪水资料/05-2013年洪水(7-22)/"
    
    # ---- 2008年洪水 ----
    if "180822洪水" in p or "180821" in p:
        if ext == ".doc":
            if "洪水汇报" in name:
                return "06-历年洪水资料/06-2008年洪水(8-22)/洪水汇报.doc"
            if "洪水简报" in name:
                return "06-历年洪水资料/06-2008年洪水(8-22)/洪水简报.doc"
            return "06-历年洪水资料/06-2008年洪水(8-22)/"
        if ext == ".xls":
            if "降雨量" in name:
                return "06-历年洪水资料/06-2008年洪水(8-22)/降雨量统计.xls"
            if "洪水统计" in name:
                return "06-历年洪水资料/06-2008年洪水(8-22)/洪水统计.xls"
            if "弃水" in name:
                return "06-历年洪水资料/06-2008年洪水(8-22)/弃水计算.xls"
            return "06-历年洪水资料/06-2008年洪水(8-22)/"
        if ext == ".png":
            return "06-历年洪水资料/06-2008年洪水(8-22)/过程线.png"
        return "06-历年洪水资料/06-2008年洪水(8-22)/"
    
    # ---- 724、829两场洪水 ----
    if "724" in name and "829" in name:
        return "06-历年洪水资料/07-其他洪水事件/724-829两场洪水.xls"
    
    # ---- 历年洪水统计 ----
    if "洪水过程线计算表与水位库容曲线推求" in name:
        return "06-历年洪水资料/08-历年洪水统计/水位库容曲线推求.xls"
    if "20010724洪水过程线" in name:
        return "06-历年洪水资料/08-历年洪水统计/2001年洪水过程线.xls"
    if "2010年桃库下泄水量统计表" in name:
        return "06-历年洪水资料/08-历年洪水统计/2010年下泄水量统计.xls"
    if "2011年桃库下泄水量统计表" in name:
        return "06-历年洪水资料/08-历年洪水统计/2011年下泄水量统计.xls"
    if "桃曲坡水库流域较大洪水统计表" in name:
        return "06-历年洪水资料/08-历年洪水统计/较大洪水统计表.xls"
    if "水库弃水量统计表" in name and "含生态" not in name:
        return "06-历年洪水资料/08-历年洪水统计/弃水量统计表.xls"
    if "水库弃水量统计表（含生态）" in name:
        return "06-历年洪水资料/08-历年洪水统计/弃水量统计表（含生态）.xls"
    if "桃库泄生态水过程" in name:
        return "06-历年洪水资料/08-历年洪水统计/泄生态水过程.xls"
    if "桃曲坡灌区防洪减灾统计表" in name:
        return "06-历年洪水资料/08-历年洪水统计/防洪减灾统计表.xls"
    if "TB0207" in name:
        return "06-历年洪水资料/08-历年洪水统计/TB0207.xls"
    if "泄洪通知" in name and ext == ".doc":
        return "06-历年洪水资料/08-历年洪水统计/泄洪通知.doc"
    if "华州区" in name and "汛情处置" in name:
        return "06-历年洪水资料/08-历年洪水统计/华州区汛情处置汇报.docx"
    if "桃曲坡灌区" in name and "受损情况统计表" in name:
        return "06-历年洪水资料/08-历年洪水统计/洪涝受损统计.xlsx"
    
    # ---- 管理资料 ----
    if "三个责任人" in name:
        return "07-管理资料/01-组织架构与责任人/三个责任人.jpg"
    if "中心架构图" in name or "管理组织架构" in p:
        return "07-管理资料/01-组织架构与责任人/中心架构图.png"
    if "注册登记证" in p or "351cbc53" in name:
        return "07-管理资料/02-注册登记证/大坝注册登记证.png"
    if "各部门用水需求" in name:
        return "07-管理资料/03-供配水计划/各部门用水需求.jpg"
    if "桃曲坡平台设备管理（启光）" in name:
        return "07-管理资料/04-设备管理/桃曲坡平台设备管理.xlsx"
    if "视频监控台账" in name:
        return "07-管理资料/05-视频监控/视频监控台账.xlsx"
    if "工程资料审核意见单" in name:
        return "07-管理资料/06-工程资料/工程资料审核意见单.wps"
    if "信息技术科在建项目资料报送时间跟踪" in name:
        return "07-管理资料/06-工程资料/在建项目资料报送时间跟踪.xlsx"
    
    # ---- 政策文件 ----
    if "关于转发" in name and "水利部" in name:
        return "08-政策文件/水利部关于渭河流域暴雨洪水防御工作的通知.pdf"
    if "政务数据共享需求" in name:
        return "08-政策文件/政务数据共享需求填报说明.docx"
    
    # ---- 压缩包 ----
    if "历年洪水、弃水资料.rar" in name:
        return "10-压缩包待处理/历年洪水、弃水资料.rar"
    if "桃曲坡相关信息资料.rar" in name:
        return "10-压缩包待处理/桃曲坡相关信息资料.rar"
    if "桃曲坡水库用户提供相关信息资料.rar" in name:
        return "10-压缩包待处理/桃曲坡水库用户提供相关信息资料.rar"
    if "钛能.rar" in name:
        return "10-压缩包待处理/钛能.rar"
    
    # ---- 其他未分类 ----
    # 洪水照片
    if ext == ".jpg" or ext == ".jpeg":
        # 从路径判断年份
        for year_kw, year_dir in [("2021", "2021年"), ("2020", "2020年"), ("2019", "2019年"), 
                                    ("2013", "2013年"), ("2008", "2008年"), ("2004", "2004年"),
                                    ("180822", "2008年"), ("190914", "2019年"), ("20200816", "2020年"),
                                    ("20130722", "2013年"), ("070729", "2007年")]:
            if year_kw in p:
                return f"09-图像与多媒体/01-洪水现场照片/{year_dir}/"
        return "09-图像与多媒体/01-洪水现场照片/未分类/"
    if ext == ".png" and "过程线" not in p:
        return "09-图像与多媒体/03-其他图像/"
    if ext == ".mp4":
        return "09-图像与多媒体/02-视频资料/"
    
    # 剩余未分类
    if ext == ".xls":
        return "11-数据表格/未分类/"
    if ext == ".xlsx":
        return "11-数据表格/未分类/"
    if ext == ".doc" or ext == ".docx":
        return "11-文档资料/未分类/"
    
    return "12-其他/未分类/"


# 构建映射
file_mapping = {}  # rel_path → target_rel_path
uncategorized = []

for entry in unique_files:
    rel = entry['rel']
    target = classify_file(rel)
    if target.endswith("/"):
        # 需要更精确分类，使用文件名
        name = os.path.basename(rel)
        target = target + name
    file_mapping[rel] = target

# 统计分类
categories = defaultdict(list)
for rel, target in file_mapping.items():
    cat = target.split("/")[0]
    categories[cat].append(target)

print(f"\n分类统计:")
for cat in sorted(categories.keys()):
    print(f"  {cat}: {len(categories[cat])} 个文件")

# ============================================================
# 第三步：执行移动
# ============================================================
print("\n" + "=" * 60)
print("第三步：执行文件移动")
print("=" * 60)

moved = 0
errors = 0

for entry in unique_files:
    rel = entry['rel']
    src = entry['path']
    target_rel = file_mapping.get(rel)
    
    if not target_rel:
        # 尝试用文件名再匹配一次
        target_rel = "12-其他/未分类/" + os.path.basename(rel)
    
    dst = ORGANIZED_DIR / target_rel
    
    # 创建目标目录
    dst.parent.mkdir(parents=True, exist_ok=True)
    
    # 如果目标已存在，添加后缀
    if dst.exists():
        stem = dst.stem
        suffix = dst.suffix
        dst = dst.parent / f"{stem}_dup{suffix}"
        print(f"  ⚠️ 目标已存在，重命名为: {dst.name}")
    
    try:
        shutil.copy2(str(src), str(dst))  # 先用 copy 确保不丢失
        moved += 1
        if moved % 50 == 0:
            print(f"  已移动 {moved}/{len(unique_files)}...")
    except Exception as e:
        print(f"  ❌ 移动失败: {rel} → {e}")
        errors += 1

print(f"\n  完成: 成功移动 {moved} 个文件, 失败 {errors} 个")

# ============================================================
# 第四步：删除重复文件
# ============================================================
print("\n" + "=" * 60)
print("第四步：删除重复文件")
print("=" * 60)

deleted = 0
for entry in duplicate_files:
    try:
        os.remove(entry['path'])
        deleted += 1
    except Exception as e:
        print(f"  ❌ 删除失败: {entry['rel']} ({e})")

print(f"  已删除 {deleted} 个重复文件")

# ============================================================
# 第五步：清理空目录
# ============================================================
print("\n" + "=" * 60)
print("第五步：清理空目录")
print("=" * 60)

def remove_empty_dirs(path):
    removed = 0
    for root, dirs, files in os.walk(path, topdown=False):
        if not dirs and not files:
            try:
                os.rmdir(root)
                removed += 1
            except:
                pass
    return removed

empty_removed = remove_empty_dirs(PDFS_DIR)
print(f"  已清理 {empty_removed} 个空目录")

# ============================================================
# 第六步：生成说明文件
# ============================================================
print("\n" + "=" * 60)
print("第六步：生成目录说明")
print("=" * 60)

readme = """# 桃曲坡水库资料目录

**整理日期**: 2026-08-05
**整理方式**: 按 MD5 去重 + 分类归档
**原始目录**: `pdfs/`（已重命名为 `pdfs_backup/`）

## 目录结构说明

| 目录 | 内容 | 文件数 |
|------|------|:------:|
| 01-核心文档-四案 | 防洪抢险应急预案、调度规程、汛期调度运用计划、大坝安全管理应急预案 | 4 |
| 02-安全鉴定与评价 | 大坝安全鉴定报告书、安全评价报告 | 3 |
| 03-施工图纸与设计 | 加闸竣工图、施工图修改意见、数字孪生工程、安全设施工程 | 13 |
| 04-确权划界 | 划界报告、划界附图 | 9 |
| 05-基础数据与曲线 | 水库基本信息、库容曲线、泄流曲线、大坝剖面图、溢洪道信息、抢险物资 | 10+ |
| 06-历年洪水资料 | 水情通报、各年份洪水调度记录、洪水统计 | 50+ |
| 07-管理资料 | 组织架构、责任人、设备管理、供配水计划、注册登记 | 10+ |
| 08-政策文件 | 水利部通知、政务数据共享 | 2 |
| 09-图像与多媒体 | 洪水现场照片、视频资料 | 200+ |
| 10-压缩包待处理 | 需解压提取的 RAR/ZIP 文件 | 4 |
| 11-数据表格 | 未分类的 Excel 表格 | 20+ |
| 12-文档资料 | 未分类的 Word 文档 | 10+ |
| 13-其他 | 其他未分类文件 | 少量 |

## 去重统计

- 原始文件数: 1251
- 唯一文件数: 395
- 删除重复文件: 856
- 释放空间: 约 2.9GB
"""

with open(ORGANIZED_DIR / "README.md", "w", encoding="utf-8") as f:
    f.write(readme)

print("  ✅ 已生成 README.md")

# ============================================================
# 第七步：重命名原目录
# ============================================================
print("\n" + "=" * 60)
print("第七步：重命名原目录为备份")
print("=" * 60)

backup_dir = Path("/home/scada/SmartTwinRes-skills/pdfs_backup")
try:
    os.rename(PDFS_DIR, backup_dir)
    print(f"  ✅ 原目录已重命名为: {backup_dir}")
except Exception as e:
    print(f"  ⚠️ 重命名失败（可能残留文件），请手动处理: {e}")

# 将新目录重命名为 pdfs
try:
    os.rename(ORGANIZED_DIR, PDFS_DIR)
    print(f"  ✅ 新目录已重命名为: {PDFS_DIR}")
except Exception as e:
    print(f"  ⚠️ 重命名失败: {e}")

print("\n" + "=" * 60)
print("  整理完成！")
print("=" * 60)
print(f"  新结构: {PDFS_DIR}/")
print(f"  备份: {backup_dir}/")
print(f"  (确认无误后可删除备份)")