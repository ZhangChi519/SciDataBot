"""数据上下文 - 用于智能体间数据传递"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DataUnit:
    """数据单元 - 单一模态、时空、对象"""
    id: str
    name: str
    path: str
    format: str
    modality: str  # 数据模态: image, timeseries, tabular, text, etc.
    spatial_range: dict | None = None  # 空间范围
    temporal_range: dict | None = None  # 时间范围
    metadata: dict = field(default_factory=dict)
    quality_score: float = 0.0


@dataclass
class DataSource:
    """数据源"""
    id: str
    name: str
    type: str  # local, remote, database, api
    connection_config: dict = field(default_factory=dict)
    data_units: list[DataUnit] = field(default_factory=list)


@dataclass
class ProcessingPipeline:
    """处理管线"""
    id: str
    name: str
    steps: list[dict] = field(default_factory=list)  # [{"tool": "xxx", "params": {}}]
    input: str = ""
    output: str | None = None


@dataclass
class DataContext:
    """数据上下文 - 贯穿整个处理流程"""
    request_id: str
    data_sources: list[DataSource] = field(default_factory=list)
    processing_pipelines: list[ProcessingPipeline] = field(default_factory=list)
    intermediate_results: dict = field(default_factory=dict)
    final_dataset: Any = None

    def add_data_source(self, source: DataSource):
        self.data_sources.append(source)

    def add_pipeline(self, pipeline: ProcessingPipeline):
        self.processing_pipelines.append(pipeline)

    def get_data_unit(self, unit_id: str) -> DataUnit | None:
        for source in self.data_sources:
            for unit in source.data_units:
                if unit.id == unit_id:
                    return unit
        return None
