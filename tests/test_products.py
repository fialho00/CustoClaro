"""Regression coverage for chat actions, grounded lookup and forecasts."""
import json
import unittest
from decimal import Decimal
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.index import app
from products import Product, comparable_products, monthly_product_kwh, parse_products, safe_https


client = TestClient(app)


class ProductToolsTests(unittest.TestCase):
    def test_research_parser_requires_source_and_no_guesses(self):
        raw = json.dumps({'products': [
            {'name': 'Geladeira Marca XYZ 400', 'watts': '100', 'price_brl': None,
             'source_url': 'https://fabricante.example/modelo'},
            {'name': 'Inexistente ABC', 'watts': 90, 'source_url': 'http://example.com'},
            {'name': 'Inseguro ABC', 'watts': -50, 'source_url': 'https://example.com'},
        ]})
        items = parse_products(raw)
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0].price_brl)
        self.assertEqual(items[0].watts, Decimal(100))
        self.assertEqual(safe_https('https://user:pass@example.com'), '')

    def test_label_consumption_does_not_scale_with_hours(self):
        product = Product(name='Modelo', watts=Decimal(300), label_kwh_month=Decimal(48))
        self.assertEqual(monthly_product_kwh(product, hours=1, days=30), Decimal(48))
        self.assertEqual(monthly_product_kwh(product, hours=24, days=10), Decimal(48))

    def test_comparator_unknown_price_does_not_pass_price_filter(self):
        items = [Product(name='Sem preço', watts=Decimal(90)),
                 Product(name='Com preço', watts=Decimal(120), price_brl=Decimal(2000))]
        result = comparable_products(items, max_price=3000, order='Preço de compra',
                                     hours=5, days=30, tariff=.9)
        self.assertEqual([item.name for item in result], ['Com preço'])

    def test_search_refuses_to_invent_products_without_api_key(self):
        with patch('api.index.configured_api_key', return_value=None):
            response = client.post('/api/products/discover', json={'query': 'geladeira frost free'})
        self.assertEqual(response.status_code, 503)

    def test_search_returns_candidates_with_sources(self):
        product = Product(name='Geladeira Marca ABC 400', watts=Decimal(120),
                          source_url='https://example.com/modelo')
        with patch('api.index.configured_api_key', return_value='test'), \
             patch('api.index.search_products', return_value=[product]) as search:
            response = client.post('/api/products/discover', json={'query': 'geladeira ABC 400'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['items'][0]['watts'], '120')
        search.assert_called_once()

    def test_monthly_forecast_is_deterministic(self):
        power = client.post('/api/products/forecast', json={
            'watts': '100', 'hours': 5, 'days': 30, 'tariff': '0.90'})
        self.assertEqual(power.status_code, 200)
        self.assertEqual(power.json()['monthly_kwh_label'], '15,00 kWh')
        self.assertEqual(power.json()['monthly_brl_label'], 'R$ 13,50')
        rated = client.post('/api/products/forecast', json={
            'watts': '100', 'label_kwh_month': '48', 'hours': 1, 'days': 30, 'tariff': '0.90'})
        self.assertEqual(rated.json()['monthly_brl_label'], 'R$ 43,20')
        self.assertEqual(rated.json()['method'], 'etiqueta_padronizada')
        self.assertEqual(client.post('/api/products/forecast', json={'watts': '0'}).status_code, 422)

    def test_chat_suggests_clickable_action(self):
        response = client.post('/api/chat', json={'question': 'Quanto uma geladeira consome?'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['action'], 'products')
        response = client.post('/api/chat', json={'question': 'Compare dois aparelhos'})
        self.assertEqual(response.json()['action'], 'compare')


if __name__ == '__main__':
    unittest.main()
