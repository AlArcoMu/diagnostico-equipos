import copy
import json
import unittest
from datetime import datetime
from pathlib import Path

from diagnostico import analysis
from diagnostico.analysis import CRITICAL, OK, WARNING

DEMO = json.loads((Path(__file__).parent.parent / "diagnostico" / "demo.json").read_text(encoding="utf-8"))
NOW = datetime(2026, 10, 29, 10, 15)


def healthy():
    data = copy.deepcopy(DEMO)
    data["disks"] = [{"drive": "C:", "size": 500e9, "free": 300e9}]
    data["physicalDisks"] = [{"name": "SSD", "health": "Healthy"}]
    data["system"]["lastBoot"] = "2026-10-28T08:00:00"
    data["system"]["ramFreeKB"] = 8_000_000
    data["pendingReboot"] = False
    data["printers"] = [{"name": "HP", "offline": False, "error": 0, "jobs": 0}]
    data["services"] = [{"name": "gupdate", "display": "Google Update", "state": "Stopped"}]
    data["events"] = [{"source": "x", "id": 1, "level": 2, "time": "2026-10-28T10:00:00"}]
    data["lastUpdate"] = {"id": "KB1", "date": "2026-10-20T00:00:00"}
    return data


def titles(data):
    return [f["title"] for f in analysis.analyse(data, NOW)]


class HealthyMachine(unittest.TestCase):
    def test_no_findings(self):
        findings = analysis.analyse(healthy(), NOW)
        self.assertEqual(findings, [])
        self.assertEqual(analysis.overall(findings), OK)


class Disks(unittest.TestCase):
    def test_almost_full_is_critical(self):
        data = healthy()
        data["disks"][0]["free"] = 20e9
        found = analysis.analyse(data, NOW)
        self.assertEqual(found[0]["level"], CRITICAL)
        self.assertIn("C:", found[0]["title"])

    def test_low_space_is_warning(self):
        data = healthy()
        data["disks"][0]["free"] = 75e9
        self.assertEqual(analysis.analyse(data, NOW)[0]["level"], WARNING)

    def test_unhealthy_physical_disk(self):
        data = healthy()
        data["physicalDisks"][0]["health"] = "2"
        found = analysis.analyse(data, NOW)
        self.assertEqual(found[0]["level"], CRITICAL)
        self.assertIn("dañado", found[0]["detail"])


class Network(unittest.TestCase):
    def test_apipa_address(self):
        data = healthy()
        data["network"][0]["ipv4"] = ["169.254.10.4"]
        self.assertIn("IP automática (169.254.x.x)", titles(data))

    def test_gateway_down(self):
        data = healthy()
        data["connectivity"]["gateway"]["ok"] = False
        self.assertIn("No responde la puerta de enlace", titles(data))

    def test_dns_failure_with_internet(self):
        data = healthy()
        data["connectivity"]["dns"]["ok"] = False
        self.assertEqual(titles(data), ["Fallo de DNS"])

    def test_no_internet(self):
        data = healthy()
        data["connectivity"]["internet"]["ok"] = False
        data["connectivity"]["http"]["ok"] = False
        self.assertIn("Sin salida a internet", titles(data))

    def test_weak_wifi(self):
        data = healthy()
        data["connectivity"]["wifi"] = {"ssid": "Oficina", "signal": 35}
        self.assertIn("Señal Wi-Fi débil", titles(data))


class System(unittest.TestCase):
    def test_uptime_and_pending_reboot(self):
        data = healthy()
        data["system"]["lastBoot"] = "2026-10-10T08:00:00"
        data["pendingReboot"] = True
        found = titles(data)
        self.assertIn("El equipo lleva tiempo sin reiniciarse", found)
        self.assertIn("Reinicio pendiente", found)

    def test_ram_almost_full(self):
        data = healthy()
        data["system"]["ramFreeKB"] = 500_000
        self.assertIn("Memoria RAM casi agotada", titles(data))

    def test_old_updates(self):
        data = healthy()
        data["lastUpdate"]["date"] = "2026-07-01T00:00:00"
        self.assertIn("Actualizaciones atrasadas", titles(data))


class Security(unittest.TestCase):
    def test_antivirus_states(self):
        self.assertEqual(analysis.antivirus_state(397568), {"enabled": True, "updated": True})
        self.assertEqual(analysis.antivirus_state(393472), {"enabled": False, "updated": True})
        self.assertEqual(analysis.antivirus_state(397584), {"enabled": True, "updated": False})

    def test_disabled_antivirus_is_critical(self):
        data = healthy()
        data["antivirus"][0]["state"] = 393472
        found = analysis.analyse(data, NOW)
        self.assertEqual(found[0]["level"], CRITICAL)


class PrintersAndServices(unittest.TestCase):
    def test_offline_printer_and_stuck_jobs(self):
        data = healthy()
        data["printers"] = [{"name": "Zebra", "offline": True, "jobs": 0}, {"name": "HP", "error": 8, "jobs": 2}]
        found = titles(data)
        self.assertIn("Zebra está sin conexión", found)
        self.assertIn("HP: atasco de papel", found)
        self.assertIn("HP tiene 2 trabajos en cola", found)

    def test_ignored_services_are_skipped(self):
        data = healthy()
        data["services"].append({"name": "Spooler", "display": "Cola de impresión", "state": "Stopped"})
        found = analysis.analyse(data, NOW)
        self.assertEqual(found[0]["title"], "Hay un servicio automático detenido")
        self.assertEqual(found[0]["detail"], "Cola de impresión.")


class Events(unittest.TestCase):
    def test_groups_by_source_and_id(self):
        groups = analysis.event_groups(DEMO["events"])
        self.assertEqual(groups[0]["source"], "Microsoft-Windows-Kernel-Power")
        outlook = next(g for g in groups if g["id"] == 1000)
        self.assertEqual(outlook["count"], 12)


class Summary(unittest.TestCase):
    def test_summary_for_ticket(self):
        found = analysis.analyse(DEMO, NOW)
        text = analysis.summary_text(DEMO, found, "INC0012345", "No imprime")
        self.assertIn("Ticket: INC0012345", text)
        self.assertIn("[CRÍTICO] La unidad C: está casi llena", text)
        self.assertTrue(text.startswith("DIAGNÓSTICO PC-OFICINA-07 · 29/10/2026 10:15"))

    def test_summary_with_missing_data(self):
        text = analysis.summary_text({"system": {"computer": "PC"}}, [])
        self.assertNotIn("S/N", text)
        self.assertIn("Sin avisos", text)


if __name__ == "__main__":
    unittest.main()
