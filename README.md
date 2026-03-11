# scidatabot

科学数据智能助手 - 基于多智能体架构的科学数据处理系统

## 特性

- **多智能体架构**: 意图解析、数据接入、数据处理、数据整合
- **可扩展工具集**: 工具按类别组织，易于扩展
- **Lane 并发调度**: 支持真正并行处理
- **多渠道支持**: 控制台、Telegram、飞书、Webhook
- **通用 Agent**: Agent 本身是通用的，通过组合不同工具集实现不同功能
- **多 LLM 提供商**: 支持 OpenAI、Anthropic、MiniMax

## 环境要求

- Python 3.10+
- pip

## 安装

```bash
cd scidatabot

# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖 (需要取消设置 SOCKS 代理)
unset ALL_PROXY all_proxy
pip install loguru typer textual openai anthropic aiohttp aiofiles asyncpg aiomysql openpyxl pyarrow netCDF4 h5py pyyaml psutil croniter

# 或安装所有依赖
pip install -e ".[all]"
```

## 配置

配置文件为 `config.yaml`，主要配置项：

### LLM Provider 配置

```yaml
llm:
  # 可选: openai, anthropic, minimax
  provider: minimax

  minimax:
    api_key: "your-minimax-api-key"
    model: "MiniMax-M2.5"
    base_url: "https://api.minimax.chat/v1"
    temperature: 0.7
    max_tokens: 4096
```

### Agent 配置

```yaml
agent:
  name: "scidatabot"
  max_iterations: 40
  timeout: 300
```

### 渠道配置

```yaml
channel:
  # 可选: console, telegram, feishu, webhook
  type: console
```

## 运行

### 命令行模式

```bash
# 使用虚拟环境中的 Python
unset ALL_PROXY all_proxy
.venv/bin/python -m src.main "你的请求"

# 例如
.venv/bin/python -m src.main "分析 PM2.5 数据"
```

### TUI 模式

```bash
.venv/bin/python tui.py
```

### 使用启动脚本

```bash
# 需要先确保 .venv/bin/python 存在
./scidatabot.sh "你的请求"

# TUI 模式
./scidatabot.sh --tui
```

## 架构

```
用户请求
    │
    ▼
TaskScheduler (任务调度器)
    ├── 意图分类 (Intent Classifier)
    ├── 任务分解 (Planning Generator)
    ├── 执行调度 (Lane Scheduler)
    │   ├── main: 主任务
    │   ├── cron: 定时任务
    │   ├── subagent: 子代理
    │   └── nested: 嵌套任务
    └── 结果聚合
```

## 工具类别

### data_access (数据接入)
- `detect_format`: 格式检测
- `extract_metadata`: 元数据提取
- `assess_quality`: 质量评估
- `weather`: 天气数据获取

### intent_parser (意图解析)
- `classify_intent`: 意图分类
- `generate_plan`: 规划生成

### data_processing (数据处理)
- `extract_data`: 数据抽取
- `transform_data`: 数据转换
- `clean_data`: 数据清洗
- `analyze_statistics`: 统计分析
- `extract_mat_files`: MATLAB 文件提取

### data_integration (数据整合)
- `align_temporal`: 时间对齐
- `align_spatial`: 空间对齐
- `export_data`: 数据导出

### general (通用工具)
- `filesystem`: 文件系统操作
- `shell`: Shell 命令执行
- `web`: Web 请求
- `cron`: 定时任务

## 代码示例

```python
import asyncio
from scidatabot.src.main import create_app
import yaml

async def main():
    # 加载配置
    with open("config.yaml") as f:
        config = yaml.safe_load(f)
    
    # 创建应用
    scheduler = create_app(config)
    
    # 执行请求
    result = await scheduler.execute("分析 PM2.5 数据")
    print(result.get("final_report"))

asyncio.run(main())
```

## 项目结构

```
scidatabot/
├── config.yaml          # 配置文件
├── pyproject.toml       # 项目配置
├── src/
│   ├── main.py          # 主入口
│   ├── core/            # 核心模块
│   │   ├── scheduler.py # 任务调度器
│   │   ├── agent.py     # Agent 实现
│   │   └── lane_scheduler.py # Lane 调度器
│   ├── tools/           # 工具模块
│   │   ├── data_access/    # 数据接入
│   │   ├── intent_parser/  # 意图解析
│   │   ├── data_processing/ # 数据处理
│   │   ├── data_integration/ # 数据整合
│   │   └── general/        # 通用工具
│   ├── providers/      # LLM 提供商
│   ├── channels/       # 通信渠道
│   └── skills/         # 技能模块
├── tui.py              # TUI 界面
└── workspace/          # 工作目录
```

## License

MIT
