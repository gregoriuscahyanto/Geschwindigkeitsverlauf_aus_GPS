import unittest

from qt_route_selector.app_entry import _install_persistent_simulation_window
from qt_route_selector.simulation_settings import PersistentSimulationSettingsMixin


class AppEntrySettingsTests(unittest.TestCase):
    def test_settings_mixin_is_installed(self):
        cls = _install_persistent_simulation_window()
        self.assertTrue(issubclass(cls, PersistentSimulationSettingsMixin))
        self.assertTrue(hasattr(cls, "save_simulation_settings"))


if __name__ == "__main__":
    unittest.main()
