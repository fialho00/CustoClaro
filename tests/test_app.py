"""Streamlit smoke tests using a simulated UI session."""

import unittest
from pathlib import Path
from decimal import Decimal

from streamlit.testing.v1 import AppTest
from vision import LabelReading

APP_PATH = str(Path(__file__).resolve().parents[1] / "app.py")


class StreamlitAppTests(unittest.TestCase):
    def test_initial_screen_loads_without_exception(self):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any("<h1>CustoClaro</h1>" in item.value for item in app.markdown))

    def test_example_produces_expected_metrics(self):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
        example_button = next(
            button for button in app.button if button.label == "Carregar ventilador de exemplo"
        )
        example_button.click().run(timeout=30)
        self.assertFalse(app.exception)
        metrics = {metric.label: metric.value for metric in app.metric}
        self.assertEqual(metrics["Consumo mensal"], "14,40 kWh")
        self.assertEqual(metrics["Custo mensal estimado"], "R$ 12,96")
        self.assertEqual(metrics["Custo em 12 meses iguais"], "R$ 155,52")

    def test_ai_extraction_requires_explicit_confirmation(self):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
        app.session_state["label_reading"] = LabelReading(
            appliance="Ventilador", power_watts=Decimal(60), evidence="60 W",
            confidence="alta", notes="", model="gemma-4-26b-a4b-it",
        )
        app.session_state["device_name"] = "Ventilador"
        app.session_state["watts_field"] = 60.0
        app.session_state["power_confirmed"] = False
        app.session_state["source_kind"] = "Gemma 4 — pendente de revisão humana"
        app.run(timeout=30)
        self.assertFalse(app.exception)
        self.assertFalse(any(metric.label == "Consumo mensal" for metric in app.metric))
        confirm = next(button for button in app.button if button.label == "✓ Confirmar potência e calcular")
        confirm.click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any(metric.label == "Consumo mensal" for metric in app.metric))

    def test_manual_correction_still_requires_confirmation(self):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
        app.session_state["label_reading"] = LabelReading(
            appliance="Ventilador", power_watts=Decimal(60), evidence="60 W",
            confidence="alta", notes="", model="gemma-4-26b-a4b-it",
        )
        app.session_state["watts_field"] = 60.0
        app.session_state["power_confirmed"] = False
        app.run(timeout=30)
        power_input = next(field for field in app.number_input if field.label == "Potência nominal (W)")
        power_input.set_value(75.0).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertFalse(app.session_state["power_confirmed"])
        self.assertIn("manualmente", app.session_state["source_kind"])
        self.assertFalse(any(metric.label == "Consumo mensal" for metric in app.metric))
        confirm = next(button for button in app.button if button.label == "✓ Confirmar potência e calcular")
        confirm.click().run(timeout=30)
        self.assertTrue(app.session_state["power_confirmed"])
        self.assertIn("manualmente", app.session_state["source_kind"])
        self.assertTrue(any(metric.label == "Consumo mensal" for metric in app.metric))

    def test_fractional_daily_usage_keeps_slider_valid(self):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
        example = next(button for button in app.button if button.label == "Carregar ventilador de exemplo")
        example.click().run(timeout=30)
        hours_input = next(field for field in app.number_input if field.label == "Horas de uso por dia")
        hours_input.set_value(2.5).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertTrue(any(metric.label == "Consumo mensal" for metric in app.metric))


if __name__ == "__main__":
    unittest.main()

