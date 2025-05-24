from django.shortcuts import render
from .forms import CityForm
import openmeteo_requests
import pandas as pd
import requests_cache
from retry_requests import retry
import requests
from zoneinfo import ZoneInfo
from datetime import datetime
from django.http import JsonResponse
from django.views.decorators.http import require_GET

@require_GET
def autocomplete(request):
    query = request.GET.get('q', '')
    if not query:
        return JsonResponse([], safe=False)

    url = "https://nominatim.openstreetmap.org/search"
    params = {
        'q': query,
        'format': 'json',
        'limit': 10,
        'accept-language': 'ru',
        'addressdetails': 1
    }
    headers = {
        'User-Agent': 'weather-app/1.0'
    }

    try:
        response = requests.get(url, params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        city_list = []

        for item in data:
            city = item.get('display_name')
            if city:
                city_list.append(city)
    except Exception as e:
        print(f"Autocomplete error: {e}")
        city_list = []

    return JsonResponse(city_list, safe=False)

weather_codes = {
    0: ("☀️", "Ясно"),
    1: ("🌤️", "Малооблачно"),
    2: ("⛅", "Переменная облачность"),
    3: ("☁️", "Облачно"),
    45: ("🌫️", "Туман"),
    48: ("🌫️", "Дымка"),
    51: ("🌦️", "Морось"),
    53: ("🌧️", "Дождь"),
    55: ("🌧️", "Сильный дождь"),
    61: ("🌧️", "Дождь"),
    63: ("🌧️", "Сильный дождь"),
    65: ("🌧️", "Очень сильный дождь"),
    71: ("❄️", "Снег"),
    73: ("❄️", "Снег"),
    75: ("❄️", "Сильный снег"),
    80: ("🌧️", "Ливень"),
    81: ("🌧️", "Ливень"),
    82: ("🌧️", "Сильный ливень"),
    95: ("⛈️", "Гроза"),
    96: ("⛈️", "Гроза с градом"),
    99: ("⛈️", "Гроза с крупным градом"),
}

def get_coordinates(city_name):
    url = f"https://nominatim.openstreetmap.org/search"
    params = {
        'q': city_name,
        'format': 'json'
    }
    headers = {
        'User-Agent': 'weather-app/1.0'
    }

    response = requests.get(url, params=params, headers=headers)

    if response.status_code != 200:
        print(f"Error fetching coordinates: {response.status_code}")
        return None, None

    try:
        data = response.json()
    except Exception as e:
        print(f"JSON decode error: {e}")
        return None, None

    if not data:
        return None, None

    lat = data[0]['lat']
    lon = data[0]['lon']
    return float(lat), float(lon)


def get_weather(lat, lon):
    cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
    retry_session = retry(cache_session, retries=5, backoff_factor=0.2)
    openmeteo = openmeteo_requests.Client(session=retry_session)

    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,weathercode",  # Добавили weathercode
        "timezone": "auto"
    }

    responses = openmeteo.weather_api(url, params=params)
    response = responses[0]

    hourly = response.Hourly()
    hourly_temperature_2m = hourly.Variables(0).ValuesAsNumpy()
    hourly_weathercode = hourly.Variables(1).ValuesAsNumpy()  # Получаем weathercode

    hourly_data = {
        "date": pd.date_range(
            start=pd.to_datetime(hourly.Time(), unit="s", utc=True),
            end=pd.to_datetime(hourly.TimeEnd(), unit="s", utc=True),
            freq=pd.Timedelta(seconds=hourly.Interval()),
            inclusive="left"
        ),
        "temperature_2m": hourly_temperature_2m,
        "weathercode": hourly_weathercode  # Добавляем в данные
    }

    df = pd.DataFrame(data=hourly_data)

    tzname = response.Timezone()
    if isinstance(tzname, bytes):
        tzname = tzname.decode('utf-8')
    tz = ZoneInfo(tzname)
    now = datetime.now(tz)
    offset_seconds = now.utcoffset().total_seconds()
    hours = int(offset_seconds // 3600)
    minutes = int((offset_seconds % 3600) // 60)
    utc_offset_str = f"UTC{'+' if hours >= 0 else '-'}{abs(hours):02d}:{abs(minutes):02d}"

    return {
        "latitude": response.Latitude(),
        "longitude": response.Longitude(),
        "timezone": utc_offset_str,
        "elevation": response.Elevation(),
        "forecast": df.head(12)
    }


def index(request):
    weather_data = None
    city_name = None

    if request.method == 'POST':
        form = CityForm(request.POST)
        if form.is_valid():
            city_name = form.cleaned_data['city']
            lat, lon = get_coordinates(city_name)
            if lat and lon:
                weather_data = get_weather(lat, lon)
    else:
        form = CityForm()

    return render(request, 'weathertrak/index.html', {
        'form': form,
        'weather': weather_data,
        'city': city_name,
        'weather_codes': weather_codes
    })
