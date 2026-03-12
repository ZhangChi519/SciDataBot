# Tool Usage Notes

工具签名通过 function calling 自动提供。
本文件记录非显而易见的约束和使用模式。

## 工具列表

- **weather**: 天气查询 (city, operation)
- **web_search**: 网络搜索 (query)
- **web_fetch**: 网页抓取 (url)
- **detect_format**: 格式检测 (file_path)
- **extract_metadata**: 元数据提取 (file_path)
- **extract_data**: 数据提取 (file_path, keys)
- **transform_data**: 数据转换 (data, operations)
- **clean_data**: 数据清洗 (data, rules)
- **assess_quality**: 质量评估 (data)
- **export_data**: 数据导出 (input_data, output_path, format)
- **list_dir**: 列出目录 (path)
- **read_file**: 读取文件 (file_path)
- **write_file**: 写入文件 (file_path, content)
- **edit_file**: 编辑文件 (file_path, old_string, new_string)
- **exec**: 执行命令 (command)

## 使用说明

- 所有参数必须显式提供
- 文件路径使用绝对路径或相对于工作目录
- 执行危险命令会被阻止 (rm -rf, format, dd, shutdown 等)
