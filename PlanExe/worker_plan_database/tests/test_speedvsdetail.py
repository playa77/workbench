import unittest

from worker_plan_internal.plan.speedvsdetail import SpeedVsDetailEnum
from worker_plan_database.speedvsdetail import resolve_speedvsdetail


class TestResolveSpeedVsDetail(unittest.TestCase):
    def test_speed_vs_detail_value(self):
        parameters = {"speed_vs_detail": SpeedVsDetailEnum.PING_LLM.value}
        self.assertEqual(resolve_speedvsdetail(parameters), SpeedVsDetailEnum.PING_LLM)

    def test_invalid_value_falls_back_to_fast(self):
        parameters = {"speed_vs_detail": "invalid", "fast": ""}
        self.assertEqual(resolve_speedvsdetail(parameters), SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS)

    def test_fast_flag_falls_back(self):
        parameters = {"fast": "true"}
        self.assertEqual(resolve_speedvsdetail(parameters), SpeedVsDetailEnum.FAST_BUT_SKIP_DETAILS)

    def test_default_all_details(self):
        self.assertEqual(resolve_speedvsdetail(None), SpeedVsDetailEnum.ALL_DETAILS_BUT_SLOW)


if __name__ == "__main__":
    unittest.main()
