"""测试 MAT 文件并行解析"""
import asyncio
import json
import os
from pathlib import Path
from scipy.io import loadmat
import numpy as np
from concurrent.futures import ProcessPoolExecutor, as_completed

def _extract_tensor_info_from_mat(file_path: str) -> dict:
    """从单个 .mat 文件中提取张量信息"""
    try:
        result = {
            "file": os.path.basename(file_path),
            "file_path": file_path,
            "file_size_bytes": os.path.getsize(file_path),
            "tensors": [],
            "error": None
        }
        
        data = loadmat(file_path, squeeze_me=True, struct_as_record=False)
        
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
                tensor_info["size_bytes"] = value.nbytes
                
                if value.ndim == 0:
                    tensor_info["dimensions"] = "scalar"
                elif value.ndim == 1:
                    tensor_info["dimensions"] = "1D"
                elif value.ndim == 2:
                    tensor_info["dimensions"] = "2D"
                elif value.ndim == 3:
                    tensor_info["dimensions"] = "3D"
                elif value.ndim == 4:
                    tensor_info["dimensions"] = "4D"
                else:
                    tensor_info["dimensions"] = f"{value.ndim}D"
                    
                if value.ndim > 0:
                    tensor_info["total_elements"] = int(value.size)
                    
            elif isinstance(value, (np.integer, np.floating)):
                tensor_info["dimensions"] = "scalar"
            elif isinstance(value, str):
                tensor_info["dimensions"] = "string"
            elif isinstance(value, dict):
                tensor_info["dimensions"] = "dict"
                tensor_info["keys"] = list(value.keys())[:20]
            else:
                tensor_info["dimensions"] = "unknown"
                
            result["tensors"].append(tensor_info)
            
        result["tensor_count"] = len(result["tensors"])
        return result
        
    except Exception as e:
        return {
            "file": os.path.basename(file_path),
            "file_path": file_path,
            "error": str(e),
            "tensors": [],
            "tensor_count": 0
        }

async def main():
    directory = "/Users/zc-home/Downloads/Ahrens_2018_Neuron/Additional_mat_files/Additional_mat_files"
    dir_path = Path(directory)
    
    mat_files = list(dir_path.glob("*.mat"))
    print(f"找到 {len(mat_files)} 个 .mat 文件")
    
    cpu_count = os.cpu_count() or 4
    agents_count = min(cpu_count, 8)
    print(f"使用 {agents_count} 个 Agent 并行处理")
    
    files_per_agent = (len(mat_files) + agents_count - 1) // agents_count
    print(f"每个 Agent 处理约 {files_per_agent} 个文件")
    
    # 模拟多智能体并行处理
    async def process_group(files, agent_idx):
        print(f"Agent {agent_idx} 开始处理 {len(files)} 个文件...")
        results = []
        for f in files:
            result = _extract_tensor_info_from_mat(str(f))
            results.append(result)
            print(f"  - {f.name}: {result.get('tensor_count', 0)} 个张量")
        return results
    
    # 创建并行任务
    tasks = []
    for i in range(agents_count):
        start_idx = i * files_per_agent
        end_idx = min(start_idx + files_per_agent, len(mat_files))
        files_group = mat_files[start_idx:end_idx]
        if files_group:
            tasks.append(process_group(files_group, i))
    
    # 并行执行
    all_results = await asyncio.gather(*tasks)
    
    # 合并结果
    final_results = []
    failed = 0
    for results in all_results:
        for r in results:
            final_results.append(r)
            if r.get("error"):
                failed += 1
    
    # 保存到JSON
    output_file = dir_path / "tensors_info_parallel.json"
    summary = {
        "directory": str(dir_path),
        "total_files": len(mat_files),
        "successful": len(final_results) - failed,
        "failed": failed,
        "agents_used": agents_count,
        "files": final_results
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    
    print(f"\n完成!")
    print(f"- 总文件数: {len(mat_files)}")
    print(f"- 成功: {len(final_results) - failed}")
    print(f"- 失败: {failed}")
    print(f"- 总张量数: {sum(r.get('tensor_count', 0) for r in final_results)}")
    print(f"- 结果保存到: {output_file}")

if __name__ == "__main__":
    asyncio.run(main())
