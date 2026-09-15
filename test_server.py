import json
import unittest
from urllib.request import Request, urlopen
from threading import Thread
from http.server import ThreadingHTTPServer

from server import DroneRequestHandler


class ServerApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DroneRequestHandler)
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def test_locations_endpoint_is_empty_for_live_input_mode(self):
        with urlopen(f"{self.base_url}/api/locations") as response:
            data = json.loads(response.read())
        self.assertEqual(data, [])

    def test_plan_endpoint_accepts_multiple_drones(self):
        request = Request(
            f"{self.base_url}/api/plan",
            data=json.dumps(
                {
                    "drones": [
                        {"start": "17.3850, 78.4867", "goal": "17.9689, 79.5941"},
                        {"start": "17.2403, 78.4294", "goal": "18.4386, 79.1288"},
                    ]
                }
            ).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            data = json.loads(response.read())
        self.assertEqual(len(data["routes"]), 2)
        self.assertGreaterEqual(len(data["routes"][0]["path"]), 2)
        self.assertAlmostEqual(data["routes"][0]["start"]["lat"], 17.3850)
        self.assertIn("cost", data["routes"][0])

    def test_plan_endpoint_accepts_100_drones(self):
        missions = [
            {"start": "17.3850, 78.4867", "goal": "17.9689, 79.5941"}
            for _ in range(100)
        ]
        request = Request(
            f"{self.base_url}/api/plan",
            data=json.dumps({"drones": missions}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            data = json.loads(response.read())
        self.assertEqual(len(data["routes"]), 100)

    def test_owner_can_read_and_update_drone_status(self):
        request = Request(
            f"{self.base_url}/api/plan",
            data=json.dumps({"drones": [{"start": "17.3850, 78.4867", "goal": "17.9689, 79.5941"}]}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urlopen(request).read()
        status_request = Request(
            f"{self.base_url}/api/drones/status",
            data=json.dumps({"drone": 1, "status": "reached_safely", "lat": 17.9689, "lon": 79.5941}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(status_request) as response:
            status = json.loads(response.read())
        self.assertTrue(status["reached"])
        with urlopen(f"{self.base_url}/api/drones") as response:
            fleet = json.loads(response.read())
        self.assertEqual(fleet[0]["status"], "reached_safely")


if __name__ == "__main__":
    unittest.main()
