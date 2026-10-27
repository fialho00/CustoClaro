import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from vision import answer_about_estimate, evidence_power_values, parse_label_response, read_label


class GemmaOutputTests(unittest.TestCase):
    def test_supported_json(self):
        result = parse_label_response(
            '{"appliance":"Ventilador","power_watts":60,'
            '"evidence":"POTÊNCIA: 60 W","confidence":"alta","notes":""}'
        )
        self.assertEqual(result.appliance, "Ventilador")
        self.assertEqual(result.power_watts, Decimal(60))
        self.assertEqual(result.evidence, "POTÊNCIA: 60 W")

    def test_markdown_fence_from_model(self):
        result = parse_label_response(
            '```json\n{"appliance":"A","power_watts":1200,'
            '"evidence":"1.2 kW","confidence":"média"}\n```'
        )
        self.assertEqual(result.power_watts, Decimal(1200))

    def test_unknown_power_stays_unknown(self):
        result = parse_label_response(
            '{"appliance":"Ferro","power_watts":null,'
            '"evidence":"127 V","confidence":"baixa","notes":"Sem watts"}'
        )
        self.assertIsNone(result.power_watts)

    def test_no_evidence_rejects_invented_wattage(self):
        result = parse_label_response(
            '{"appliance":"Ferro","power_watts":1500,'
            '"evidence":"","confidence":"alta"}'
        )
        self.assertIsNone(result.power_watts)
        self.assertEqual(result.confidence, "baixa")

    def test_evidence_must_contain_the_claimed_power(self):
        for misleading in ("127 V, 60 Hz", "60 kWh", "80 W", "60 W/h"):
            with self.subTest(evidence=misleading):
                result = parse_label_response(
                    '{"appliance":"Ventilador","power_watts":60,'
                    f'"evidence":"{misleading}","confidence":"alta"}}'
                )
                self.assertIsNone(result.power_watts)
                self.assertEqual(result.confidence, "baixa")

    def test_matching_power_evidence_accepts_kw_and_localized_numbers(self):
        self.assertIn(Decimal("1500"), evidence_power_values("Potência: 1,5 kW"))
        self.assertIn(Decimal("1200"), evidence_power_values("Entrada 1.200 W"))
        self.assertIn(Decimal("125"), evidence_power_values("0.125 kW"))
        result = parse_label_response(
            '{"appliance":"Aquecedor","power_watts":1500,'
            '"evidence":"Potência nominal: 1,5 kW","confidence":"alta"}'
        )
        self.assertEqual(result.power_watts, Decimal("1500"))

    def test_real_label_english_watts_and_equivalent_bulb_are_handled(self):
        reading = parse_label_response(
            '{"appliance":"Lâmpada","power_watts":10.5,'
            '"evidence":"Energy Used 10.5 watts","confidence":"alta"}'
        )
        self.assertEqual(reading.power_watts, Decimal("10.5"))
        self.assertIn(Decimal("1450"), evidence_power_values("Rated input 1.45 kilowatts"))
        self.assertIn(Decimal("900"), evidence_power_values("Potência 0,9 quilowatt"))
        self.assertNotIn(Decimal(60), evidence_power_values("60W equivalent"))
        self.assertNotIn(Decimal(60), evidence_power_values("equivalent to 60 watts"))
        self.assertIn(Decimal(9), evidence_power_values("Energy used 9W; 60W equivalent"))

        incorrect = parse_label_response(
            '{"appliance":"Lâmpada","power_watts":60,'
            '"evidence":"60W equivalent","confidence":"alta"}'
        )
        self.assertIsNone(incorrect.power_watts)

    def test_unexpected_or_unsafe_outputs(self):
        invalid = [
            "não sei", "", "[]", "null",
            '{"power_watts":-1,"evidence":"-1W"}',
            '{"power_watts":"NaN","evidence":"NaN W"}',
            '{"power_watts":true,"evidence":"W"}',
            '{"power_watts":1000001,"evidence":"1000001 W"}',
        ]
        for sample in invalid:
            with self.subTest(sample=sample):
                with self.assertRaises(ValueError):
                    parse_label_response(sample)

    def test_image_validation_before_api(self):
        with self.assertRaisesRegex(ValueError, "JPEG"):
            read_label(b"file", "application/pdf", api_key="fake")
        with self.assertRaisesRegex(ValueError, "8 MB"):
            read_label(b"", "image/jpeg", api_key="fake")

    def test_missing_api_key_is_explicit(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "", "GOOGLE_API_KEY": ""}):
            with self.assertRaisesRegex(ValueError, "GEMINI_API_KEY"):
                read_label(b"mock-image", "image/png")

    def test_model_and_image_are_sent_to_the_correct_api(self):
        with patch("google.genai.Client") as client:
            client.return_value.__enter__.return_value.models.generate_content.return_value.text = (
                '{"appliance":"Ventilador","power_watts":60,'
                '"evidence":"60 W","confidence":"alta"}'
            )
            result = read_label(b"test-image", "image/jpeg", api_key="key-for-test-only")
        self.assertEqual(result.power_watts, Decimal(60))
        self.assertEqual(result.model, "gemma-4-26b-a4b-it")
        arguments = client.return_value.__enter__.return_value.models.generate_content.call_args
        self.assertEqual(arguments.kwargs["model"], "gemma-4-26b-a4b-it")
        self.assertEqual(len(arguments.kwargs["contents"]), 2)
        self.assertEqual(arguments.kwargs["contents"][1].inline_data.data, b"test-image")
        client_args = client.call_args.kwargs
        self.assertEqual(client_args['http_options'].timeout, 12000)
        retry = client_args['http_options'].retry_options
        self.assertEqual(retry.attempts, 3)
        self.assertEqual(retry.http_status_codes, [500, 502, 503, 504])

    def test_contextual_chat_sends_only_current_question_and_numbers(self):
        with patch('google.genai.Client') as client:
            client.return_value.__enter__.return_value.models.generate_content.return_value.text = 'O custo varia com a tarifa.'
            answer = answer_about_estimate('Por que varia?', 'Custo mensal: R$ 20', api_key='test-only')
        self.assertEqual(answer, 'O custo varia com a tarifa.')
        args = client.return_value.__enter__.return_value.models.generate_content.call_args.kwargs
        self.assertIn('Custo mensal: R$ 20', args['contents'])
        self.assertIn('Por que varia?', args['contents'])
        self.assertEqual(args['model'], 'gemma-4-26b-a4b-it')
        with self.assertRaises(ValueError):
            answer_about_estimate('x' * 801, 'context', api_key='test-only')


if __name__ == "__main__":
    unittest.main()

