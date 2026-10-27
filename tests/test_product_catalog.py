"""Ensure catalog findings never pretend missing facts are known."""

import json
import unittest
from decimal import Decimal

from product_catalog import normalize_products


class ProductCatalogTests(unittest.TestCase):
    def test_uses_label_energy_without_multiplying_by_hours(self):
        content = json.dumps({'products': [
            {'name': 'Geladeira Modelo B', 'source_index': 1, 'label_kwh_month': 30,
             'watts': 100, 'price_brl': 2500, 'efficiency': 'A'},
        ]})
        result = normalize_products(content, ['https://example.com/item'], tariff=Decimal('.9'),
                                    hours_per_day=Decimal('8'), days=30)
        self.assertEqual(result[0]['monthly_kwh'], '30')
        self.assertEqual(result[0]['monthly_brl_label'], 'R$ 27,00')
        self.assertEqual(result[0]['calculation_basis'], 'etiqueta mensal')

    def test_watts_calculation_and_unknown_values(self):
        raw = json.dumps({'products': [
            {'name': 'Ventilador Modelo X', 'source_index': 1, 'watts': 50},
            {'name': 'Ventilador Modelo Y', 'source_index': 2, 'price_brl': 120},
        ]})
        rows = normalize_products(raw, ['https://example.com/one', 'https://example.com/two'],
                                  tariff=Decimal('1'), hours_per_day=Decimal('4'), days=30)
        self.assertEqual(Decimal(rows[0]['monthly_kwh']), Decimal('6'))
        self.assertEqual(rows[0]['monthly_brl_label'], 'R$ 6,00')
        self.assertIsNone(rows[1]['monthly_brl_label'])

    def test_rejects_unattributed_products_and_filters_unknown_prices(self):
        raw = json.dumps({'products': [
            {'name': 'Aparelho sem fonte', 'source_index': 5, 'price_brl': 100},
            {'name': 'Aparelho com fonte', 'source_index': 1, 'watts': 300},
        ]})
        rows = normalize_products(raw, ['https://example.com'], tariff=Decimal('.9'),
                                  hours_per_day=Decimal('1'), days=30, max_price=Decimal('300'))
        self.assertEqual(rows, [])

    def test_consumption_filter_excludes_missing_and_above_limit(self):
        raw = json.dumps({'products': [
            {'name': 'Produto Economico', 'source_index': 1, 'label_kwh_month': 12},
            {'name': 'Produto Gastador', 'source_index': 1, 'label_kwh_month': 100},
            {'name': 'Produto Sem Consumo', 'source_index': 1, 'price_brl': 300},
        ]})
        rows = normalize_products(raw, ['https://example.com'], tariff=Decimal('.9'),
                                  hours_per_day=Decimal(2), days=30,
                                  max_monthly_kwh=Decimal('25'))
        self.assertEqual([item['name'] for item in rows], ['Produto Economico'])


if __name__ == '__main__':
    unittest.main()
