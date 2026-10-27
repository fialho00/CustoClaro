from datetime import date
from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
from tariffs import current_flag, parse_residential_tariff

class TariffTests(TestCase):
    def test_only_current_conventional_residential_base(self):
        row = {'SigAgente':'Neoenergia Brasília','DscBaseTarifaria':'Base Econômica',
               'DscSubGrupo':'B1','DscModalidadeTarifaria':'Convencional',
               'DscClasse':'Residencial','DscSubClasse':'Residencial',
               'DscDetalhe':'Não se aplica','NomPostoTarifario':'Não se aplica',
               'DscUnidadeTerciaria':'MWh','DatInicioVigencia':'2026-10-22',
               'DatFimVigencia':'2027-10-21','VlrTE':'356,52','VlrTUSD':'423,44'}
        other = dict(row,DscSubClasse='Baixa Renda',VlrTE='0,00')
        result = parse_residential_tariff([other,row], 'Neoenergia Brasília', date(2026,10,27))
        self.assertEqual(result.per_kwh, Decimal('0.77996'))
        self.assertIsNone(parse_residential_tariff([row], 'Neoenergia Brasília', date(2028,1,1)))
        conflict = dict(row,VlrTE='450,00')
        self.assertIsNone(parse_residential_tariff([row,conflict], 'Neoenergia Brasília', date(2026,10,27)))

    @patch('tariffs._get')
    def test_current_flag_only_same_month(self, get):
        get.return_value = [{'DatCompetencia':'2026-10-01','NomBandeiraAcionada':'Verde','VlrAdicionalBandeira':',00'}]
        self.assertEqual(current_flag(date(2026,10,27)), ('Verde', Decimal('0')))
        self.assertIsNone(current_flag(date(2026,11,1)))
