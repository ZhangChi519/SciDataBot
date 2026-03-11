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

        # 延迟创建 Agent 池 - 仅在实际需要时创建
        self._mat_agents = None
        self._provider = provider
        self._workspace = workspace
        self._tool_registry = tool_registry

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
        """执行用户请求"""

        # 检查是否包含"数据准备"标签
        if "数据准备" in user_request:
            # 使用 4 步骤处理流程
            return await self._execute_with_planning(user_request)
        else:
            # 使用 OpenClaw 风格：直接对话
            return await self._execute_simple(user_request)

    async def _execute_with_planning(self, user_request: str) -> dict:
        """使用 4 步骤处理流程 (数据准备模式) - 通过Lane调度"""
        import time
        total_start = time.time()
        
        context = ExecutionContext(
            request_id=str(uuid.uuid4())[:8],
            user_input=user_request,
        )

        logger.info(f"[{context.request_id}] [数据准备模式] 开始处理: {user_request}")
        
        # 初始化动态 Todo List
        todo = self.TodoList("执行计划")
        
        # 添加初始任务 - 解析用户请求
        todo.add(f"解析请求: {user_request[:50]}...")
        
        # Step 1: 意图分类 + 任务分解
        todo.pending(0)
        self._print_todo(todo)
        
        logger.info(f"[{context.request_id}] ═══════════════════════════════════════════")
        logger.info(f"[{context.request_id}] Step 1/3: 意图分析与任务分解 📊 [Lane: main]")
        step_start = time.time()
        
        # 通过LaneScheduler提交任务
        intent_result, task_graph = await self.lane_scheduler.submit_task(
            "main",
            self._classify_and_decompose,
            user_request
        )
        context.intent = intent_result
        context.task_graph = task_graph
        logger.info(f"[{context.request_id}] ✓ 意图分析与任务分解完成 (耗时: {time.time()-step_start:.2f}s)")
        
        # 更新 todo - 标记解析完成，添加具体任务
        todo.complete(0)
        
        # 添加具体执行任务 (从 task_graph 获取)
        task_indices = []
        for i, t in enumerate(task_graph):
            task_name = t.get('task', 'unknown')[:45]
            lane = t.get('lane', 'unknown')
            idx = todo.add(f"[{lane}] {task_name}")
            task_indices.append(idx)
        
        # 如果有具体目录信息，添加
        import re
        dir_match = re.search(r'([/\w]+)', user_request)
        if dir_match:
            dir_path = dir_match.group(1)
            if dir_path.startswith('/') or dir_path.startswith('~'):
                todo.add(f"📁 目标目录: {dir_path}")
        
        # 添加聚合任务
        agg_idx = todo.add("📊 生成最终报告")
        todo.complete(agg_idx)
        
        self._print_todo(todo)

        # Step 2: 执行调度 → subagent lane
        logger.info(f"[{context.request_id}] ═══════════════════════════════════════════")
        exec_strategy = intent_result.get("execution", {}).get("strategy", "sequential")
        logger.info(f"[{context.request_id}] Step 2/3: 执行调度 ⚡ [Lane: subagent, strategy={exec_strategy}]")
        step_start = time.time()
        
        # 标记任务为进行中
        for idx in task_indices:
            todo.pending(idx)
        self._print_todo(todo)
        
        results = await self.lane_scheduler.submit_task(
            "subagent",
            self._execute_tasks,
            task_graph,
            context,
            intent_result.get("execution", {})
        )
        logger.info(f"[{context.request_id}] ✓ 执行调度完成 (耗时: {time.time()-step_start:.2f}s)")
        
        # 检查执行结果
        failed_count = sum(1 for r in results if isinstance(r, dict) and not r.get('success', True))
        
        # 更新任务状态
        for idx in task_indices:
            todo.complete(idx)
        
        # 动态添加反思任务
        if failed_count > 0:
            todo.add(f"⚠ 分析 {failed_count} 个失败原因")
            logger.warning(f"[{context.request_id}] 任务执行有 {failed_count} 个失败")
            
            # 添加恢复任务
            error_analysis = self._analyze_failures(results)
            logger.info(f"[{context.request_id}] 失败原因: {error_analysis}")
            
            if "scipy" in error_analysis.lower() or "缺少依赖" in error_analysis:
                retry_idx = todo.add("🔧 尝试安装依赖并重试")
                self._print_todo(todo)
                
                logger.info(f"[{context.request_id}] 尝试安装缺失依赖后重试...")
                retry_result = await self._retry_with_fix(results, context)
                if retry_result:
                    results = retry_result
                    logger.info(f"[{context.request_id}] 重试成功!")
                    todo.complete(retry_idx)
                else:
                    todo.fail(retry_idx)
        
        self._print_todo(todo)

        # Step 3: 结果聚合 → main lane (根据 intent 决定格式)
        logger.info(f"[{context.request_id}] ═══════════════════════════════════════════")
        agg_format = intent_result.get("aggregation", {}).get("format", "markdown")
        logger.info(f"[{context.request_id}] Step 3/3: 结果聚合 📝 [Lane: main, format={agg_format}]")
        step_start = time.time()
        
        # 标记聚合为进行中
        todo.pending(agg_idx)
        self._print_todo(todo)
        
        final_result = await self.lane_scheduler.submit_task(
            "main",
            self._aggregate_results,
            results,
            context,
            intent_result.get("aggregation", {})  # 传递聚合适
        )
        
        todo.complete(agg_idx)
        logger.info(f"[{context.request_id}] ✓ 结果聚合完成 (耗时: {time.time()-step_start:.2f}s)")

        total_time = time.time() - total_start
        logger.info(f"[{context.request_id}] ═══════════════════════════════════════════")
        logger.info(f"[{context.request_id}] [数据准备模式] 全部完成 ✅ (总耗时: {total_time:.2f}s)")
        
        # 打印最终 Todo
        self._print_todo(todo)

        final_result["total_time"] = total_time
        
        return final_result

    async def _execute_simple(self, user_request: str) -> dict:
        """简单模式 - 直接对话，使用专用 Agent，支持对话历史"""
        import time
        total_start = time.time()
        
        context = ExecutionContext(
            request_id=str(uuid.uuid4())[:8],
            user_input=user_request,
        )

        logger.info(f"[{context.request_id}] [简单模式] 处理: {user_request}")
        
        # 简单模式 Todo List - 动态跟踪
        todo = self.TodoList("简单模式执行计划")
        
        # 解析请求，提取关键信息
        import re
        dir_match = re.search(r'([/\w]+(?:[/\w\.])*)', user_request)
        target_dir = dir_match.group(1) if dir_match else None
        
        # 初始 todo
        todo.add(f"🔍 分析请求: {user_request[:50]}...")
        if target_dir:
            todo.add(f"📁 目标: {target_dir}")
        
        todo.add("🤔 规划操作步骤")
        todo.add("⚙️ 执行操作")
        todo.add("📝 生成报告")
        
        todo.pending(2)  # 规划中
        self._print_todo(todo)

        # 跟踪步骤的索引
        step_indices = []
        
        # 使用 on_progress 回调来动态更新 todo
        def on_progress(content: str, is_tool_hint: bool):
            nonlocal step_indices
            if is_tool_hint:
                # 解析工具调用信息
                if "执行工具:" in content or "🔧" in content:
                    # 提取工具名和参数
                    match = re.search(r'🔧\s*执行工具:\s*(\w+)\((.*?)\)', content)
                    if match:
                        tool_name = match.group(1)
                        args = match.group(2)[:40]
                        
                        # 添加新步骤
                        icon = {"list_dir": "📂", "read_file": "📄", "write_file": "✏️", 
                               "exec": "⚡", "web_search": "🔎", "web_fetch": "🌐",
                               "edit_file": "✂️"}.get(tool_name, "🔧")
                        
                        idx = todo.add(f"{icon} {tool_name}: {args}")
                        step_indices.append(idx)
                        self._print_todo(todo)
                elif "→" in content and "完成" in content:
                    # 工具完成，标记最后一个步骤
                    if step_indices:
                        todo.complete(step_indices[-1])
                        self._print_todo(todo)
        
        todo.complete(2)  # 规划完成
        todo.pending(3)  # 执行中
        self._print_todo(todo)

        # 使用简单模式专用 Agent，传入对话历史和进度回调
        result = await self.simple_agent.execute(
            user_request, 
            context,
            history=self.simple_history,
            on_progress=on_progress,
        )

        # 更新对话历史
        self.simple_history.append({"role": "user", "content": user_request})
        self.simple_history.append({"role": "assistant", "content": result})

        # 限制历史长度，避免无限增长
        if len(self.simple_history) > 20:
            self.simple_history = self.simple_history[-20:]

        total_time = time.time() - total_start
        
        todo.complete(3)  # 执行完成
        todo.complete(4)  # 报告完成
        self._print_todo(todo)
        
        logger.info(f"[{context.request_id}] [简单模式] 完成 ✅ (耗时: {total_time:.2f}s)")

        return {
            "final_report": result,
            "mode": "simple",
            "request_id": context.request_id,
            "total_time": total_time,
        }

    async def _classify_and_decompose(self, user_request: str) -> tuple[dict, list]:
        """意图分类 + 任务分解 - 合并为一步"""
        result = await self.agents["planning"].execute(
            f"""分析用户需求，直接分解为可执行的任务。

需求: {user_request}

请同时完成意图分析和任务分解，输出包含以下内容的JSON：
{{
    "intent_type": "分析|处理|整合|检索|对比",
    "domain": "领域",
    "data_requirements": ["数据需求列表"],
    "tasks": [
        {{
            "task": "任务描述",
            "lane": "data_access|processing|integration",
            "parallel_type": "none|task"
        }}
    ],
    "execution": {{
        "strategy": "sequential|parallel|streaming",
        "on_error": "continue|abort|retry"
    }},
    "aggregation": {{
        "format": "table|json|csv|markdown",
        "include_errors": true|false,
        "summary_only": true|false,
        "use_tools": true|false,
        "allowed_tools": ["工具名列表，如需使用工具则必填"]
    }}
}}

只输出 JSON。"""
        )

        # 解析 JSON
        try:
            match = re.search(r'\{.*\}', result, re.DOTALL)
            if match:
                data = json.loads(match.group())
                intent = {
                    "type": data.get("intent_type", "unknown"),
                    "domain": data.get("domain", "general"),
                    "data_requirements": data.get("data_requirements", []),
                    "execution": data.get("execution", {}),
                    "aggregation": data.get("aggregation", {}),
                }
                tasks = data.get("tasks", [])
                return intent, tasks
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"解析失败: {result}, error: {e}")

        # 解析失败，返回空结果
        return {
            "type": "unknown",
            "domain": "general",
            "data_requirements": [],
        }, []

    async def _execute_tasks(self, task_graph: list, context: ExecutionContext, execution_config: dict = None) -> list:
        """执行任务图 - 支持通用并行化，根据 execution_config 决定工具范围"""
        import asyncio
        from collections import defaultdict
        
        if execution_config is None:
            execution_config = {}
        
        allowed_tools = execution_config.get("allowed_tools", [])
        
        # 如果指定了可用工具范围，限制工具集
        if allowed_tools:
            tool_registry = self.tool_registry.get_subset(allowed_tools)
            from src.core.agent import GeneralAgent
            executor_agent = GeneralAgent(
                "TaskExecutor",
                self.provider,
                self.workspace,
                tool_registry,
                system_prompt="你是一个任务执行助手，负责根据任务描述执行相应操作。使用可用的工具完成任务。"
            )
        else:
            # 使用默认工具集
            tool_registry = self.tool_registry
            from src.core.agent import GeneralAgent
            executor_agent = GeneralAgent(
                "TaskExecutor",
                self.provider,
                self.workspace,
                tool_registry,
                system_prompt="你是一个任务执行助手，负责根据任务描述执行相应操作。使用可用的工具完成任务。"
            )
        
        results = {}
        completed = set()
        
        # 检查用户输入是否包含文件解析需求
        user_input = context.user_input
        user_lower = user_input.lower()
        
        # 提取目录路径
        import re
        dir_match = re.search(r'(/[\w\u4e00-\u9fff_.-]+(?:/[\w-]+)*)', user_input)
        if not dir_match:
            # 使用通用任务执行
            return await self._execute_tasks_generic(task_graph, context, executor_agent)
        
        dir_path = dir_match.group(1).rstrip('/')
        dir_path = re.sub(r'[^\w/.-].*$', '', dir_path)
        
        from pathlib import Path
        if not Path(dir_path).exists():
            logger.warning(f"[Scheduler] 目录不存在: {dir_path}")
            return await self._execute_tasks_generic(task_graph, context, executor_agent)
        
        # ===== 通用数据处理框架 =====
        logger.info(f"[Scheduler] 开始通用数据处理: {dir_path}")
        
        # 1. 扫描目录获取所有文件
        all_files = []
        for f in Path(dir_path).rglob("*"):
            if f.is_file() and not f.name.startswith('.'):
                all_files.append(f)
        
        logger.info(f"[Scheduler] 扫描到 {len(all_files)} 个文件")
        
        # 2. 按文件格式分组
        format_groups = defaultdict(list)
        for f in all_files:
            ext = f.suffix.lower()
            format_groups[ext].append(f)
        
        logger.info(f"[Scheduler] 文件格式分布: {dict((k, len(v)) for k,v in format_groups.items())}")
        
        # 3. 根据格式选择处理方法并并行执行
        all_results = []
        
        # 并行处理不同格式的文件
        format_tasks = []
        for ext, files in format_groups.items():
            format_tasks.append(self._process_files_by_format(ext, files, context))
        
        if format_tasks:
            format_results = await asyncio.gather(*format_tasks, return_exceptions=True)
            for r in format_results:
                if isinstance(r, Exception):
                    logger.error(f"[Scheduler] 格式处理异常: {r}")
                elif r:
                    all_results.append(r)
        
        if all_results:
            return all_results
        
        # 如果没有匹配的处理方法，使用通用任务执行
        return await self._execute_tasks_generic(task_graph, context, executor_agent)

    async def _process_files_by_format(self, ext: str, files: list, context: ExecutionContext) -> str:
        """根据文件格式处理文件"""
        logger.info(f"[Scheduler] 处理 {len(files)} 个 {ext} 文件")
        
        # 格式处理器映射
        handlers = {
            '.mat': self._process_mat_files,
            '.json': self._process_json_files,
            '.csv': self._process_csv_files,
            '.nii': self._process_nifti_files,
            '.nii.gz': self._process_nifti_files,
            '.tif': self._process_image_files,
            '.tiff': self._process_image_files,
            '.png': self._process_image_files,
            '.jpg': self._process_image_files,
            '.pdf': self._process_pdf_files,
        }
        
        handler = handlers.get(ext)
        if handler:
            return await handler(files, context)
        else:
            # 未知格式，使用通用处理器
            return await self._process_generic_files(files, context)

    async def _process_mat_files(self, files: list, context: ExecutionContext) -> str:
        """处理MATLAB文件"""
        dir_path = str(files[0].parent.parent) if len(files) > 1 else str(files[0].parent)
        return await self._execute_mat_parallel(dir_path, context)

    async def _process_json_files(self, files: list, context: ExecutionContext) -> str:
        """处理JSON文件"""
        import json
        results = []
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    data = json.load(fp)
                results.append({
                    "file": f.name,
                    "type": "json",
                    "keys": list(data.keys()) if isinstance(data, dict) else type(data).__name__,
                    "size": f.stat().st_size
                })
            except Exception as e:
                results.append({"file": f.name, "error": str(e)})
        
        return f"JSON文件处理完成: {len(results)} 个文件"

    async def _process_csv_files(self, files: list, context: ExecutionContext) -> str:
        """处理CSV文件"""
        results = []
        for f in files:
            try:
                import csv
                with open(f, 'r', encoding='utf-8') as fp:
                    reader = csv.reader(fp)
                    rows = list(reader)
                results.append({
                    "file": f.name,
                    "type": "csv",
                    "rows": len(rows),
                    "cols": len(rows[0]) if rows else 0
                })
            except Exception as e:
                results.append({"file": f.name, "error": str(e)})
        
        return f"CSV文件处理完成: {len(results)} 个文件"

    async def _process_nifti_files(self, files: list, context: ExecutionContext) -> str:
        """处理NIfTI文件"""
        return f"NIfTI文件: {len(files)} 个 (需要nibabel库支持)"

    async def _process_image_files(self, files: list, context: ExecutionContext) -> str:
        """处理图像文件"""
        results = []
        for f in files:
            results.append({
                "file": f.name,
                "type": "image",
                "size": f.stat().st_size
            })
        return f"图像文件处理完成: {len(results)} 个文件"

    async def _process_pdf_files(self, files: list, context: ExecutionContext) -> str:
        """处理PDF文件"""
        results = []
        for f in files:
            results.append({
                "file": f.name,
                "type": "pdf",
                "size": f.stat().st_size,
                "pages": "未知"
            })
        return f"PDF文件处理完成: {len(results)} 个文件"

    async def _process_generic_files(self, files: list, context: ExecutionContext) -> str:
        """通用文件处理"""
        results = []
        for f in files:
            results.append({
                "file": f.name,
                "ext": f.suffix,
                "size": f.stat().st_size
            })
        
        # 保存到JSON
        import json
        output_file = Path(files[0].parent.parent) / "file_analysis.json"
        with open(output_file, 'w', encoding='utf-8') as fp:
            json.dump(results, fp, indent=2, ensure_ascii=False)
        
        return f"通用文件处理完成: {len(results)} 个文件，结果保存到 {output_file}"

    async def _execute_tasks_generic(self, task_graph: list, context: ExecutionContext, executor_agent=None) -> list:
        """通用任务执行"""
        from collections import defaultdict
        
        results = {}
        completed = set()
        
        # 1. 按 parallel_group 分组
        parallel_groups = defaultdict(list)
        serial_tasks = []
        
        for i, task in enumerate(task_graph):
            task_id = task.get("task", f"task_{i}")
            parallel_type = task.get("parallel_type", "none")
            parallel_group = task.get("parallel_group")
            
            if parallel_type != "none" and parallel_group:
                parallel_groups[parallel_group].append(task)
                logger.info(f"[Scheduler] 并行组 '{parallel_group}': {task_id} (type={parallel_type})")
            else:
                serial_tasks.append(task)
                logger.info(f"[Scheduler] 串行任务: {task_id}")
        
        # 2. 按依赖关系排序并行组
        # 先执行没有依赖的并行组，然后逐步执行
        executed_groups = set()
        
        # 3. 执行没有依赖的并行任务组
        while len(completed) < len(task_graph):
            # 找可执行的串行任务
            for task in serial_tasks:
                task_id = task.get("task", "")
                if task_id in completed:
                    continue
                
                deps = task.get("depends_on", [])
                # 检查依赖是否都已完成
                dep_tasks = [t.get("task", "") for t in task_graph]
                if all(d in completed for d in deps if d in dep_tasks):
                    logger.info(f"[Scheduler] 执行串行任务: {task_id}")
                    result = await self._execute_single_task(task, context)
                    completed.add(task_id)
                    results[task_id] = result
            
            # 找可执行的并行任务组
            for group_name, group_tasks in parallel_groups.items():
                if group_name in executed_groups:
                    continue
                
                # 检查组内所有任务的依赖
                can_execute = True
                for task in group_tasks:
                    task_id = task.get("task", "")
                    deps = task.get("depends_on", [])
                    dep_tasks = [t.get("task", "") for t in task_graph]
                    if not all(d in completed for d in deps if d in dep_tasks):
                        can_execute = False
                        break
                
                if can_execute and group_tasks:
                    # 执行整个并行组
                    logger.info(f"[Scheduler] ⚡ 并行执行组 '{group_name}' ({len(group_tasks)} 个任务)")
                    group_results = await self._execute_parallel_group(group_tasks, context)
                    
                    for task, result in zip(group_tasks, group_results):
                        task_id = task.get("task", "")
                        completed.add(task_id)
                        results[task_id] = result
                        executed_groups.add(group_name)
        
        return list(results.values())

    async def _execute_parallel_group(self, tasks: list, context: ExecutionContext) -> list:
        """并行执行一组任务"""
        import asyncio
        
        logger.info(f"[Scheduler] 创建 {len(tasks)} 个并行任务")
        
        # 根据资源类型决定并发数
        resource_type = tasks[0].get("resource_hint", "cpu") if tasks else "cpu"
        
        if resource_type == "io":
            # IO密集型任务可以高并发
            max_concurrent = min(len(tasks), 8)
        elif resource_type == "cpu":
            # CPU密集型任务受CPU核心数限制
            max_concurrent = min(len(tasks), os.cpu_count() or 4)
        else:
            max_concurrent = min(len(tasks), 4)
        
        logger.info(f"[Scheduler] 并发数: {max_concurrent} (resource={resource_type})")
        
        # 使用信号量控制并发
        semaphore = asyncio.Semaphore(max_concurrent)
        
        async def bounded_execute(task):
            async with semaphore:
                return await self._execute_single_task(task, context)
        
        # 并行执行所有任务
        task_results = await asyncio.gather(
            *[bounded_execute(task) for task in tasks],
            return_exceptions=True
        )
        
        # 处理异常结果
        results = []
        for i, result in enumerate(task_results):
            if isinstance(result, Exception):
                logger.error(f"[Scheduler] 任务 {i} 执行异常: {result}")
                results.append(f"执行失败: {str(result)}")
            else:
                results.append(result)
        
        return results

    async def _execute_single_task(self, task: dict, context: ExecutionContext) -> str:
        """执行单个任务"""
        task_text = task.get("task", "")
        task_type = task.get("lane", "processing")

        task_lower = task_text.lower()
        user_lower = context.user_input.lower()
        
        # 检测 .mat 文件解析任务 - 使用多智能体并行处理
        # 也检测"解析"、"数据准备"等关键词
        mat_keywords = [".mat", "mat 文件", "matfile", "解析"]
        is_mat_task = any(k in task_lower or k in user_lower for k in mat_keywords)
        
        if is_mat_task:
            from src.tools.data_processing import MatFileExtractor
            import re
            
            # 尝试从任务中提取目录路径
            dir_match = re.search(r'([/~\w\u4e00-\u9fff_.-]+(?:Additional_mat_files)?/?)', task_text)
            if dir_match:
                dir_path = dir_match.group(1).rstrip('/')
            else:
                # 从用户输入中提取
                dir_match = re.search(r'([/~\w\u4e00-\u9fff_.-]+(?:Additional_mat_files)?/?)', context.user_input)
                dir_path = dir_match.group(1) if dir_match else None
            from src.tools.data_processing import MatFileExtractor
            import re
            
            # 尝试从任务中提取目录路径
            dir_match = re.search(r'[/~\w\u4e00-\u9fff_-]+\.(?:mat|MAT)(?:/|$|/[\w-]+\.mat)?', task_text)
            if dir_match:
                dir_path = dir_match.group().rstrip('/')
                if not dir_path.endswith('.mat'):
                    dir_path = Path(dir_path).parent
            else:
                # 尝试从用户输入中提取
                dir_match = re.search(r'([/~\w\u4e00-\u9fff_.-]+)', context.user_input)
                dir_path = dir_match.group(1) if dir_match else None
            
            if dir_path:
                dir_str = str(dir_path)
                if Path(dir_str).exists():
                    logger.info(f"[Scheduler] 检测到 .mat 文件解析，使用多智能体并行处理: {dir_str}")
                    try:
                        # 使用多智能体并行处理
                        result = await self._execute_mat_parallel(dir_str, context)
                        return result
                    except Exception as e:
                        logger.error(f"多智能体并行处理失败: {e}")
                        # 回退到直接处理
                        mat_extractor = MatFileExtractor()
                        result = await mat_extractor.execute(directory=dir_str)
                        if result.success:
                            data = result.data
                            return f"成功解析 {data['total_files']} 个 .mat 文件\n" \
                                   f"- 成功: {data['successful']}\n" \
                                   f"- 失败: {data['failed']}\n" \
                                   f"- 总张量数: {data['total_tensors']}\n" \
                                   f"结果已保存到: {data['output_file']}"
                        else:
                            return f"解析失败: {result.error}"
                else:
                    return f"目录不存在: {dir_str}"
            else:
                return f"未找到有效目录"

        # 检测天气相关任务并直接执行
        task_lower = task_text.lower()
        if any(k in task_lower for k in ["天气", "weather", "温度", "temperature", "降水", "precipitation", "温差"]):
            weather_tool = self.tool_registry.get("weather")
            if weather_tool:
                # 尝试从任务中提取城市
                import re
                # 使用 | 匹配完整城市名称
                chinese_cities = '北京|上海|广州|深圳|杭州|成都|武汉|西安|南京|重庆|天津|苏州|长沙|郑州|济南|青岛|沈阳|大连|哈尔滨|长春|昆明|贵阳|南昌|合肥|南宁|福州|拉萨|乌鲁木齐|东莞|佛山'
                cities = re.findall(chinese_cities, task_text)
                cities += re.findall(r'Beijing|Shanghai|Guangzhou|Shenzhen|Hangzhou|Chengdu|Wuhan|Xian|Nanjing|Chongqing', task_text, re.IGNORECASE)
                
                # 也从原始用户查询中提取城市
                if context:
                    cities += re.findall(chinese_cities, context.user_input)
                    cities += re.findall(r'Beijing|Shanghai|Guangzhou|Shenzhen|Hangzhou|Chengdu|Wuhan|Xian|Nanjing|Chongqing', context.user_input, re.IGNORECASE)
                
                # 去重
                cities = list(dict.fromkeys(cities))

                if cities:
                    # 判断是否需要查询温差（使用原始用户查询判断）
                    user_query = context.user_input if context else task_text
                    need_forecast = len(cities) > 1 or "温差" in user_query
                    operation = "forecast" if need_forecast else "current"
                    
                    if len(cities) == 1:
                        # 单城市查询
                        city = cities[0]
                        logger.info(f"[Scheduler] 检测到天气查询，执行 weather 工具: {city} (operation={operation})")
                        try:
                            result = await weather_tool.execute(operation=operation, city=city)
                            if result.success:
                                data = result.data
                                if operation == "forecast" and "forecast" in data:
                                    # 预报数据
                                    fc = data["forecast"][0]
                                    return f"城市: {data.get('location')}, 国家: {data.get('country')}, " \
                                           f"今天: {fc.get('temperature_c_min')}°C ~ {fc.get('temperature_c_max')}°C, " \
                                           f"天气: {fc.get('weather')}, 湿度: {fc.get('humidity')}%, " \
                                           f"日出: {fc.get('sunrise')}, 日落: {fc.get('sunset')}"
                                else:
                                    # 当前天气
                                    return f"城市: {data.get('location')}, 国家: {data.get('country')}, " \
                                           f"温度: {data.get('temperature_c')}°C, 天气: {data.get('weather')}, " \
                                           f"湿度: {data.get('humidity')}%, 风速: {data.get('wind_speed_kph')}km/h, " \
                                           f"体感温度: {data.get('feels_like_c')}°C"
                            else:
                                return f"天气查询失败: {result.error}"
                        except Exception as e:
                            return f"天气查询错误: {str(e)}"
                    else:
                        # 多城市查询 - 查询所有城市
                        all_results = []
                        for city in cities:
                            try:
                                result = await weather_tool.execute(operation="forecast", city=city)
                                if result.success:
                                    data = result.data
                                    if "forecast" in data and len(data["forecast"]) > 0:
                                        fc = data["forecast"][0]
                                        all_results.append({
                                            "city": data.get("location"),
                                            "country": data.get("country"),
                                            "temp_max": fc.get("temperature_c_max", 0),
                                            "temp_min": fc.get("temperature_c_min", 0),
                                            "temp_current": fc.get("temperature_c", 0),
                                            "weather": fc.get("weather"),
                                            "humidity": fc.get("humidity"),
                                        })
                            except Exception as e:
                                logger.warning(f"查询{city}天气失败: {e}")
                        
                        if not all_results:
                            return "所有城市天气查询失败"
                        
                        # 计算温差
                        if len(all_results) >= 2:
                            # 按今天最高温-最低温计算日内温差，或城市间温差
                            if "温差" in task_text:
                                # 计算城市间最高温度差
                                temps = [r["temp_max"] if r["temp_max"] else r["temp_current"] for r in all_results]
                                max_temp = max(temps)
                                min_temp = min(temps)
                                max_diff = max_temp - min_temp
                                
                                result_text = "城市天气预报：\n"
                                for r in all_results:
                                    result_text += f"- {r['city']}: {r['temp_min']}°C ~ {r['temp_max']}°C ({r['weather']})\n"
                                result_text += f"\n城市间最大温差: {max_diff}°C"
                                return result_text
                        
                        # 默认返回所有城市信息
                        result_text = "城市天气预报：\n"
                        for r in all_results:
                            result_text += f"- {r['city']}: {r['temp_min']}°C ~ {r['temp_max']}°C ({r['weather']})\n"
                        return result_text

        # 检测PM2.5/空气质量相关任务
        if any(k in task_lower for k in ["pm2.5", "pm25", "空气质量", "air quality", "污染", "pollution"]):
            # 可以扩展为调用空气质量API
            logger.info(f"[Scheduler] 检测到空气质量查询")

        # 默认使用 agent 执行
        agent = self.agents.get(task_type, self.agents["processor"])
        return await agent.execute(task_text, context)

    async def _execute_mat_parallel(self, directory: str, context: ExecutionContext) -> str:
        """使用多智能体并行处理 MAT 文件"""
        import asyncio
        from pathlib import Path
        
        dir_path = Path(directory)
        # 递归查找所有.mat文件
        mat_files = list(dir_path.rglob("*.mat"))
        
        if not mat_files:
            return f"目录中没有找到 .mat 文件: {directory}"
        
        logger.info(f"[数据准备模式] 递归找到 {len(mat_files)} 个 .mat 文件")
        for f in mat_files:
            logger.info(f"  - {f.relative_to(dir_path)}")
        
        # 将文件分配给多个智能体
        files_per_agent = (len(mat_files) + len(self.mat_agents) - 1) // len(self.mat_agents)
        
        logger.info(f"[数据准备模式] 使用 {len(self.mat_agents)} 个智能体并行处理 {len(mat_files)} 个文件")
        
        async def process_file_group(agent, files: list, agent_idx: int) -> dict:
            """单个智能体处理一组文件 - 返回结果而不是保存到文件"""
            logger.info(f"Agent {agent_idx} 开始处理 {len(files)} 个文件...")
            results = []
            
            # 检查 scipy 是否可用，不可用则尝试安装
            scipy_available = True
            try:
                from scipy.io import loadmat
            except ImportError:
                logger.warning(f"Agent {agent_idx}: scipy 未安装，尝试安装...")
                try:
                    import subprocess
                    subprocess.run(["pip", "install", "scipy", "-q"], check=True)
                    from scipy.io import loadmat
                    logger.info(f"Agent {agent_idx}: scipy 安装成功")
                except Exception as install_err:
                    scipy_available = False
                    logger.error(f"Agent {agent_idx}: scipy 安装失败: {install_err}")
            
            if not scipy_available:
                for f in files:
                    results.append({
                        "file": f.name,
                        "file_path": str(f),
                        "error": "缺少 scipy 库且自动安装失败，请手动运行: pip install scipy",
                        "tensors": [],
                        "tensor_count": 0,
                        "success": False
                    })
                return {"agent": agent.name, "results": results}
            
            for f in files:
                try:
                    # 直接解析文件，返回tensor信息
                    import numpy as np
                    
                    data = loadmat(str(f), squeeze_me=True, struct_as_record=False)
                    tensors = []
                    for key, value in data.items():
                        if key.startswith('__'):
                            continue
                        tensor_info = {
                            "name": key,
                            "type": type(value).__name__,
                        }
                        if isinstance(value, np.ndarray):
                            tensor_info["shape"] = list(value.shape)
                            tensor_info["dtype"] = str(value.dtype)
                            tensor_info["dimensions"] = f"{value.ndim}D"
                            tensor_info["total_elements"] = int(value.size)
                            tensor_info["size_bytes"] = value.nbytes
                        tensors.append(tensor_info)
                    
                    results.append({
                        "file": f.name,
                        "file_path": str(f),
                        "file_size_bytes": f.stat().st_size,
                        "tensors": tensors,
                        "tensor_count": len(tensors),
                        "error": None,
                        "success": True
                    })
                except Exception as e:
                    results.append({
                        "file": f.name,
                        "file_path": str(f),
                        "error": str(e),
                        "tensors": [],
                        "tensor_count": 0,
                        "success": False
                    })
            return {
                "agent": agent.name,
                "results": results
            }
        
        # 创建并行任务
        tasks = []
        for i, agent in enumerate(self.mat_agents):
            start_idx = i * files_per_agent
            end_idx = min(start_idx + files_per_agent, len(mat_files))
            files_group = mat_files[start_idx:end_idx]
            
            if files_group:
                tasks.append(process_file_group(agent, files_group, i))
        
        # 并行执行所有智能体任务，添加整体超时
        try:
            all_results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=300.0
            )
        except asyncio.TimeoutError:
            logger.error("多智能体并行处理超时")
            return "处理超时，请重试"
        
        # 收集结果并合并
        all_file_results = []
        successful = 0
        failed = 0
        total_tensors = 0
        
        for result in all_results:
            if isinstance(result, Exception):
                logger.error(f"Agent 执行异常: {result}")
                continue
            
            if not isinstance(result, dict):
                continue
            
            for r in result.get("results", []):
                all_file_results.append(r)
                if isinstance(r, dict) and r.get("success"):
                    successful += 1
                    total_tensors += r.get("tensor_count", 0)
                else:
                    failed += 1
        
        # 合并所有结果到一个JSON文件
        output_file = str(dir_path / "tensors_info.json")
        summary = {
            "directory": str(dir_path),
            "total_files": len(mat_files),
            "successful": successful,
            "failed": failed,
            "failed_files": [r["file"] for r in all_file_results if not r.get("success", False)],
            "agents_used": len([t for t in tasks]),
            "files": all_file_results
        }
        
        import json
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        return f"[数据准备模式] 多智能体并行处理完成\n" \
               f"- 智能体数量: {len(self.mat_agents)}\n" \
               f"- 总文件数: {len(mat_files)}\n" \
               f"- 成功: {successful}\n" \
               f"- 失败: {failed}\n" \
               f"- 总张量数: {total_tensors}\n" \
                f"- 结果保存到: {output_file}"

    def _analyze_failures(self, results: list) -> str:
        """分析任务失败原因"""
        error_messages = []
        for r in results:
            if isinstance(r, dict):
                # 检查是否有错误信息
                if not r.get('success', True):
                    error = r.get('error', '未知错误')
                    error_messages.append(error)
                # 检查嵌套结果
                if 'results' in r:
                    for sub_r in r.get('results', []):
                        if isinstance(sub_r, dict) and not sub_r.get('success', True):
                            error = sub_r.get('error', '未知错误')
                            error_messages.append(error)
        
        if not error_messages:
            return "未知错误"
        
        # 合并相似错误
        unique_errors = list(set(error_messages))
        return "; ".join(unique_errors[:3])  # 返回前3个唯一错误
    
    async def _retry_with_fix(self, results: list, context: ExecutionContext) -> list:
        """尝试修复错误并重试"""
        import subprocess
        
        # 尝试安装 scipy
        try:
            logger.info("尝试安装 scipy...")
            subprocess.run(["pip", "install", "scipy", "-q"], check=True, capture_output=True)
            
            # 检查任务类型，如果是 MAT 文件处理，重新执行
            # 这里简化为返回 None，表示无法自动恢复
            logger.info("scipy 安装成功，但需要重新执行任务")
            return None  # 让用户知道需要重试
        except Exception as e:
            logger.error(f"安装依赖失败: {e}")
            return None

    async def _aggregate_results(self, results: list, context: ExecutionContext, aggregation_config: dict = None) -> dict:
        """结果聚合 - 根据 aggregation_config 格式化结果，可选择使用工具"""
        
        if aggregation_config is None:
            aggregation_config = {}
        
        format_type = aggregation_config.get("format", "markdown")
        include_errors = aggregation_config.get("include_errors", True)
        summary_only = aggregation_config.get("summary_only", False)
        use_tools = aggregation_config.get("use_tools", False)
        allowed_tools = aggregation_config.get("allowed_tools", [])
        
        # 如果需要使用工具，先获取受限的工具集
        if use_tools and allowed_tools:
            from src.tools.registry import ToolRegistry
            # 获取可用工具的子集
            tool_registry = self.tool_registry.get_subset(allowed_tools)
            # 创建专用聚合 Agent
            from src.core.agent import GeneralAgent
            agg_agent = GeneralAgent(
                "Aggregator",
                self.provider,
                self.workspace,
                tool_registry,
                system_prompt="你是一个数据分析助手，负责将任务执行结果聚合成最终报告。使用给定的工具完成任务。"
            )
            
            # 使用 Agent 聚合结果
            agg_result = await agg_agent.execute(
                f"""请聚合以下任务结果，生成最终报告：

用户请求: {context.user_input}
意图: {json.dumps(context.intent, ensure_ascii=False)}
任务结果: {json.dumps(results, ensure_ascii=False, indent=2)}

请生成最终报告。"""
            )
            
            return {
                "request_id": context.request_id,
                "intent": context.intent,
                "task_graph": context.task_graph,
                "results": results,
                "final_report": agg_result,
            }
        
        # 默认：直接格式化结果（不使用工具）
        
        report_lines = []
        
        if format_type == "markdown" or format_type == "md":
            report_lines = ["## 最终报告\n"]
            
            # 任务概述
            report_lines.append("### 任务完成情况\n")
            report_lines.append(f"- **用户请求**: {context.user_input}\n")
            if context.intent:
                report_lines.append(f"- **意图类型**: {context.intent.get('type', '未知')}\n")
            report_lines.append(f"- **执行任务数**: {len(results)}\n")
            
            if not summary_only:
                report_lines.append("\n### 执行结果摘要\n")
                for i, result in enumerate(results, 1):
                    if isinstance(result, dict):
                        report_lines.append(f"**任务 {i}**: {result.get('task_name', '未命名')}\n")
                        status = "✅ 成功" if result.get('success') else "❌ 失败"
                        report_lines.append(f"- 状态: {status}\n")
                        if result.get('data'):
                            data_preview = str(result.get('data'))[:200]
                            report_lines.append(f"- 数据预览: {data_preview}...\n")
                        if include_errors and result.get('error'):
                            report_lines.append(f"- 错误: {result.get('error')}\n")
                    else:
                        report_lines.append(f"**任务 {i}**: {str(result)[:100]}...\n")
            
            # 文件信息
            import os
            try:
                workspace_files = []
                for f in os.listdir('workspace/'):
                    fpath = os.path.join('workspace/', f)
                    size = os.path.getsize(fpath)
                    workspace_files.append(f"- `{f}` ({size} bytes)")
                
                if workspace_files:
                    report_lines.append("\n### 生成的文件\n")
                    report_lines.append("\n".join(workspace_files))
            except Exception:
                pass
            
            final_report = "".join(report_lines)
            
        elif format_type == "json":
            final_report = json.dumps({
                "user_request": context.user_input,
                "intent": context.intent,
                "results": results,
            }, ensure_ascii=False, indent=2)
            
        elif format_type == "csv":
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["任务", "状态", "数据", "错误"])
            for i, result in enumerate(results, 1):
                if isinstance(result, dict):
                    writer.writerow([
                        result.get('task_name', f'任务{i}'),
                        "成功" if result.get('success') else "失败",
                        str(result.get('data', ''))[:100],
                        result.get('error', '') if include_errors else ''
                    ])
            final_report = output.getvalue()
            
        else:
            # 默认 markdown
            report_lines = [f"任务完成，共 {len(results)} 个任务"]
            final_report = "\n".join(report_lines)
        
        return {
            "request_id": context.request_id,
            "intent": context.intent,
            "task_graph": context.task_graph,
            "results": results,
            "final_report": final_report,
        }


# 类型提示
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scidatabot.tools.registry import ToolRegistry
    from scidatabot.providers.base import LLMProvider
