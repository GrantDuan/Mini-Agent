"""Quick test for WeatherTool"""

import asyncio
from mini_agent.tools.weather_tool import WeatherTool


async def test_weather_tool():
    """Test the WeatherTool directly."""
    tool = WeatherTool()

    print("Testing WeatherTool...")
    print("=" * 60)

    # Test cities
    cities = ["Shanghai", "Beijing", "London", "New York"]

    for city in cities:
        print(f"\nQuerying weather for {city}...")
        result = await tool.execute(city=city)

        if result.success:
            print(f"✅ Success!")
            print(result.content)
        else:
            print(f"❌ Failed: {result.error}")

        print("-" * 60)


if __name__ == "__main__":
    asyncio.run(test_weather_tool())
