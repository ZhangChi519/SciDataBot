---
name: climate_description
description: 规范化语言标注。将CMIP6气候分级数据转换为自然语言描述，通过大模型API集成极端事件搜索功能，并将双语（英文/中文）格式化描述及极端事件回填至 JSONL 中。
type: skill
tags:
  - climate
  - language-generation
  - weather-description
  - extremes
  - nlg
  - llm
keywords:
  - 语言规范化
  - 自然语言生成
  - 大模型API
  - 极端事件
  - 双语输出
---

# 规范化语言标注 Skill

## 功能概述

该Skill将`CMIP6_CLIMATE_EXTREME_SKILL.md` 输出的 JSONL 分级数据，结合大模型API（LLM API），转换为包含地理与季节上下文的自然语言描述，最终将生成的英语天气描述写回原始 JSONL 结构中。

### 核心特性
- **数据与模型双驱动**：输入基于 JSONL 的气候分级数据，并调用大模型API进行文本润色与事件检索。
- **动态时空语境**：自动计算所在半球（南/北）及对应季节，融入描述中（如“处于北半球冬季的北京地区”）。
- **专业描述生成**：根据风速、降水、温度等级自动生成符合气象学规范的双语描述。
- **原地数据回填**：直接在输入的 JSONL 城市的节点下新增描述字段，便于下游直接调用。

### 处理流程
1. **遍历输入JSONL文件** → 逐个加载日期和城市数据
2. **计算时空语境** → 根据经纬度、月份确定半球、季节信息
3. **LLM调用** → 以英文为输出语言，生成 `summary`
4. **回写JSONL** → 将两个新字段写入原 JSONL 城市对象，保存文件

---

## 1. 输入数据说明

### 1.1 气候分级数据
接收来自`CMIP6_CLIMATE_EXTREME_SKILL.md` 的结构化 JSONL。

### 1.2 大模型 API 配置
- 需要传入可用的大模型 API 密钥及基础 URL（如 OpenAI 兼容接口）。
- **调用策略**：
  - **第一次调用（英文描述）**：使用标准 prompt，约束输出为单个英文段落，temperature 参数建议设为 0.3 保证确定性。 ⚠️ 注意：对于大气环境（atmospheric environment）的描述要基于API的理解生成

---

## 2. 语言规则与算法实现

### 2.1 语言风格
- You are a professional meteorologist writing concise official weather bulletins in the style of the China Meteorological Administration (CMA) and NOAA/NASA climate reports.
- Output must be a single plain English paragraph with NO numbers, NO bullet points, and NO markdown.
- Maintain a formal, authoritative tone throughout.

### 2.2 时空语境计算规则（半球与季节）
在组装提示词或模板前，需根据经纬度（lat, lon）计算时空信息：
- **半球判断**：
  - 纬度 `lat >= 0` 为北半球 (Northern Hemisphere)；`lat < 0` 为南半球 (Southern Hemisphere)。
- **季节判断**（基于月份和南北半球）：
| 月份 | 北半球 (lat > 0) | 南半球 (lat < 0) |
|---|---|---|
| 1 - 2  | Midwinter | Summer |
| 3 - 5  | Spring    | Autumn |
| 6 - 8  | Summer    | Winter |
| 9 - 11 | Autumn    | Spring |
| 12     | Midwinter | Midsummer |

### 2.3 英文总结`summary`生成流程
- 提取城市背景信息：
  - Date: {month}, {day}, {year}
  - City: {city["name"]}, {city["country"]} ({city["continent"]})
  - Latitude: {city["lat"]} ({"Northern" if lat >= 0 else "Southern"} Hemisphere)
- 提取城市当天天气等级：`temperature.grade`、`precipitation.grade`、`wind.grade`
- ⚠️ 生成注意事项：
  - You are given CMIP6 climate model weather data for a specific city and date.
  - The paragraph MUST begin with exactly: e.g. ("On July 21, 2012, in Pretoria").
  - Your task is to produce ONE formal English paragraph weather summary following these rules:
    - ONE paragraph only - no section headers, no bullet points, no markdown.
    - NO numerical values of any kind (no digits, no decimals, no percentages) except in date.
    - Formal, authoritative tone (modeled on CMA/NOAA climate bulletins).
    - Describe wind condition using only its anomaly grade relative to climatological baseline.
    - Describe precipitation using only its anomaly grade relative to climatological baseline.
    - Describe temperature using only its anomaly grade relative to climatological baseline.
    - Avoid overly repetitive expressions. Depending on the anomaly grade relative to climatological baseline, consider using more substantial vocabulary instead.
    - Include season information determined by hemisphere.
  - CMIP wind data contains speed only (no directional components), so use grades like "calm", "gentle", "moderate", "strong", etc. without specifying direction.
  - SEASON CONVENTION: 
    - Season is determined by hemisphere (Northern vs Southern) based on latitude.
    - Northern Hemisphere: Jan-Feb-Dec = winter, Mar-May = spring, Jun-Aug = summer, Sep-Nov = autumn.
    - Southern Hemisphere: seasons are reversed.

---

## 3. 最终输出格式

给定搜索请求后，不仅向终端返回自然语言描述，还需要将结果**直接追加写入原始 JSONL 数据的对应城市对象中**，新增以下一个字段：
1. `summary` — 字符串类型（单个段落），无数值、无 markdown 格式

**字段设计说明**：
- 字段类型为**字符串而非数组**（与示例中的数组格式保持一致需在实现时统一选择）。
- 推荐采用**字符串格式**以简化后续处理和展示。

### 目标输出 JSONL 示例

**CMIP6 场景输出：**
```jsonl
{"date": "2012-07-21", "year": 2012, "month": 7, "day": 21, "city": "Pretoria", "country": "South Africa", "continent": "Africa", "lat": -25.7449, "lon": 28.1878, "row": 45, "col": 20, "weather": {"wind": {"speed_ms": 3.444, "clim_mean_ms": 3.229, "clim_std_ms": 1.383, "delta": 0.214, "grade": "Normal"}, "precipitation": {"tp_mm_per_day": 0.0, "clim_mean_mm_per_day": 1.13, "clim_std_mm_per_day": 4.946, "log_clim_mean_mm_day": 0.756, "log_clim_std_mm_day": 1.783, "delta": -1.13, "grade": "Normal"}, "temperature": {"t2m_celsius": 0.142, "clim_mean_celsius": 7.194, "clim_std_celsius": 3.159, "delta_t": -7.052, "grade": "Extremely Low"}}, "extreme_categories": ["extreme_temperature_cold"], "summary": ["On July 21, 2012, in Pretoria, located in the Southern Hemisphere during winter, compared to climatic baseline values, temperatures were extremely low, wind speeds were near the climatic baseline, and precipitation was near the climatic baseline, resulting in an overall stable atmospheric environment that was consistent with regional seasonal dynamics."]}
