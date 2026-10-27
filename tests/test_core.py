import unittest
from decimal import Decimal

from core import brl, calculate_energy, pt_number, safe_spreadsheet_text


class EnergyCalculationTests(unittest.TestCase):
    def test_demo_60w_8_hours(self):
        result = calculate_energy(
            watts=60, hours_per_day=8, days_per_month=30,
            tariff_per_kwh="0.90",
        )
        self.assertEqual(result.daily_kwh, Decimal("0.48"))
        self.assertEqual(result.monthly_kwh, Decimal("14.40"))
        self.assertEqual(result.monthly_brl, Decimal("12.9600"))
        self.assertEqual(result.annual_brl, Decimal("155.5200"))

    def test_hypothetical_1200w_2_hours(self):
        result = calculate_energy(
            watts=1200, hours_per_day=2, days_per_month=30,
            tariff_per_kwh="0.90",
        )
        self.assertEqual(result.monthly_kwh, Decimal("72.0"))
        self.assertEqual(result.monthly_brl, Decimal("64.800"))

    def test_multiple_devices(self):
        result = calculate_energy(
            watts=100, hours_per_day=5, days_per_month=20,
            tariff_per_kwh=1, units=3,
        )
        self.assertEqual(result.monthly_kwh, Decimal("30.0"))
        self.assertEqual(result.monthly_brl, Decimal("30.0"))

    def test_zero_hours_has_zero_cost(self):
        result = calculate_energy(
            watts=120, hours_per_day=0, days_per_month=31,
            tariff_per_kwh=1.2,
        )
        self.assertEqual(result.monthly_brl, 0)

    def test_money_rounding_and_pt_br(self):
        self.assertEqual(brl("1234.565"), "R$ 1.234,57")
        self.assertEqual(pt_number("1440.5"), "1.440,50")

    def test_invalid_numbers_are_rejected(self):
        defaults = dict(
            watts=100, hours_per_day=2, days_per_month=30,
            tariff_per_kwh=1,
        )
        cases = [
            {"watts": 0}, {"watts": -10}, {"watts": "Infinity"},
            {"hours_per_day": 24.5}, {"hours_per_day": -0.1},
            {"days_per_month": 32}, {"days_per_month": 0},
            {"tariff_per_kwh": -1}, {"tariff_per_kwh": "NaN"},
            {"units": 0}, {"units": 1001},
            {"units": True}, {"days_per_month": True},
        ]
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with self.assertRaises(ValueError):
                    calculate_energy(**{**defaults, **overrides})

    def test_csv_formula_injection_is_neutralized(self):
        for name in ("=HYPERLINK(\"https://example.com\")", "+SUM(1,2)", " @SUM(1,2)", "\t=1+1"):
            with self.subTest(name=name):
                self.assertTrue(safe_spreadsheet_text(name).startswith("'"))
        self.assertEqual(safe_spreadsheet_text("Ventilador 60 W"), "Ventilador 60 W")


if __name__ == "__main__":
    unittest.main()
