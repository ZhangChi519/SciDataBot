"""整合器 - 整合并行执行结果、格式化输出、生成最终报告"""

import json
import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class Integrator:
    """整合器 - 统一替代 Aggregator"""
    
    def __init__(self, agent, tool_registry):
        self.agent = agent
        self.tool_registry = tool_registry
    
    async def integrate(self, execution_result: dict, execution_plan: dict, context: Any) -> dict:
        """整合结果
        
        职责:
        1. 收集各并行任务的结果
        2. 整合数据 (时空对齐、数据合并)
        3. 格式化输出 (JSON/CSV/Markdown)
        4. 保存文件
        5. 生成最终报告
        
        Returns:
            整合后的结果
        """
        logger.info(f"[Integrator] 开始整合结果...")
        
        results = execution_result.get("results", [])
        result_handling = execution_plan.get("result_handling", {})
        
        mode = result_handling.get("mode", "context")
        save_format = result_handling.get("save_format", "markdown")
        result_path = result_handling.get("result_path", "")
        
        # Step 1: 收集结果
        integrated_data = self._collect_results(results)
        
        # Step 2: 格式化输出
        formatted_output = self._format_output(integrated_data, save_format)
        
        # Step 3: 保存文件
        if mode == "file" or save_format in ("markdown", "json", "csv"):
            saved_path = await self._save_file(formatted_output, save_format, result_path, context)
            logger.info(f"[Integrator] 结果已保存到: {saved_path}")
        
        # Step 4: 生成最终报告
        final_report = await self._generate_report(execution_result, integrated_data, context)
        
        logger.info(f"[Integrator] 整合完成")
        
        return {
            "final_report": final_report,
            "integrated_data": integrated_data,
            "saved_path": saved_path if mode == "file" else None,
            "format": save_format
        }
    
    def _collect_results(self, results: list) -> dict:
        """收集各任务结果"""
        
        collected = {
            "total_tasks": len(results),
            "successful": 0,
            "failed": 0,
            "data": []
        }
        
        for result in results:
            if result.get("success", False):
                collected["successful"] += 1
            else:
                collected["failed"] += 1
            
            collected["data"].append({
                "task_id": result.get("task_id"),
                "description": result.get("description", ""),
                "result": result.get("result", ""),
                "success": result.get("success", False)
            })
        
        return collected
    
    def _format_output(self, data: dict, save_format: str) -> str:
        """格式化输出"""
        
        if save_format == "json":
            return json.dumps(data, ensure_ascii=False, indent=2)
        
        elif save_format == "csv":
            lines = ["task_id,description,success"]
            for item in data.get("data", []):
                lines.append(f'{item.get("task_id")},"{item.get("description", "")}",{item.get("success")}')
            return "\n".join(lines)
        
        elif save_format == "markdown":
            lines = ["## 执行结果\n"]
            lines.append(f"- 总任务数: {data.get('total_tasks')}")
            lines.append(f"- 成功: {data.get('successful')}")
            lines.append(f"- 失败: {data.get('failed')}\n")
            lines.append("### 任务详情\n")
            lines.append("| 任务ID | 描述 | 状态 |\n")
            lines.append("|--------|------|------|\n")
            for item in data.get("data", []):
                status = "✅" if item.get("success") else "❌"
                lines.append(f"| {item.get('task_id')} | {item.get('description', '')[:30]} | {status} |\n")
            return "".join(lines)
        
        else:
            # 默认返回字符串
            return str(data)
    
    async def _save_file(self, content: str, save_format: str, result_path: str, context: Any) -> str:
        """保存文件"""
        from pathlib import Path
        
        if not result_path:
            result_path = "workspace/result"
        
        # 确定扩展名
        ext_map = {
            "json": ".json",
            "csv": ".csv",
            "markdown": ".md"
        }
        ext = ext_map.get(save_format, ".txt")
        
        # 构建文件路径
        file_path = Path(result_path).with_suffix(ext)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 保存
        file_path.write_text(content, encoding='utf-8')
        
        return str(file_path)
    
    async def _generate_report(self, execution_result: dict, data: dict, context: Any) -> str:
        """生成最终报告"""
        
        # 如果是 markdown 格式，生成更详细的报告
        report_lines = []
        
        mode = execution_result.get("mode", "unknown")
        
        if mode == "parallel":
            report_lines.append("## 并行执行完成\n")
        else:
            report_lines.append("## 串行执行完成\n")
        
        report_lines.append(f"- 总任务数: {data.get('total_tasks')}")
        report_lines.append(f"- 成功: {data.get('successful')}")
        report_lines.append(f"- 失败: {data.get('failed')}\n")
        
        # 添加数据摘要
        if data.get("data"):
            report_lines.append("### 执行摘要\n")
            for item in data.get("data")[:5]:  # 只显示前5个
                status = "✅" if item.get("success") else "❌"
                report_lines.append(f"- {status} {item.get('description', '')[:50]}")
        
        return "\n".join(report_lines)
