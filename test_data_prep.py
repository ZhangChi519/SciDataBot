#!/usr/bin/env python3
"""测试并行任务执行 - 数据准备模式"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    from src.main import create_app
    
    print("=" * 60)
    print("SciDataBot 数据准备模式测试")
    print("=" * 60)
    
    # 创建应用
    scheduler = create_app()
    
    # 测试请求 - 数据准备模式
    test_request = "数据准备 解析 /data/KITTI/dataset/sequences/00 下的所有数据,生成元数据文件"
    
    print(f"\n测试请求: {test_request}\n")
    
    # 执行
    result = asyncio.run(scheduler.execute(test_request))
    
    print("\n" + "=" * 60)
    print("执行结果:")
    print("=" * 60)
    print(f"Request ID: {result.get('request_id')}")
    print(f"总耗时: {result.get('total_time', 0):.2f}s")
    print(f"\nFinal Report:\n{result.get('final_report', '无结果')[:1000]}")

if __name__ == "__main__":
    main()
