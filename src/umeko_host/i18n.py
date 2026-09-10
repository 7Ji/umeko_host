from __future__ import annotations

import os

from PySide6.QtCore import QLocale


_ZH_CN = {
    "Umeko Thermal Imaging": "Umeko 热成像",
    "Device": "设备",
    "Serial port": "串口",
    "Language": "语言",
    "Follow system": "跟随系统",
    "Simplified Chinese": "简体中文",
    "Refresh": "刷新",
    "Refresh serial port list": "刷新串口列表",
    "Connect": "连接",
    "Disconnect": "断开",
    "Connect or disconnect the thermal camera": "连接或断开热像仪",
    "Pause": "暂停",
    "Resume": "继续",
    "Freeze or resume the image while continuing to receive data": "冻结或继续画面，串口保持接收",
    "Device photos": "设备照片",
    "Browse and export photos stored on the camera": "浏览和导出相机内保存的照片",
    "Temperature": "温度",
    "Maximum: {value}": "最高温: {value}",
    "Minimum: {value}": "最低温: {value}",
    "Average: {value}": "平均温: {value}",
    "Center: {value}": "中心温: {value}",
    "Mouse position: {value}": "鼠标位置: {value}",
    "Display": "显示",
    "Palette": "色表",
    "Interpolation": "插值",
    "Bilinear": "双线性",
    "Nearest neighbor": "最近邻",
    "Automatic range": "自动量程",
    "Lower limit °C": "下限 °C",
    "Upper limit °C": "上限 °C",
    "Flip horizontally": "水平翻转",
    "Flip vertically": "垂直翻转",
    "Rotation": "旋转",
    "Export": "导出",
    "Not connected": "未连接",
    "Connecting": "连接中",
    "Receiving": "接收中",
    "Error": "错误",
    "Protocol: {value}": "协议: {value}",
    "Frame: {value}": "帧: {value}",
    "No serial ports found": "未发现串口设备",
    "Unable to connect": "无法连接",
    "Select a serial port.": "请选择一个串口设备。",
    "Device not connected": "设备未连接",
    "Connect the camera first.": "请先连接相机。",
    "Save thermal image": "保存热图",
    "PNG images (*.png)": "PNG 图片 (*.png)",
    "Save failed": "保存失败",
    "Unable to write PNG file.": "无法写入 PNG 文件。",
    "Save temperature matrix": "保存温度矩阵",
    "CSV files (*.csv)": "CSV 文件 (*.csv)",
    "Photos on camera": "相机内照片",
    "Refresh list": "刷新列表",
    "Photo information": "照片信息",
    "File: {value}": "文件: {value}",
    "Range: {value}": "范围: {value}",
    "Average: {value}": "平均: {value}",
    "Device values: {value}": "设备记录: {value}",
    "Export current photo": "导出当前照片",
    "Raw DAT": "原始 DAT",
    "Temperature CSV": "温度 CSV",
    "Thermal image PNG": "热图 PNG",
    "Export all": "批量导出全部",
    "Click refresh to read the device list": "点击刷新读取设备列表",
    "Connect the camera in the main window first.": "请先在主窗口连接相机。",
    "Reading photo list...": "正在读取照片列表...",
    "Downloading {filename}...": "正在下载 {filename}...",
    "Read failed: {error}": "读取失败: {error}",
    "{count} photos": "共 {count} 张照片",
    "Download of {filename} failed: {error}": "下载 {filename} 失败: {error}",
    "Unknown file": "未知文件",
    "Failed to parse {filename}: {error}": "解析 {filename} 失败: {error}",
    "Export failed: {error}": "导出失败: {error}",
    "Export failed": "导出失败",
    "Loaded {filename}": "已加载 {filename}",
    "Save original photo": "保存原始照片",
    "DAT files (*.dat)": "DAT 文件 (*.dat)",
    "Export complete": "导出完成",
    "No photos": "没有照片",
    "Refresh the photo list first.": "请先刷新照片列表。",
    "Select export directory": "选择批量导出目录",
    "Exported {count} photos": "已导出 {count} 张照片",
    "Exporting {filename}...": "正在导出 {filename}...",
    "Unable to export {filename}": "无法导出 {filename}",
    "Serial device": "串口设备",
    "Invalid photo filename": "照片文件名无效",
    "Device is not connected": "设备尚未连接",
    "Device response timed out": "设备响应超时",
    "Photo list not found in device response": "设备响应中没有照片列表",
    "Incomplete photo list JSON": "照片列表 JSON 不完整",
    "Invalid photo list": "照片列表格式无效",
    "Invalid photo entry": "照片条目格式无效",
    "Unsupported photo entry: {filename} ({size} bytes)": "不支持的照片条目: {filename} ({size} bytes)",
    "Incomplete photo download response": "照片下载响应不完整",
    "Invalid photo length: expected {expected}, received {actual} bytes": "照片长度错误: 期望 {expected}，收到 {actual} 字节",
    "Invalid photo temperature data": "照片温度数据无效",
    "Waiting for thermal image data": "等待热成像数据",
    "Grayscale": "灰度",
    "Inverted Grayscale": "反灰度",
}


def detect_language(locale_name: str | None = None) -> str:
    if locale_name is None:
        locale_name = next(
            (
                os.environ[name]
                for name in ("LC_ALL", "LC_MESSAGES", "LANG")
                if os.environ.get(name)
            ),
            QLocale.system().name(),
        )
    name = locale_name.split(".", 1)[0].replace("-", "_").lower()
    return "zh_CN" if name.startswith(("zh_cn", "zh_sg", "zh_hans")) else "en"


_language = detect_language()


def language() -> str:
    return _language


def set_language(value: str) -> None:
    """Set the UI language before constructing windows (primarily useful for tests)."""
    global _language
    _language = "zh_CN" if value == "zh_CN" else "en"


def tr(text: str, **values: object) -> str:
    translated = _ZH_CN.get(text, text) if _language == "zh_CN" else text
    return translated.format(**values) if values else translated


def palette_label(name: str) -> str:
    return tr(name)
