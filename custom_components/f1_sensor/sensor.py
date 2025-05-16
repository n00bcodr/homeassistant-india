from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import async_timeout
import datetime

from .const import DOMAIN


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Create sensors when the integration is added."""
    data = hass.data[DOMAIN][entry.entry_id]
    race_coordinator = data["race_coordinator"]
    driver_coordinator = data["driver_coordinator"]
    constructor_coordinator = data["constructor_coordinator"]

    base = entry.data.get("sensor_name", "F1")
    # Read user's selection of sensors
    enabled = entry.data.get("enabled_sensors", [])
    # Map key to sensor class and coordinator
    mapping = {
        "next_race": (F1NextRaceSensor, data["race_coordinator"]),
        "current_season": (F1CurrentSeasonSensor, data["race_coordinator"]),
        "driver_standings": (F1DriverStandingsSensor, data["driver_coordinator"]),
        "constructor_standings": (F1ConstructorStandingsSensor, data["constructor_coordinator"]),
        "weather": (F1WeatherSensor, data["race_coordinator"]),
    }
    sensors = []
    for key in enabled:
        cls, coord = mapping.get(key, (None, None))
        if cls and coord:
            sensors.append(cls(coord, f"{base}_{key}"))
    async_add_entities(sensors, True)


class F1NextRaceSensor(CoordinatorEntity, SensorEntity):
    """Sensor showing the next race's start time and attributes."""
    def __init__(self, coordinator, sensor_name):
        super().__init__(coordinator)
        self._attr_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_unique"
        self._attr_icon = "mdi:flag-checkered"
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    def _get_next_race(self):
        data = self.coordinator.data
        if not data:
            return None
        races = data["MRData"]["RaceTable"]["Races"]
        now = datetime.datetime.now(datetime.timezone.utc)
        for race in races:
            dt = self.combine_date_time(race.get("date"), race.get("time"))
            if dt and datetime.datetime.fromisoformat(dt) > now:
                return race
        return None

    def combine_date_time(self, date_str, time_str):
        if not date_str:
            return None
        dt_str = f"{date_str}T{(time_str or '00:00:00Z')}".replace("Z", "+00:00")
        try:
            return datetime.datetime.fromisoformat(dt_str).isoformat()
        except ValueError:
            return None

    @property
    def state(self):
        race = self._get_next_race()
        return self.combine_date_time(race.get("date"), race.get("time")) if race else None

    @property
    def extra_state_attributes(self):
        race = self._get_next_race()
        if not race:
            return {}
        circuit = race.get("Circuit", {})
        loc = circuit.get("Location", {})
        first = race.get("FirstPractice", {})
        second = race.get("SecondPractice", {})
        third = race.get("ThirdPractice", {})
        qual = race.get("Qualifying", {})
        sprintq = race.get("SprintQualifying", {})
        sprint = race.get("Sprint", {})
        return {
            "season": race.get("season"),
            "round": race.get("round"),
            "race_name": race.get("raceName"),
            "race_url": race.get("url"),
            "circuit_id": circuit.get("circuitId"),
            "circuit_name": circuit.get("circuitName"),
            "circuit_url": circuit.get("url"),
            "circuit_lat": loc.get("lat"),
            "circuit_long": loc.get("long"),
            "circuit_locality": loc.get("locality"),
            "circuit_country": loc.get("country"),
            "race_start": self.combine_date_time(race.get("date"), race.get("time")),
            "first_practice_start": self.combine_date_time(first.get("date"), first.get("time")),
            "second_practice_start": self.combine_date_time(second.get("date"), second.get("time")),
            "third_practice_start": self.combine_date_time(third.get("date"), third.get("time")),
            "qualifying_start": self.combine_date_time(qual.get("date"), qual.get("time")),
            "sprint_qualifying_start": self.combine_date_time(sprintq.get("date"), sprintq.get("time")),
            "sprint_start": self.combine_date_time(sprint.get("date"), sprint.get("time")),
        }


class F1WeatherSensor(CoordinatorEntity, SensorEntity):
    """Sensor for weather: fetched at the same time as the F1 data coordinator."""
    def __init__(self, coordinator, sensor_name):
        super().__init__(coordinator)
        self._attr_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_unique"
        self._attr_icon = "mdi:weather-partly-cloudy"
        self._current = {}
        self._race = {}

    async def async_added_to_hass(self):
        await super().async_added_to_hass()
        # Run _update_weather when the coordinator updates
        def _listener():
            self.hass.async_create_task(self._update_weather())
        removal = self.coordinator.async_add_listener(_listener)
        self.async_on_remove(removal)
        # Initial update
        await self._update_weather()

    async def _update_weather(self):
        race = F1NextRaceSensor(self.coordinator, "")._get_next_race()
        loc = race.get("Circuit", {}).get("Location", {}) if race else {}
        lat, lon = loc.get("lat"), loc.get("long")
        if lat is None or lon is None:
            return
        session = async_get_clientsession(self.hass)
        url = f"https://api.met.no/weatherapi/locationforecast/2.0/compact?lat={lat}&lon={lon}"
        headers = {"User-Agent": "homeassistant-f1_sensor"}
        try:
            async with async_timeout.timeout(10):
                resp = await session.get(url, headers=headers)
                data = await resp.json()
        except Exception:
            return
        times = data.get("properties", {}).get("timeseries", [])
        if not times:
            return
        curr = times[0].get("data", {}).get("instant", {}).get("details", {})
        self._current = self._extract(curr)
        # Race start forecast only if the same calendar date exists in the forecast
        start_iso = None
        if race:
            start_iso = F1NextRaceSensor(self.coordinator, "").combine_date_time(race.get("date"), race.get("time"))
        # default: no values
        self._race = {k: None for k in self._current}
        if start_iso:
            start_dt = datetime.datetime.fromisoformat(start_iso)
            # filter forecasts that are on the same date as the race start
            same_day = [
                t for t in times
                if datetime.datetime.fromisoformat(t.get("time")).date() == start_dt.date()
            ]
            if same_day:
                # choose the closest time
                closest = min(
                    same_day,
                    key=lambda t: abs(datetime.datetime.fromisoformat(t.get("time")) - start_dt)
                )
                rd = closest.get("data", {}).get("instant", {}).get("details", {})
                self._race = self._extract(rd)
        self.async_write_ha_state()

    def _extract(self, d):
        wd = d.get("wind_from_direction")
        return {
            "temperature": d.get("air_temperature"),
            "temperature_unit": "celsius",
            "humidity": d.get("relative_humidity"),
            "humidity_unit": "%",
            "cloud_cover": d.get("cloud_area_fraction"),
            "cloud_cover_unit": "%",
            "precipitation": d.get("precipitation_amount", 0),
            "precipitation_unit": "mm",
            "wind_speed": d.get("wind_speed"),
            "wind_speed_unit": "m/s",
            "wind_direction": self._abbr(wd),
            "wind_from_direction_degrees": wd,
            "wind_from_direction_unit": "degrees"
        }

    def _abbr(self, deg):
        if deg is None:
            return None
        dirs = [(i*22.5, d) for i, d in enumerate([
            "N","NNE","NE","ENE","E","ESE","SE","SSE",
            "S","SSW","SW","WSW","W","WNW","NW","NNW","N"
        ])]
        return min(dirs, key=lambda x: abs(deg - x[0]))[1]

    @property
    def state(self):
        return self._current.get("temperature")

    @property
    def extra_state_attributes(self):
        attrs = {}
        for k, v in self._current.items():
            attrs[f"current_{k}"] = v
        for k, v in self._race.items():
            attrs[f"race_{k}"] = v
        return attrs


class F1CurrentSeasonSensor(CoordinatorEntity, SensorEntity):
    """Sensor for number of races and list."""
    def __init__(self, coordinator, sensor_name):
        super().__init__(coordinator)
        self._attr_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_unique"
        self._attr_icon = "mdi:calendar-month"

    @property
    def state(self):
        d = self.coordinator.data
        return len(d.get("MRData", {}).get("RaceTable", {}).get("Races", [])) if d else None

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        if not d:
            return {}
        r = d.get("MRData", {}).get("RaceTable", {})
        return {"season": r.get("season"), "races": r.get("Races", [])}


class F1DriverStandingsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for driver standings."""
    def __init__(self, coordinator, sensor_name):
        super().__init__(coordinator)
        self._attr_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_unique"
        self._attr_icon = "mdi:account-multiple-check"

    @property
    def state(self):
        d = self.coordinator.data
        lists = d.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
        return len(lists[0].get("DriverStandings", [])) if lists else 0

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        lists = d.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
        if not lists:
            return {}
        f = lists[0]
        return {"season": f.get("season"), "round": f.get("round"), "driver_standings": f.get("DriverStandings", [])}


class F1ConstructorStandingsSensor(CoordinatorEntity, SensorEntity):
    """Sensor for constructor standings."""
    def __init__(self, coordinator, sensor_name):
        super().__init__(coordinator)
        self._attr_name = sensor_name
        self._attr_unique_id = f"{sensor_name}_unique"
        self._attr_icon = "mdi:factory"

    @property
    def state(self):
        d = self.coordinator.data
        lists = d.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
        return len(lists[0].get("ConstructorStandings", [])) if lists else 0

    @property
    def extra_state_attributes(self):
        d = self.coordinator.data
        lists = d.get("MRData", {}).get("StandingsTable", {}).get("StandingsLists", [])
        if not lists:
            return {}
        f = lists[0]
        return {"season": f.get("season"), "round": f.get("round"), "constructor_standings": f.get("ConstructorStandings", [])}
