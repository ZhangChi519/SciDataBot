"""scidatabot 主入口"""

import asyncio
from pathlib import Path

from loguru import logger

from .core.scheduler import TaskScheduler
from .core.lane_scheduler import LaneScheduler, LaneConfig
from .tools.registry import ToolRegistry
from .tools.data_access import FormatDetector, MetadataExtractor, QualityAssessor
from .tools.intent_parser import IntentClassifier, PlanningGenerator
from .tools.data_processing import DataExtractor, DataTransformer, DataCleaner, StatisticsAnalyzer, MatFileExtractor
from .tools.data_integration import TemporalAligner, SpatialAligner, DataExporter
from .tools.data_access.weather import WeatherTool


def create_app(config: dict = None, confirm_callback=None):
    """创建应用"""
    config = config or {}

    workspace = Path(config.get("workspace", "~/.scidatabot")).expanduser()
    workspace.mkdir(parents=True, exist_ok=True)

    # 1. 创建 Provider - 从配置或CLI
    from .cli import create_llm_provider
    provider = create_llm_provider(config)
    logger.info(f"使用 LLM Provider: {provider.name}")

    # 2. 创建 Lane 调度器 (简化版)
    lane_scheduler = LaneScheduler()
    lane_scheduler.register_lane(LaneConfig("main", max_concurrent=1, timeout=300))
    lane_scheduler.register_lane(LaneConfig("subagent", max_concurrent=8, timeout=300))

    # 3. 创建工具注册表
    tool_registry = ToolRegistry()

    # 注册数据接入工具
    tool_registry.register(FormatDetector(), "data_access")
    tool_registry.register(MetadataExtractor(), "data_access")
    tool_registry.register(QualityAssessor(), "data_access")
    tool_registry.register(WeatherTool(), "data_access")

    # 注册通用工具 (web search, etc.)
    from src.tools.general import WebSearchTool, WebFetchTool, ExecTool, ReadFileTool, WriteFileTool, EditFileTool, ListDirTool
    tool_registry.register(WebSearchTool(), "general")
    tool_registry.register(WebFetchTool(), "general")
    tool_registry.register(ExecTool(), "general")
    tool_registry.register(ReadFileTool(), "general")
    tool_registry.register(WriteFileTool(), "general")
    tool_registry.register(EditFileTool(), "general")
    tool_registry.register(ListDirTool(), "general")

    # 注册意图解析工具
    tool_registry.register(IntentClassifier(), "intent_parser")
    tool_registry.register(PlanningGenerator(), "intent_parser")

    # 注册数据处理工具
    tool_registry.register(DataExtractor(), "data_processing")
    tool_registry.register(DataTransformer(), "data_processing")
    tool_registry.register(DataCleaner(), "data_processing")
    tool_registry.register(StatisticsAnalyzer(), "data_processing")
    tool_registry.register(MatFileExtractor(), "data_processing")

    # 注册数据整合工具
    tool_registry.register(TemporalAligner(), "data_integration")
    tool_registry.register(SpatialAligner(), "data_integration")
    tool_registry.register(DataExporter(), "data_integration")

    logger.info(f"注册了 {len(tool_registry)} 个工具")

    # 4. 创建任务调度器
    scheduler = TaskScheduler(
        provider=provider,
        workspace=workspace,
        tool_registry=tool_registry,
        lane_scheduler=lane_scheduler,
        confirm_callback=confirm_callback,
    )

    return scheduler


async def main():
    """主函数"""
    import sys

    logger.info("=" * 50)
    logger.info("scidatabot 启动")
    logger.info("=" * 50)

    # 加载配置 - 使用 main.py 所在目录的 config.yaml
    from .cli import load_config
    config_dir = Path(__file__).parent.parent
    config_path = config_dir / "config.yaml"
    config = load_config(str(config_path))

    # 创建应用 - 自动确认危险工具 (非交互模式)
    async def auto_confirm(tool_name: str, arguments: dict) -> bool:
        logger.info(f"危险工具请求: {tool_name} - 自动确认")
        return True
    
    scheduler = create_app(config, confirm_callback=auto_confirm)

    # 打印可用工具
    print("\n可用工具类别:")
    for cat in scheduler.tool_registry.list_categories():
        tools = scheduler.tool_registry.list_tools(cat)
        print(f"  {cat}: {', '.join(tools)}")

    # 示例请求
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "分析过去24小时北京和上海的PM2.5数据，比较两地污染水平"

    print(f"\n用户请求: {query}")
    print("-" * 50)

    # 执行
    result = await scheduler.execute(query)

    print("\n" + "=" * 50)
    print("结果:")
    print("=" * 50)
    print(result.get("final_report", "无结果"))


if __name__ == "__main__":
    asyncio.run(main())
