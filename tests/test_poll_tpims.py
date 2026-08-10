from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import poll_tpims


class PollerTests(unittest.TestCase):
    def test_public_poller_contains_only_working_tpims_feeds(self) -> None:
        self.assertEqual(set(poll_tpims.FEEDS), {"IL", "IN", "KY"})

    @patch("poll_tpims.requests.get")
    def test_tpims_requests_have_short_timeout(self, get: Mock) -> None:
        response = Mock()
        response.json.return_value = []
        get.return_value = response

        payload, error = poll_tpims.fetch("https://example.test/feed")

        self.assertEqual(payload, [])
        self.assertEqual(error, "")
        self.assertEqual(get.call_args.kwargs["timeout"], 9)

    @patch("poll_tpims._wfetch")
    def test_point_weather_uses_hourly_forecast(self, fetch: Mock) -> None:
        fetch.side_effect = [
            {"properties": {"forecastHourly": "https://example.test/hourly"}},
            {
                "properties": {
                    "periods": [
                        {
                            "temperature": 72,
                            "shortForecast": "Light Rain",
                            "probabilityOfPrecipitation": {"value": 40},
                            "windSpeed": "8 mph",
                        }
                    ]
                }
            },
        ]

        point, hourly_url, weather = poll_tpims._fetch_point_weather((45.0, -93.0), None)

        self.assertEqual(point, (45.0, -93.0))
        self.assertEqual(hourly_url, "https://example.test/hourly")
        self.assertEqual(weather["temp_f"], 72)
        self.assertEqual(weather["wind_mph"], 8)

    @patch("poll_tpims.collect_weather", return_value=(0, "disabled in test"))
    @patch("poll_tpims.fetch")
    def test_main_preserves_rows_when_weather_is_unavailable(
        self,
        fetch: Mock,
        _weather: Mock,
    ) -> None:
        dynamic = [
            {
                "siteId": "IL-1",
                "reportedAvailable": 7,
                "capacity": 20,
                "open": True,
            }
        ]
        fetch.side_effect = [(dynamic, "")] * 6
        original_data = poll_tpims.DATA
        try:
            with tempfile.TemporaryDirectory() as directory:
                poll_tpims.DATA = Path(directory)
                self.assertEqual(poll_tpims.main(), 0)
                csv_files = list(Path(directory).glob("*/tpims_dynamic.csv"))
                self.assertEqual(len(csv_files), 1)
                self.assertGreater(len(csv_files[0].read_text().splitlines()), 1)
        finally:
            poll_tpims.DATA = original_data


if __name__ == "__main__":
    unittest.main()
