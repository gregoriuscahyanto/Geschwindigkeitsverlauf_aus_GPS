from __future__ import annotations

try:
    from .integrated_speed_profile_v13 import IntegratedSpeedProfileWindow, main
except ImportError:
    from integrated_speed_profile_v13 import IntegratedSpeedProfileWindow, main


__all__ = ["IntegratedSpeedProfileWindow", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
