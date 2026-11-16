import unittest

from poll_az511 import select_sites


class ArizonaPublishTest(unittest.TestCase):
    def test_keeps_only_open_numeric_counts(self):
        document = select_sites(
            [
                {
                    "Id": 8,
                    "Name": "Texas Canyon Rest Area (EB)",
                    "Latitude": 32.059722,
                    "Longitude": -110.076111,
                    "Location": "I-10 / MP 320",
                    "Status": "Open",
                    "TotalTruckSpaces": "22",
                    "AvailableTruckSpaces": "5",
                },
                {
                    "Id": 9,
                    "Name": "No reading",
                    "Latitude": 32.2,
                    "Longitude": -109.0,
                    "Status": "Open",
                    "TotalTruckSpaces": "17",
                    "AvailableTruckSpaces": "No Data",
                },
                {
                    "Id": 10,
                    "Name": "Closed",
                    "Latitude": 33.0,
                    "Longitude": -112.0,
                    "Status": "Closed",
                    "TotalTruckSpaces": "12",
                    "AvailableTruckSpaces": "4",
                },
            ],
            "2026-11-16T22:00:00Z",
        )
        self.assertEqual(len(document["sites"]), 1)
        self.assertEqual(document["sites"][0]["available"], 5)
        self.assertEqual(document["sites"][0]["id"], "8")
        self.assertNotIn("key", json_text(document))


def json_text(document):
    import json

    return json.dumps(document)


if __name__ == "__main__":
    unittest.main()
