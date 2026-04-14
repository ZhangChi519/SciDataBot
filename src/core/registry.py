"""组件注册表"""

from typing import Any


class ComponentRegistry:
    """组件注册表 - 单例"""

    _instance = None
    _components: dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, name: str, component: Any):
        """注册组件"""
        self._components[name] = component

    def get(self, name: str) -> Any:
        """获取组件"""
        return self._components.get(name)

    def list(self) -> list[str]:
        """列出所有组件"""
        return list(self._components.keys())

    def clear(self):
        """清空注册表"""
        self._components.clear()
