"""Contract and safety checks for the web UI's API."""

import io
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from api.index import app
from vision import LabelReading
from decimal import Decimal


client = TestClient(app)


class WebApiTests(unittest.TestCase):
    def test_health_does_not_reveal_the_api_key(self):
        with patch('api.index.configured_api_key', return_value='private-key'):
            response = client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'ai_available': True})

    def test_energy_is_calculated_by_python_core(self):
        response = client.post('/api/estimate', json={
            'name': 'Chuveiro', 'watts': 5500, 'minutes': 10,
            'days': 30, 'units': 1, 'tariff': 0.9,
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['monthly_brl_label'], 'R$ 24,75')
        self.assertEqual(response.json()['monthly_kwh_label'], '27,50 kWh')
        self.assertEqual(response.json()['annual_brl_label'], 'R$ 297,00')

    def test_house_total_uses_validated_items(self):
        response = client.post('/api/house', json=[
            {'name': 'Chuveiro', 'watts': 5500, 'minutes': 10, 'tariff': .9},
            {'name': 'Geladeira', 'watts': 120, 'minutes': 1440, 'tariff': .9},
            {'name': 'Ventilador', 'watts': 80, 'minutes': 480, 'tariff': .9},
        ])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_brl_label'], 'R$ 119,79')
        self.assertEqual(response.json()['total_kwh_label'], '133,10 kWh')

    def test_rejects_invalid_power_and_oversized_house(self):
        response = client.post('/api/estimate', json={'watts': -1})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(client.post('/api/house', json=[{'watts': 100}] * 31).status_code, 422)

    def test_chat_comparison_is_deterministic_without_model(self):
        response = client.post('/api/chat', json={
            'question': 'E se eu usar só 5 minutos?',
            'appliance': {'name': 'Chuveiro', 'watts': 5500, 'minutes': 10, 'tariff': .9},
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['source'], 'calculo')
        self.assertIn('R$ 12,38', response.json()['reply'])

    def test_chat_highest_cost_uses_the_house(self):
        response = client.post('/api/chat', json={
            'question': 'Qual aparelho mais pesa na conta?',
            'house': [
                {'name': 'Chuveiro', 'watts': 5500, 'minutes': 10, 'tariff': .9},
                {'name': 'Geladeira', 'watts': 120, 'minutes': 1440, 'tariff': .9},
            ],
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('Geladeira', response.json()['reply'])
        self.assertIn('R$ 77,76', response.json()['reply'])

    def test_nom_nom_refuses_topics_outside_electric_energy(self):
        for question in ('Quais são as raças de cachorros?', 'Conte uma piada', 'Qual time ganhou o futebol?'):
            with self.subTest(question=question):
                response = client.post('/api/chat', json={'question': question})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json()['source'], 'escopo')
                self.assertIn('Nom Nom', response.json()['reply'])

    def test_nom_nom_uses_grounded_product_comparison(self):
        response = client.post('/api/chat', json={
            'question': 'Qual produto é mais econômico?',
            'products': [
                {'name': 'Modelo A', 'monthly_kwh': '40', 'price_brl': '2300'},
                {'name': 'Modelo B', 'monthly_kwh': '25', 'price_brl': '2800'},
            ],
        })
        self.assertEqual(response.json()['source'], 'calculo')
        self.assertIn('Modelo B', response.json()['reply'])

    def test_product_search_checks_parameters_and_can_use_mock_sources(self):
        invalid = client.post('/api/products/search', json={'query': 'geladeira', 'hours_per_day': 26})
        self.assertEqual(invalid.status_code, 422)
        with patch('api.index.configured_api_key', return_value='test-only'), patch('api.index.search_appliances') as search:
            search.return_value = {'products': [], 'sources_found': 0, 'notice': 'Teste'}
            response = client.post('/api/products/search', json={
                'query': 'geladeira inverter', 'tariff': 0.8, 'hours_per_day': 3,
                'max_price': 3000, 'sort': 'price',
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(search.call_args.kwargs['query'] if 'query' in search.call_args.kwargs else search.call_args.args[0], 'geladeira inverter')
        self.assertEqual(search.call_args.kwargs['max_price'], Decimal('3000'))

    def test_upload_rejects_invalid_image_format(self):
        with patch('api.index.configured_api_key', return_value='test-only'):
            response = client.post('/api/analyze', files={'file': ('file.pdf', b'%PDF', 'application/pdf')})
        self.assertEqual(response.status_code, 415)

    def test_upload_sanitizes_and_passes_image_to_vision(self):
        image = Image.new('RGB', (50, 30), 'white')
        data = io.BytesIO()
        image.save(data, format='PNG')
        with patch('api.index.configured_api_key', return_value='test-only'), patch('api.index.read_label') as reader:
            reader.return_value = LabelReading('Lâmpada', Decimal(9), 'POTÊNCIA: 9 W', 'alta', '', 'test')
            response = client.post('/api/analyze', files={'file': ('etiqueta.png', data.getvalue(), 'image/png')})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['power_watts'], '9')
        self.assertEqual(reader.call_args.args[1], 'image/jpeg')
        self.assertIn('gemini-', reader.call_args.kwargs['model'])


if __name__ == '__main__':
    unittest.main()
