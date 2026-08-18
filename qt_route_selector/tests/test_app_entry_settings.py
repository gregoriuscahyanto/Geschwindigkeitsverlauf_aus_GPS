import inspect
import unittest

from qt_route_selector.app_entry import (
    CompleteApplicationWindow,
    _install_persistent_simulation_window,
)
from qt_route_selector.simulation_settings import PersistentSimulationSettingsMixin
from qt_route_selector.speed_axis_autoscale import SpeedAxisAutoscaleMixin


class AppEntrySettingsTests(unittest.TestCase):
    def test_settings_and_autoscale_mixins_are_installed(self):
        cls = _install_persistent_simulation_window()
        self.assertTrue(issubclass(cls, PersistentSimulationSettingsMixin))
        self.assertTrue(issubclass(cls, SpeedAxisAutoscaleMixin))
        self.assertTrue(hasattr(cls, "save_simulation_settings"))

    def test_visible_simulation_tab_uses_final_patched_class(self):
        source = inspect.getsource(CompleteApplicationWindow._ensure_simulation_created)
        self.assertIn("simulation_type = _install_persistent_simulation_window()", source)
        self.assertIn("simulation = simulation_type(", source)
        self.assertNotIn("super()._ensure_simulation_created()", source)


if __name__ == "__main__":
    unittest.main()
