"""Weather Query Tool - Query weather for any city using Open-Meteo API.

This tool allows the agent to:
- Query current weather for any city in the world
- Get temperature, wind speed, and weather conditions
- Uses Open-Meteo's free geocoding and weather APIs
"""

import requests
from typing import Any

from .base import Tool, ToolResult


class WeatherTool(Tool):
    """Tool for querying weather information for any city.

    This tool uses Open-Meteo API which is:
    - Completely free
    - No API key required
    - Supports worldwide cities

    The tool works in two steps:
    1. Use geocoding API to get coordinates for the city name
    2. Use weather API to get current weather data
    """

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return (
            "Get current weather information for any city. "
            "Provide the city name (e.g., 'Shanghai', 'Beijing', 'New York') "
            "and receive current temperature, wind speed, and weather conditions. "
            "Supports cities worldwide."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The name of the city to query weather for (e.g., 'Shanghai', 'London', 'Tokyo')",
                },
                "language": {
                    "type": "string",
                    "description": "Optional language code for location names (e.g., 'en', 'zh', 'ja'). Default is 'en'.",
                    "default": "en",
                },
            },
            "required": ["city"],
        }

    def _get_coordinates(self, city: str, language: str = "en") -> tuple[float, float, str] | None:
        """Get coordinates for a city using Open-Meteo geocoding API.

        Args:
            city: City name to search for
            language: Language code for results

        Returns:
            Tuple of (latitude, longitude, full_location_name) or None if not found
        """
        try:
            url = f"https://geocoding-api.open-meteo.com/v1/search?name={city}&count=1&language={language}&format=json"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            results = data.get("results", [])

            if not results:
                return None

            # Get first result
            result = results[0]
            lat = result.get("latitude")
            lon = result.get("longitude")
            name = result.get("name", city)
            country = result.get("country", "")
            admin1 = result.get("admin1", "")

            # Build full location name
            location_parts = [name]
            if admin1:
                location_parts.append(admin1)
            if country:
                location_parts.append(country)
            full_location = ", ".join(location_parts)

            if lat is None or lon is None:
                return None

            return (lat, lon, full_location)

        except Exception as e:
            print(f"Geocoding error: {e}")
            return None

    def _get_weather(self, latitude: float, longitude: float) -> dict | None:
        """Get current weather data using Open-Meteo API.

        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate

        Returns:
            Dictionary with weather data or None if failed
        """
        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast?"
                f"latitude={latitude}&longitude={longitude}"
                f"&current_weather=true"
                f"&timezone=auto"
            )
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()
            return data.get("current_weather")

        except Exception as e:
            print(f"Weather API error: {e}")
            return None

    def _format_weather(self, location: str, weather_data: dict) -> str:
        """Format weather data into human-readable text.

        Args:
            location: Full location name
            weather_data: Weather data from API

        Returns:
            Formatted weather string
        """
        temp = weather_data.get("temperature", "N/A")
        windspeed = weather_data.get("windspeed", "N/A")
        time = weather_data.get("time", "N/A")

        # Weather code mapping (WMO Weather interpretation codes)
        weather_codes = {
            0: "Clear sky",
            1: "Mainly clear",
            2: "Partly cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Depositing rime fog",
            51: "Light drizzle",
            53: "Moderate drizzle",
            55: "Dense drizzle",
            61: "Slight rain",
            63: "Moderate rain",
            65: "Heavy rain",
            71: "Slight snow",
            73: "Moderate snow",
            75: "Heavy snow",
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

        weather_code = weather_data.get("weathercode", 0)
        weather_desc = weather_codes.get(weather_code, "Unknown")

        return (
            f"Weather for {location}:\n"
            f"🌡️  Temperature: {temp}°C\n"
            f"☁️  Condition: {weather_desc}\n"
            f"💨 Wind Speed: {windspeed} km/h\n"
            f"🕐 Updated: {time}"
        )

    async def execute(self, city: str, language: str = "en") -> ToolResult:
        """Query weather for a city.

        Args:
            city: City name to query
            language: Language code for results

        Returns:
            ToolResult with weather information
        """
        try:
            # Step 1: Get coordinates
            coords = self._get_coordinates(city, language)
            if not coords:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"City '{city}' not found. Please check the spelling or try a different name.",
                )

            latitude, longitude, full_location = coords

            # Step 2: Get weather
            weather_data = self._get_weather(latitude, longitude)
            if not weather_data:
                return ToolResult(
                    success=False,
                    content="",
                    error=f"Failed to retrieve weather data for {full_location}",
                )

            # Step 3: Format result
            formatted_weather = self._format_weather(full_location, weather_data)

            return ToolResult(
                success=True,
                content=formatted_weather,
            )

        except Exception as e:
            return ToolResult(
                success=False,
                content="",
                error=f"Weather query failed: {str(e)}",
            )
