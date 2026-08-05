#!/usr/bin/env python3
"""
dag_order.py -- 场景 DAG 步骤顺序定义（供 supervisor_state.resume 断点续跑使用）。

DAG_ORDER: {scene: [stage_name, ...]} 按执行顺序排列。
stage_name 与 SKILL.md 中场景流程模板的步骤一一对应（step1..stepN）。
"""

DAG_ORDER = {
    # 场景 A：汛期暴雨研判调度（七步闭环）
    "A": [
        "step1",   # forecasting    雨情水情研判
        "step2",   # diagnosis      工情核查（渗压/渗流/位移）
        "step3",   # inspection     设备可调度性核查
        "step4",   # simulation     多方案洪水推演
        "step5",   # plan-gen       生成调度方案
        "step6",   # [仲裁]          方案 vs 仿真一致性
        "step7",   # chatbi         研判报告 + 台账 + 推送
    ],
    # 场景 B：大坝安全智能诊断
    "B": [
        "step1",   # diagnosis-verification 监测数据异常定位
        "step2",   # inspection    现场巡检/缺陷对照
        "step3",   # simulation    物理场仿真校验
        "step4",   # [仲裁]         风险定级 + 处置建议
        "step5",   # chatbi        诊断报告
    ],
    # 场景 C：日常精细化管控
    "C": [
        "step1",   # forecasting + inspection 水情 + 设备日常
        "step2",   # simulation    蓄水节律优化推演
        "step3",   # chatbi        日报台账
    ],
    # 场景 D：应急响应
    "D": [
        "step1",   # early-warning 险情研判
        "step2",   # plan-generation 应急调度方案
        "step3",   # simulation    方案推演校验
        "step4",   # [仲裁] + HITL 人工确认
        "step5",   # chatbi        应急报告 + 推送
    ],
}
