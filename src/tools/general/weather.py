"""Weather tool for fetching weather data - 使用 Open-Meteo API."""
import asyncio
import os
from typing import Any, Optional

try:
    import aiohttp
    from aiohttp import ClientTimeout
except ImportError:
    aiohttp = None
    ClientTimeout = None

from src.tools.base import Tool, ToolResult, ToolCategory


CITY_COORDS = {
    "北京": {"lat": 39.9042, "lon": 116.4074},
    "beijing": {"lat": 39.9042, "lon": 116.4074},
    "上海": {"lat": 31.2304, "lon": 121.4737},
    "shanghai": {"lat": 31.2304, "lon": 121.4737},
    "广州": {"lat": 23.1291, "lon": 113.2644},
    "guangzhou": {"lat": 23.1291, "lon": 113.2644},
    "深圳": {"lat": 22.5431, "lon": 114.0579},
    "shenzhen": {"lat": 22.5431, "lon": 114.0579},
    "成都": {"lat": 30.5728, "lon": 104.0668},
    "chengdu": {"lat": 30.5728, "lon": 104.0668},
    "杭州": {"lat": 30.2741, "lon": 120.1551},
    "hangzhou": {"lat": 30.2741, "lon": 120.1551},
    "南京": {"lat": 32.0603, "lon": 118.7969},
    "nanjing": {"lat": 32.0603, "lon": 118.7969},
    "武汉": {"lat": 30.5928, "lon": 114.3055},
    "wuhan": {"lat": 30.5928, "lon": 114.3055},
    "西安": {"lat": 34.3416, "lon": 108.9398},
    "xian": {"lat": 34.3416, "lon": 108.9398},
    "重庆": {"lat": 29.4316, "lon": 106.9123},
    "chongqing": {"lat": 29.4316, "lon": 106.9123},
    "天津": {"lat": 39.3434, "lon": 117.3616},
    "tianjin": {"lat": 39.3434, "lon": 117.3616},
    "苏州": {"lat": 31.2989, "lon": 120.5853},
    "suzhou": {"lat": 31.2989, "lon": 120.5853},
    "兰州": {"lat": 36.0611, "lon": 103.8343},
    "lanzhou": {"lat": 36.0611, "lon": 103.8343},
}


class WeatherTool(Tool):
    """Tool for fetching weather data from Open-Meteo API."""

    name = "weather"
    description = "Get weather information for cities. Supports current weather and forecasts."
    category = "general"
    parameters = {
        "type": "object",
        "properties": {
            "operation": {"type": "string", "description": "Type of operation - 'current' or 'forecast'", "enum": ["current", "forecast"]},
            "city": {"type": "string", "description": "City name (Chinese or English, e.g., 'Beijing', '上海', '北京')"},
            "days": {"type": "integer", "description": "Number of days for forecast (1-7)", "minimum": 1, "maximum": 7},
        },
        "required": ["city"]
    }

    def __init__(self, api_key: Optional[str] = None):
        """Initialize weather tool."""
        self.api_key = api_key

    def _get_coords(self, city: str) -> tuple[float, float] | None:
        """Get coordinates for a city."""
        city_lower = city.lower().strip()
        if city_lower in CITY_COORDS:
            coords = CITY_COORDS[city_lower]
            return coords["lat"], coords["lon"]
        for name, coords in CITY_COORDS.items():
            if name.lower() in city_lower or city_lower in name.lower():
                return coords["lat"], coords["lon"]
        return None

    async def execute(
        self,
        operation: str = "current",
        city: str = None,
        **kwargs
    ) -> str:
        """Execute weather operation."""
        if not city:
            return "Error: City is required"

        try:
            if operation == "current":
                result = await self.get_current_weather(city)
            elif operation == "forecast":
                result = await self.get_forecast(city, kwargs.get("days", 3))
            else:
                return f"Error: Unknown operation: {operation}"
            
            if result.success:
                return str(result.data)
            else:
                return f"Error: {result.error}"
        except Exception as e:
            return f"Error: {str(e)}"
            return ToolResult(success=False, error=str(e))

    async def get_current_weather(self, city: str) -> ToolResult:
        """Get current weather using Open-Meteo API."""
        coords = self._get_coords(city)
        if not coords:
            return ToolResult(success=False, error=f"Unknown city: {city}")
        
        lat, lon = coords
        url = f"https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m",
            "timezone": "Asia/Shanghai",
        }

        try:
            timeout = ClientTimeout(total=15)
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return ToolResult(success=False, error=f"API error: {response.status}")
                    
                    data = await response.json()
                    current = data.get("current", {})
                    
                    weather_desc = self._weather_code_to_desc(current.get("weather_code", 0))
                    
                    result = {
                        "location": city,
                        "temperature_c": current.get("temperature_2m"),
                        "feels_like_c": current.get("apparent_temperature"),
                        "humidity": current.get("relative_humidity_2m"),
                        "wind_speed_kph": current.get("wind_speed_10m"),
                        "weather": weather_desc,
                    }
                    
                    return ToolResult(success=True, data=result)
                    
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="Request timeout")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to fetch weather: {str(e)}")

    async def get_forecast(self, city: str, days: int = 3) -> ToolResult:
        """Get weather forecast."""
        coords = self._get_coords(city)
        if not coords:
            return ToolResult(success=False, error=f"Unknown city: {city}")
        
        lat, lon = coords
        days = min(max(days, 1), 7)
        
        url = f"https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": "temperature_2m_max,temperature_2m_min,weather_code",
            "timezone": "Asia/Shanghai",
            "forecast_days": days,
        }

        try:
            timeout = ClientTimeout(total=15)
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        return ToolResult(success=False, error=f"API error: {response.status}")
                    
                    data = await response.json()
                    daily = data.get("daily", {})
                    
                    forecasts = []
                    dates = daily.get("time", [])
                    max_temps = daily.get("temperature_2m_max", [])
                    min_temps = daily.get("temperature_2m_min", [])
                    weather_codes = daily.get("weather_code", [])
                    
                    for i in range(len(dates)):
                        forecasts.append({
                            "date": dates[i],
                            "temperature_c_max": max_temps[i] if i < len(max_temps) else None,
                            "temperature_c_min": min_temps[i] if i < len(min_temps) else None,
                            "weather": self._weather_code_to_desc(weather_codes[i] if i < len(weather_codes) else 0),
                        })
                    
                    result = {
                        "location": city,
                        "forecast": forecasts,
                    }
                    
                    return ToolResult(success=True, data=result)
                    
        except asyncio.TimeoutError:
            return ToolResult(success=False, error="Request timeout")
        except Exception as e:
            return ToolResult(success=False, error=f"Failed to fetch forecast: {str(e)}")

    def _weather_code_to_desc(self, code: int) -> str:
        """Convert WMO weather code to description."""
        codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Fog",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            56: "Light freezing drizzle",
            57: "Dense freezing drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            66: "Light freezing rain",
            67: "Heavy freezing rain",
            71: "Slight snow fall",
            73: "Moderate snow fall",
            75: "Heavy snow fall",
            77: "Snow grains",
            80: "Slight rain showers",
            81: "Moderate rain showers",
            82: "Violent rain showers",
            85: "Slight snow showers",
            86: "Heavy snow showers",
            95: "Thunderstorm",
            96: "Thunderstorm with slight hail",
            99: "Thunderstorm with heavy hail",
        }
        return codes.get(code, "Unknown")
