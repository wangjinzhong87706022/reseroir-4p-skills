import os
import pathlib

# API
API_BASE = "http://localhost:9380/api/v1"
RAGFLOW_EMAIL = os.environ["RAGFLOW_EMAIL"]
RAGFLOW_PASSWORD = os.environ["RAGFLOW_PASSWORD"]
PUBLIC_PEM = "/opt/git/ragflow/conf/public.pem"

# Corpus roots (read-only)
DERIVED_ROOT = pathlib.Path("/home/scada/SmartTwinRes-skills/pdf_text_analysis")
ORIGINALS_ROOT = pathlib.Path("/home/scada/SmartTwinRes-skills/pdfs")

# Output root — create out/ directory now so later tasks can write into it
OUT_DIR = pathlib.Path("/home/scada/SmartTwinRes-skills/ragflow_import/out")
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Datasets (spec §2.1 + §2.2)
DATASETS = [
    {
        "key": "ds1",
        "name": "规程与预案",
        "chunk_method": "laws",
        "parser_config": {
            "chunk_token_num": 512,
            "auto_keywords": 10,
            "auto_questions": 3,
            "topn_tags": 3,
            "tag_kb_ids": [],
        },
        "graphrag_config": {
            "use_graphrag": True,
            "method": "light",
            "entity_types": ["FloodEvent", "Station", "Structure", "Person", "Regulation", "Parameter"],
            "resolution": True,
        },
        "raptor_config": {"use_raptor": True, "max_leaf_nodes": 10},
    },
    # ds2: naive, chunk_token_num=256, auto_keywords=8, topn_tags=3, no graphrag, no raptor
    {
        "key": "ds2",
        "name": "基础数据",
        "chunk_method": "naive",
        "parser_config": {
            "chunk_token_num": 256,
            "auto_keywords": 8,
            "auto_questions": 0,
            "topn_tags": 3,
            "tag_kb_ids": [],
        },
        "graphrag_config": {"use_graphrag": False},
        "raptor_config": {"use_raptor": False},
    },
    # ds3: naive/table, chunk_token_num=256, auto_questions=5, topn_tags=3, graphrag same as ds1, no raptor
    {
        "key": "ds3",
        "name": "洪水资料",
        "chunk_method": "naive",
        "parser_config": {
            "chunk_token_num": 256,
            "auto_keywords": 0,
            "auto_questions": 5,
            "topn_tags": 3,
            "tag_kb_ids": [],
        },
        "graphrag_config": {
            "use_graphrag": True,
            "method": "light",
            "entity_types": ["FloodEvent", "Station", "Structure", "Person", "Regulation", "Parameter"],
            "resolution": True,
        },
        "raptor_config": {"use_raptor": False},
    },
    # ds4: naive, chunk_token_num=256, auto_keywords=8, topn_tags=2, no graphrag, no raptor
    {
        "key": "ds4",
        "name": "组织管理",
        "chunk_method": "naive",
        "parser_config": {
            "chunk_token_num": 256,
            "auto_keywords": 8,
            "auto_questions": 0,
            "topn_tags": 2,
            "tag_kb_ids": [],
        },
        "graphrag_config": {"use_graphrag": False},
        "raptor_config": {"use_raptor": False},
    },
    # ds5: paper, chunk_token_num=512, auto_keywords=8, topn_tags=3, no graphrag, raptor use_raptor=True
    {
        "key": "ds5",
        "name": "工程资料",
        "chunk_method": "paper",
        "parser_config": {
            "chunk_token_num": 512,
            "auto_keywords": 8,
            "auto_questions": 0,
            "topn_tags": 3,
            "tag_kb_ids": [],
        },
        "graphrag_config": {"use_graphrag": False},
        "raptor_config": {"use_raptor": True, "max_leaf_nodes": 10},
    },
]

TAG_KB = {"key": "ds0", "name": "桃曲坡标签库", "chunk_method": "tag"}

# 11 metadata fields (spec §4.1)
METADATA_SCHEMA = [
    {"key": "doc_category",    "type": "string",  "description": "文档大类",           "enum": ["规程预案","基础数据","洪水资料","组织管理","工程资料"]},
    {"key": "sub_category",    "type": "string",  "description": "子类",               "enum": None},
    {"key": "flood_event",     "type": "string",  "description": "关联洪水事件",        "enum": ["2021-10","2020-8","2019-7","2013-7","2008-8","其他","历年统计"]},
    {"key": "doc_type",        "type": "string",  "description": "文档形态",           "enum": ["文本","表格","图片","图纸"]},
    {"key": "year",            "type": "number",  "description": "年份",               "enum": None},
    {"key": "source_format",   "type": "string",  "description": "来源格式",           "enum": ["pdf","word","excel","ocr_jpg","ocr_png","native_xlsx"]},
    {"key": "quality",         "type": "string",  "description": "OCR质量分级",         "enum": ["high","medium","low"]},
    {"key": "responsible_dept","type": "string",  "description": "责任/发文部门",        "enum": None},
    {"key": "doc_nature",      "type": "string",  "description": "文件性质",           "enum": ["法规","技术","管理","统计"]},
    {"key": "location",        "type": "string",  "description": "工程部位",            "enum": ["主坝","副坝一","副坝二","溢洪道","高洞","低洞","放水塔","库区","全库"]},
    {"key": "flood_magnitude", "type": "string",  "description": "洪水量级",            "enum": ["百年一遇","千年一遇","一般洪水","不适用"]},
]

# Top-level file assignments (spec §6 阶段0, 11 files)
TOP_LEVEL_ASSIGNMENTS = {
    "2026年桃曲坡水库调度规程_1__1_.pdf.txt":                             "ds1",
    "2026年桃曲坡水库大坝安全管理应急预案_1_.pdf.txt":                     "ds1",
    "2026年度桃曲坡水库汛期调度运用计划_2_.pdf.txt":                       "ds1",
    "2026年桃曲坡水库防洪抢险应急预案_1_.pdf.txt":                         "ds1",
    "_桃曲坡等三座大坝安全评价报告_.pdf.txt":                              "ds1",
    "桃曲坡水库大坝安全鉴定_OCR.txt":                                      "ds1",
    "关于转发_水利部办公厅关于切实做好渭河流域暴雨洪水防御工作的通知_的通知_陕水防明电_2021_7.pdf.txt": "ds1",
    "陕西省桃曲坡灌区水利工程管理范围及保护范围划界报告.pdf.txt":          "ds2",
    "水情通报第161期.pdf.txt":                                             "ds3",
    "重要水情快报_第121期_-总结预测.pdf.txt":                              "ds3",
    "汛情专报_20211006_OCR.txt":                                           "ds3",
}

# Flood event by subdir (spec §6 阶段0, flood_event field derivation)
FLOOD_EVENT_BY_SUBDIR = {
    "02-2021年洪水调度":  "2021-10",
    "03-2020年洪水(8-16)": "2020-8",
    "04-2019年洪水(9-14)": "2019-7",
    "05-2013年洪水(7-22)": "2013-7",
    "06-2008年洪水(8-22)": "2008-8",
    "07-其他洪水事件":      "其他",
    "08-历年洪水统计":     "历年统计",
}

# QA table detection keywords (spec §6 阶段1)
QA_TABLE_KEYWORDS = [
    "降雨量统计", "水位库容曲线推求", "防洪调度效益统计", "洪水统计",
    "洪水过程", "受损统计", "弃水计算", "下泄水量统计",
]

# VLM vision sources (spec §6 阶段1)
VISION_SOURCES = [
    ("05-基础数据与曲线/05-库容水位对照表.jpg", "库容水位对照表"),
    ("05-基础数据与曲线/06-泄流曲线.jpg",       "泄流曲线"),
]

# Textualized known values for cross-check (spec §6 阶段1)
TEXTUALIZED_VALUES = {
    "百年一遇泄量": "1454 m³/s",
    "千年一遇泄量": "2218 m³/s",
    "汛限水位":     "788.5 m",
}

# Longest-first for multi-pattern extraction
LOCATION_KEYWORDS = sorted([
    "主坝", "副坝一", "副坝二", "溢洪道", "高洞", "低洞", "放水塔", "库区", "全库",
], key=len, reverse=True)

DEPT_KEYWORDS = [
    "防汛办", "管理局", "设计院", "水务局", "应急管理局", "水利局",
    "桃曲坡水库管理局", "陕西省桃曲坡灌区",
]

SKIP_DIRS = {"video_analysis", "extracted", "repaired"}

# Import columns (spec §4.1)
IMPORT_COLS = [
    "rel", "native_xlsx_path", "dataset_key", "doc_category", "sub_category",
    "flood_event", "doc_type", "year", "source_format", "quality",
    "responsible_dept", "doc_nature", "location", "flood_magnitude",
    "skip_reason", "duplicate_of", "sha256",
]
