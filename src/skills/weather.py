"""Weather skill for getting weather information."""
import asyncio
from typing import Any, Dict, Optional

from src.tools.base import Tool, ToolResult, ToolCategory


class WeatherSkill(Tool):
    """Skill for weather information."""

    name = "weather"
    description = "Get weather information for locations"
    category = ToolCategory.DATA_ACCESS

    def __init__(self, api_key: Optional[str] = None):
        """Initialize weather skill."""
        self.api_key = api_key

    async def execute(self, operation: str, **kwargs) -> ToolResult:
        """Execute weather operation."""
        try:
            if operation == "current":
                return await self._get_current(
                    kwargs.get("location"),
                    kwargs.get("units", "metric"),
                )
            elif operation == "forecast":
                return await self._get_forecast(
                    kwargs.get("location"),
                    kwargs.get("days", 3),
                    kwargs.get("units", "metric"),
                )
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    async def _get_current(self, location: str, units: str) -> ToolResult:
        """Get current weather."""
        if not location:
            return ToolResult(success=False, error="Location is required")

        # Use OpenWeatherMap API if key provided
        if self.api_key:
            return await self._openweather_current(location, units)
        else:
            # Return mock data for demo
            return ToolResult(
                success=True,
                data={
                    "location": location,
                    "temperature": 20,
                    "conditions": "partly cloudy",
                    "humidity": 65,
                    "wind_speed": 10,
                    "units": units,
                },
            )

    async def _get_forecast(self, location: str, days: int, units: str) -> ToolResult:
        """Get weather forecast."""
        if not location:
            return ToolResult(success=False, error="Location is required")

        if self.api_key:
            return await self._openweather_forecast(location, days, units)
        else:
            # Return mock data for demo
            forecast = []
            conditions = ["sunny", "cloudy", "rainy", "partly cloudy"]

            for i in range(days):
                import random
                forecast.append({
                    "day": i + 1,
                    "temp_high": random.randint(15, 30),
                    "temp_low": random.randint(5, 15),
                    "conditions": random.choice(conditions),
                })

            return ToolResult(
                success=True,
                data={
                    "location": location,
                    "forecast": forecast,
                    "days": days,
                    "units": units,
                },
            )

    async def _openweather_current(self, location: str, units: str) -> ToolResult:
        """Get current weather from OpenWeatherMap."""
        import aiohttp

        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {
            "q": location,
            "units": units,
            "appid": self.api_key,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return ToolResult(
                        success=False,
                        error=f"Weather API error: {response.status}",
                    )

                data = await response.json()

                return ToolResult(
                    success=True,
                    data={
                        "location": data.get("name"),
                        "country": data.get("sys", {}).get("country"),
                        "temperature": data.get("main", {}).get("temp"),
                        "feels_like": data.get("main", {}).get("feels_like"),
                        "humidity": data.get("main", {}).get("humidity"),
                        "pressure": data.get("main", {}).get("pressure"),
                        "wind_speed": data.get("wind", {}).get("speed"),
                        "conditions": data.get("weather", [{}])[0].get("description"),
                        "icon": data.get("weather", [{}])[0].get("icon"),
                    },
                )

    async def _openweather_forecast(
        self,
        location: str,
        days: int,
        units: str,
    ) -> ToolResult:
        """Get forecast from OpenWeatherMap."""
        import aiohttp

        url = f"https://api.openweathermap.org/data/2.5/forecast"
        params = {
            "q": location,
            "units": units,
            "cnt": days * 8,  # 3-hour intervals
            "appid": self.api_key,
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as response:
                if response.status != 200:
                    return ToolResult(
                        success=False,
                        error=f"Weather API error: {response.status}",
                    )

                data = await response.json()

                forecasts = []
                for item in data.get("list", []):
                    forecasts.append({
                        "datetime": item.get("dt_txt"),
                        "temperature": item.get("main", {}).get("temp"),
                        "conditions": item.get("weather", [{}])[0].get("description"),
                    })

                return ToolResult(
                    success=True,
                    data={
                        "location": data.get("city", {}).get("name"),
                        "forecast": forecasts,
                    },
                )
