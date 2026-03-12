"""任务调度器 - 意图分类、任务分解、执行"""

import json
import os
import re
import uuid
from pathlib import Path
from typing import Any, Optional, Callable, Awaitable
from concurrent.futures import ProcessPoolExecutor, as_completed

from loguru import logger

from .agent import GeneralAgent, ExecutionContext
from .lane_scheduler import LaneScheduler


class TaskScheduler:
    """
    任务调度器

    流程：
    1. 意图分类 (Intent Classification)
    2. 任务分解 (Task Decomposition)
    3. 执行调度 (Execution Scheduling)
    4. 结果聚合 (Result Aggregation)
    """

    class TodoList:
        """动态 Todo 列表"""
        def __init__(self, title: str):
            self.title = title
            self.items: list[str] = []
            self.status: list[str] = []
        
        def add(self, item: str, status: str = "○") -> int:
            """添加新条目，返回索引"""
            self.items.append(item)
            self.status.append(status)
            return len(self.items) - 1
        
        def update(self, index: int, status: str):
            """更新条目状态"""
            if 0 <= index < len(self.status):
                self.status[index] = status
        
        def complete(self, index: int):
            """标记为完成"""
            self.update(index, "✓")
        
        def fail(self, index: int):
            """标记为失败"""
            self.update(index, "✗")
        
        def pending(self, index: int):
            """标记为进行中"""
            self.update(index, "⚙")
        
        def skip(self, index: int):
            """标记为跳过"""
            self.update(index, "⏭")
        
        def format(self) -> str:
            """格式化显示"""
            if not self.items:
                return ""
            # 标题如果已经包含 emoji，就不重复添加
            title_prefix = "" if self.title.startswith("📋") else "📋 "
            lines = [f"\n{'='*60}"]
            lines.append(f"  {title_prefix}{self.title}")
            lines.append('='*60)
            for i, (item, s) in enumerate(zip(self.items, self.status), 1):
                lines.append(f"  {s} {i}. {item}")
            lines.append('='*60 + '\n')
            return '\n'.join(lines)
        
        def log(self, logger):
            """输出到日志"""
            logger.info(self.format())

    def _print_todo(self, todo: TodoList):
        """打印 todo list 到日志"""
        todo.log(logger)

    def __init__(
        self,
        provider: "LLMProvider",
        workspace: Path,
        tool_registry: "ToolRegistry",
        lane_scheduler: LaneScheduler,
        confirm_callback: Optional[Callable[[str, dict], Awaitable[bool]]] = None,
    ):
        self.provider = provider
        self.workspace = workspace
        self.tool_registry = tool_registry
        self.lane_scheduler = lane_scheduler
        self.confirm_callback = confirm_callback

        # 简单模式对话历史
        self.simple_history: list[dict] = []

        # ============================================================
        # 架构说明 (Lane vs Agent vs 工具分类):
        # 
        # 1. Lane调度器: 控制任务并发 (main, cron, subagent, nested)
        #    - 按OpenClaw风格，区分执行上下文
        #    - 决定"什么时候"执行任务
        #
        # 2. Agent角色: 实际执行任务的智能体
        #    - coordinator: 协调者 (意图分类、任务分解、结果聚合)
        #    - data_access: 数据接入 (格式检测、元数据提取)
        #    - processor: 数据处理 (MAT解析、清洗、转换)
        #    - integrator: 数据整合 (时空对齐、导出)
        #    - 决定"谁来执行"任务
        #
        # 3. 工具分类: 工具的组织方式
        #    - data_access, data_processing, data_integration, intent_parser
        #    - 决定"用什么工具"
        # ============================================================

        # 获取各种工具集
        coordinator_tools = tool_registry.get_subset(["intent_parser", "data_processing", "data_integration", "general", "data_access"])
        simple_tools = tool_registry.get_subset(["general", "data_access", "data_processing", "data_integration"])
        tools_list = coordinator_tools.list_tools()
        simple_tools_list = simple_tools.list_tools()
        tools_desc = "\n".join([f"- {name}" for name in tools_list])
        simple_tools_desc = "\n".join([f"- {name}" for name in simple_tools_list])

        # ============================================================
        # 简单模式 Agent - 用于直接对话模式
        # ============================================================
        simple_agent_prompt = f"""你是 SciDataBot，一个专业的科学数据助手。

直接使用工具完成用户任务并返回结果。

## 可用工具
{simple_tools_desc}

## 工具使用说明
1. **天气查询** - 使用 weather(city="城市名", operation="current"或"forecast")
2. **网络搜索** - 使用 web_search(query="搜索内容") 获取网上信息
3. **网页抓取** - 使用 web_fetch(url="网址") 获取网页内容
4. **文件导出** - 使用 export_data(input_data="JSON数据", output_path="文件路径", format="json/csv/txt")
5. **文件处理** - detect_format, extract_data, transform_data, clean_data
6. **Shell命令** - 使用 exec(command="命令") 执行系统命令
7. **文件读写** - read_file, write_file, edit_file, list_dir

## 重要提示
1. **理解上下文**: 如果用户问题很短（如"装好了吗？"），结合历史对话理解用户指的是什么
2. **检查Python包**: 想知道包是否安装，用 exec 执行 `pip show 包名` 或 `python -c "import 包名"`
3. **检查文件是否存在**: 用 list_dir 或 read_file 查看
4. **当用户请求下载数据时**，必须：
   1. 使用 web_search 搜索
   2. 使用 web_fetch 抓取数据
   3. **使用 export_data 将数据保存到工作目录**
5. 工作目录是 ./workspace，使用相对路径如 "data/p450_enzymes.tsv"
6. 保存后告诉用户文件保存路径

直接执行任务，不要询问用户确认。"""

        # ============================================================
        # 数据准备模式 Agent - 用于结构化任务处理
        # ============================================================
        planning_agent_prompt = f"""你是 Planner，一个专业的科学数据助手。

你的职责是将用户的数据处理任务分解为结构化的执行步骤。

## 可用工具
{tools_desc}

## 工具使用说明
1. **网络搜索** - 使用 web_search(query="搜索内容") 获取网上信息
2. **网页抓取** - 使用 web_fetch(url="网址") 获取网页内容
3. **文件导出** - 使用 export_data(input_data="JSON数据", output_path="文件路径", format="json/csv/txt")
4. **天气查询** - weather(city="城市名", operation="current"/"forecast")

## 工作流程
1. 理解用户需求
2. 进行意图分类
3. 分解为可执行的任务（优先使用工具）
4. 调度执行
5. 聚合结果

## 重要提示
- 你必须使用上述工具来处理用户请求
- 当工具返回结果后，继续处理或汇总结果
- 不要说工具不可用，你拥有上述所有工具

## 任务指南 (task_guide) 强制要求
每个任务指南必须包含以下字段：
1. task: 任务描述 (如 "解析目录 /data/xxx 下的所有 .txt 文件")
2. tool: 使用的工具 (如 data_access, data_processing)
3. inputs: 输入路径或数据
4. outputs: 输出描述
5. result_mode: 必须是 context | file | return 之一 (必填)
   - context: 结果存入上下文
   - file: 结果保存到文件
   - return: 直接返回结果
6. 如果 result_mode=file:
   - result_path: 保存路径，如未指定，默认写入 workspace/ 目录
7. save_format: 保存格式，如未指定，默认 json (可选)

## 能力扩展
- 当发现工具能力不足时，可以**直接调用 API** 获取数据（如 UniProt API: https://rest.uniprot.org/uniprotkb/search）
- 使用 web_fetch 可以获取任何公开 API 的返回结果
- 获取数据后用 export_data 保存"""

        # 创建智能体
        # 注意: planning 只能用意图解析工具，不能执行数据处理（避免 Step 1 就开始处理数据）
        self.agents = {
            "planning": GeneralAgent(
                "Planner",
                provider,
                workspace,
                tool_registry.get_subset(["intent_parser"]),
                system_prompt=planning_agent_prompt,
            ),
            "data_access": GeneralAgent(
                "DataAccess",
                provider,
                workspace,
                tool_registry.get_subset(["data_access"]),
            ),
            "processor": GeneralAgent(
                "Processor",
                provider,
                workspace,
                tool_registry.get_subset(["data_processing"]),
            ),
            "integrator": GeneralAgent(
                "Integrator",
                provider,
                workspace,
                tool_registry.get_subset(["data_integration"]),
            ),
        }

        # 简单模式专用 Agent
        self.simple_agent = GeneralAgent(
            "SciDataBot",
            provider,
            workspace,
            simple_tools,
            system_prompt=simple_agent_prompt,
            max_iterations=20,
            confirm_callback=confirm_callback,
        )

        # ============================================================
        # 新架构组件: MainAgent, TaskPlanner, Executor, Processor, Integrator
        # ============================================================
        # 导入新组件
        from src.core.agents import MainAgent, TaskPlanner, Executor, Processor, Integrator

        # 创建通用 Agent (用于新架构)
        general_tools = tool_registry.get_subset(["general", "data_access", "data_processing", "data_integration"])
        general_agent = GeneralAgent(
            "GeneralAgent",
            provider,
            workspace,
            general_tools,
            system_prompt="你是一个通用的任务执行助手，负责根据任务描述执行相应操作。",
            max_iterations=10,
        )

        # 初始化各个组件
        self.main_agent = MainAgent(general_agent, tool_registry)
        self.task_planner = TaskPlanner(general_agent, tool_registry)
        self.executor = Executor(general_agent, tool_registry)
        self.processor = Processor(general_agent, tool_registry, self.lane_scheduler)
        self.integrator = Integrator(general_agent, tool_registry)

        # 延迟创建 Agent 池 - 仅在实际需要时创建
        self._mat_agents = None
        self._provider = provider
        self._workspace = workspace
        self._tool_registry = tool_registry

        # 注册事件处理器
        self.lane_scheduler.register_event(
            "task_timeout",
            handler=self._handle_task_timeout,
            config={"timeout": 60, "timeout_strategy": "react"}
        )

    async def _handle_task_timeout(self, task_info: dict, context: "ExecutionContext") -> dict:
        """处理任务超时事件 - 返回超时信息供 planning 重规划"""
        logger.warning(f"任务超时: {task_info.get('task_name', 'unknown')}")
        
        return {
            "timeout": True,
            "task": task_info,
            "error": f"Task {task_info.get('task_name')} timeout",
            "timeout_strategy": "react"
        }

    @property
    def mat_agents(self):
        """延迟创建MAT处理Agent池"""
        if self._mat_agents is None:
            cpu_count = os.cpu_count() or 4
            mat_tools = self._tool_registry.get_subset(["data_processing"])
            mat_prompt = """你是数据处理专家，负责从各种格式的文件中提取信息。

你可以使用各种数据处理工具来完成任务。
根据文件格式选择合适的处理方法。

处理完成后，返回处理结果摘要。"""

            self._mat_agents = []
            for i in range(min(cpu_count, 8)):
                agent = GeneralAgent(
                    f"DataProcessor-{i+1}",
                    self._provider,
                    self._workspace,
                    mat_tools,
                    system_prompt=mat_prompt,
                )
                self._mat_agents.append(agent)
            
            logger.info(f"创建了 {len(self._mat_agents)} 个数据处理 Agent")
        
        return self._mat_agents

    async def execute(self, user_request: str) -> dict:
        """执行用户请求 - 新架构
        
        流程:
        1. IntentParser - 意图解析 (React Loop)
        2. TaskPlanner - 任务规划 (React Loop)
        3. Executor/Processor - 执行 (串行/并行)
        4. Integrator - 整合结果
        """
        
        from src.core.agent import ExecutionContext
        import time
        import uuid
        
        total_start = time.time()
        
        context = ExecutionContext(
            request_id=str(uuid.uuid4())[:8],
            user_input=user_request,
        )
        
        logger.info(f"[{context.request_id}] [新架构] 开始处理: {user_request[:50]}...")
        
        try:
            # Step 1: MainAgent - 主智能体直接执行，并判断是否需要并行
            logger.info(f"[{context.request_id}] Step 1: 主智能体执行 📊")
            step_start = time.time()
            main_result = await self.main_agent.execute(user_request, context)
            logger.info(f"[{context.request_id}] ✓ 主智能体执行完成 (耗时: {time.time()-step_start:.2f}s)")
            
            # 判断是否需要并行
            if not main_result.get("need_parallel"):
                # 不需要并行，直接返回结果
                total_time = time.time() - total_start
                logger.info(f"[{context.request_id}] 任务类型: {main_result.get('task_type')}，直接返回结果")
                logger.info(f"[{context.request_id}] [新架构] 完成 ✅ (总耗时: {total_time:.2f}s)")
                
                return {
                    "final_report": main_result.get("result", "任务完成"),
                    "task_type": main_result.get("task_type"),
                    "mode": "direct",
                    "request_id": context.request_id,
                    "total_time": total_time,
                }
            
            # 需要并行，继续执行后续步骤
            task_spec = main_result.get("task_spec")
            task_type = main_result.get("task_type")
            logger.info(f"[{context.request_id}] 任务类型: {task_type}，需要并行处理")
            
            # Step 2: TaskPlanner - 任务规划
            logger.info(f"[{context.request_id}] Step 2/4: 任务规划 📋")
            step_start = time.time()
            execution_plan = await self.task_planner.plan(task_spec)
            logger.info(f"[{context.request_id}] ✓ 任务规划完成 (耗时: {time.time()-step_start:.2f}s)")
            logger.info(f"[{context.request_id}] 执行策略: {execution_plan.get('execution_strategy')} ({execution_plan.get('execution_mode')})")
            
            # Step 3: Executor/Processor - 执行
            logger.info(f"[{context.request_id}] Step 3/4: 任务执行 ⚡")
            step_start = time.time()
            
            strategy = execution_plan.get("execution_strategy", "serial")
            
            if strategy == "parallel":
                # 并行执行
                execution_result = await self.processor.execute(execution_plan, context)
            else:
                # 串行执行
                execution_result = await self.executor.execute(execution_plan, context)
            
            logger.info(f"[{context.request_id}] ✓ 任务执行完成 (耗时: {time.time()-step_start:.2f}s)")
            
            # Step 4: Integrator - 整合结果
            logger.info(f"[{context.request_id}] Step 4/4: 结果整合 📝")
            step_start = time.time()
            integration_result = await self.integrator.integrate(execution_result, execution_plan, context)
            logger.info(f"[{context.request_id}] ✓ 结果整合完成 (耗时: {time.time()-step_start:.2f}s)")
            
            total_time = time.time() - total_start
            logger.info(f"[{context.request_id}] [新架构] 全部完成 ✅ (总耗时: {total_time:.2f}s)")
            
            return {
                "final_report": integration_result.get("final_report", "任务完成"),
                "task_spec": task_spec,
                "execution_plan": execution_plan,
                "execution_result": execution_result,
                "integration_result": integration_result,
                "task_type": task_type,
                "mode": "parallel",
                "request_id": context.request_id,
                "total_time": total_time,
            }
            
        except Exception as e:
            logger.error(f"[{context.request_id}] 执行出错: {e}")
            return {
                "final_report": f"执行出错: {str(e)}",
                "error": str(e),
                "request_id": context.request_id,
            }

# 类型提示
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scidatabot.tools.registry import ToolRegistry
    from scidatabot.providers.base import LLMProvider
