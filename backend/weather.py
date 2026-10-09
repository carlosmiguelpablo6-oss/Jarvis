import json
import urllib.parse
import urllib.request

# Change these to move the weather to another place.
LOCATION_NAME = "Manila"
LATITUDE = 14.5995
LONGITUDE = 120.9842
TIMEZONE = "Asia/Manila"

# WMO weather codes used by Open-Meteo.
WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Fog",
    51: "Light drizzle",
    53: "Drizzle",
    55: "Heavy drizzle",
    56: "Freezing drizzle",
    57: "Freezing drizzle",
    61: "Light rain",
    63: "Rain",
    65: "Heavy rain",
    66: "Freezing rain",
    67: "Freezing rain",
    71: "Light snow",
    73: "Snow",
    75: "Heavy snow",
    77: "Snow grains",
    80: "Light rain showers",
    81: "Rain showers",
    82: "Heavy rain showers",
    85: "Snow showers",
    86: "Snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with hail",
    99: "Thunderstorm with hail",
}


def _fetch_json(url, timeout=5):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def get_weather():
    """Today's weather from Open-Meteo (free, no key). Returns None if unavailable."""
    query = urllib.parse.urlencode(
        {
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "current": "temperature_2m,weather_code",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max",
            "timezone": TIMEZONE,
            "forecast_days": 1,
        }
    )
    try:
        data = _fetch_json(f"https://api.open-meteo.com/v1/forecast?{query}")
        current = data["current"]
        daily = data["daily"]
        return {
            "now_c": current["temperature_2m"],
            "code": current["weather_code"],
            "high_c": daily["temperature_2m_max"][0],
            "low_c": daily["temperature_2m_min"][0],
            "rain_pct": daily["precipitation_probability_max"][0],
        }
    except Exception as err:
        print("Weather unavailable:", err, flush=True)
        return None


def format_weather(weather):
    if not weather:
        return (
            f"Weather in {LOCATION_NAME}: I can't reach the weather service right now "
            "(are you online?)."
        )
    text = f"Weather in {LOCATION_NAME}: {WEATHER_CODES.get(weather['code'], 'Mixed conditions')}"
    if weather.get("now_c") is not None:
        text += f", {round(weather['now_c'])}\u00b0C now"
    text += "."
    today = []
    if weather.get("high_c") is not None and weather.get("low_c") is not None:
        today.append(f"high {round(weather['high_c'])}\u00b0C, low {round(weather['low_c'])}\u00b0C")
    if weather.get("rain_pct") is not None:
        today.append(f"{round(weather['rain_pct'])}% chance of rain")
    if today:
        text += " Today: " + ", ".join(today) + "."
    return text