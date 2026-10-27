"""User journeys for the photo-first estimator."""
import csv
import io
import unittest
from decimal import Decimal
from datetime import date
from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from core import calculate_energy
from vision import LabelReading
from tariffs import OfficialTariff
from app import csv_report, contextual_reply, household_report, household_reply

APP_PATH = str(Path(__file__).resolve().parents[1] / 'app.py')

class StreamlitAppTests(unittest.TestCase):
    def test_initial_and_manual_estimate(self):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
        self.assertFalse(app.exception)
        self.assertFalse(app.metric)
        watts = next(i for i in app.number_input if i.label == 'Potência (W)')
        watts.set_value(5500.0).run(timeout=30)
        self.assertFalse(app.exception)
        metrics = {m.label: m.value for m in app.metric}
        self.assertEqual(metrics['Custo estimado/mês'], 'R$ 24,75')

    def test_photo_requires_explicit_confirmation_even_after_edit(self):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
        app.session_state['reading'] = LabelReading('Chuveiro', Decimal(5500), '5500 W', 'alta', '', 'gemma-4-26b-a4b-it')
        app.session_state['watts'] = 5500.0
        app.run(timeout=30)
        self.assertFalse(app.metric)
        next(i for i in app.number_input if i.label == 'Potência (W)').set_value(6000.0).run(timeout=30)
        self.assertFalse(app.session_state['confirmed'])
        self.assertFalse(app.metric)
        next(b for b in app.button if b.label == 'Confirmar potência').click().run(timeout=30)
        self.assertTrue(app.session_state['confirmed'])
        self.assertTrue(app.metric)

    def test_contextual_chat_and_single_row_csv(self):
        estimate = calculate_energy(watts=5500, hours_per_day=Decimal(10)/60,
                                    days_per_month=30, tariff_per_kwh=0.90)
        self.assertIn('R$ 24,75', contextual_reply('e se usar 10 minutos?', estimate, 'Chuveiro'))
        report = csv_report('=HYPERLINK("x")', estimate).decode('utf-8-sig').splitlines()
        self.assertEqual(len(report), 3)
        rows = list(csv.reader(report[1:], delimiter=';'))
        self.assertEqual(len(rows[0]), len(rows[1]))
        self.assertTrue(rows[1][0].startswith("'"))

    def test_official_tariff_is_applied_and_recalculates(self):
        official = OfficialTariff('Neoenergia Brasília', Decimal('0.77996'),
                                 date(2026, 10, 22), date(2027, 10, 21))
        with patch('tariffs.search_distributors', return_value=['Neoenergia Brasília']), \
             patch('tariffs.lookup_residential_tariff', return_value=official), \
             patch('tariffs.current_flag', return_value=('Verde', Decimal('0'))):
            app = AppTest.from_file(APP_PATH).run(timeout=30)
            next(i for i in app.number_input if i.label == 'Potência (W)').set_value(5500.0).run(timeout=30)
            next(i for i in app.text_input if i.label == 'Distribuidora da sua conta').set_value('Neoenergia Brasília').run(timeout=30)
            next(b for b in app.button if b.label == 'Procurar tarifa oficial').click().run(timeout=30)
            next(b for b in app.button if b.label == 'Usar tarifa base da ANEEL').click().run(timeout=30)
            self.assertFalse(app.exception)
            self.assertEqual(app.session_state['tariff'], 0.77996)
            self.assertEqual(next(m.value for m in app.metric if m.label == 'Custo estimado/mês'), 'R$ 21,45')
            next(i for i in app.text_input if i.label == 'Distribuidora da sua conta').set_value('Outra').run(timeout=30)
            self.assertEqual(app.session_state['distributors'], [])

    def test_house_adds_appliances_and_exports_total(self):
        app = AppTest.from_file(APP_PATH).run(timeout=30)
        next(r for r in app.radio if r.label == 'O que você quer calcular?').set_value('🏠 Energia da casa').run(timeout=30)
        self.assertFalse(app.exception)
        next(i for i in app.number_input if i.label == 'Potência (W)').set_value(5500.0).run(timeout=30)
        next(i for i in app.text_input if i.label == 'Nome do aparelho').set_value('Chuveiro').run(timeout=30)
        next(b for b in app.button if b.label == '＋ Adicionar à minha casa').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['house']), 1)
        self.assertEqual(next(m.value for m in app.metric if m.label == 'Total estimado por mês'), 'R$ 24,75')
        next(i for i in app.number_input if i.label == 'Potência (W)').set_value(9.0).run(timeout=30)
        next(i for i in app.text_input if i.label == 'Nome do aparelho').set_value('Lâmpada').run(timeout=30)
        next(i for i in app.number_input if i.label == 'Quantos iguais?').set_value(2).run(timeout=30)
        next(b for b in app.button if b.label == '＋ Adicionar à minha casa').click().run(timeout=30)
        self.assertFalse(app.exception)
        self.assertEqual(len(app.session_state['house']), 2)
        self.assertEqual(next(m.value for m in app.metric if m.label == 'Total estimado por mês'), 'R$ 24,83')
        report = household_report(app.session_state['house'], app.session_state['tariff']).decode('utf-8-sig').splitlines()
        rows = list(csv.reader(report[1:], delimiter=';'))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[-1][0], 'TOTAL')
        self.assertEqual(rows[-1][-2], '24,83')
        estimates = [(item, calculate_energy(watts=item['watts'],
                      hours_per_day=Decimal(item['minutes']) / 60,
                      days_per_month=item['days'], tariff_per_kwh=0.90,
                      units=item['units'])) for item in app.session_state['house']]
        self.assertIn('Chuveiro', household_reply('qual consome mais?', estimates))
        next(b for b in app.button if b.label == '✕').click().run(timeout=30)
        self.assertEqual(len(app.session_state['house']), 1)
