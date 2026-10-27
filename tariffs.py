"""Official residential base tariff lookup; no guessed taxes or utility mapping."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import unicodedata

RESOURCE = 'fcf2906c-7c32-4b9b-a637-054e7a5234f4'
FLAG_RESOURCE = '0591b8f6-fe54-437b-b72b-1aa2efd46e42'
SOURCE = 'https://dadosabertos.aneel.gov.br/dataset/tarifas-distribuidoras-energia-eletrica'
API = 'https://dadosabertos.aneel.gov.br/api/3/action/datastore_search'


def identify_utility(city: str, state: str) -> dict | None:
    """Return only verified, unambiguous coverage; never guess from an IP.

    The ANEEL distribution map contains municipalities with multiple operators.
    Expand this mapping only with documented concession areas and tests.
    """
    normalized = ''.join(c for c in unicodedata.normalize('NFKD', state.casefold()) if not unicodedata.combining(c))
    normalized = normalized.strip()
    if normalized in {'distrito federal', 'federal district', 'df'}:
        return {
            'utility': 'Neoenergia Brasília',
            'confidence': 'alta',
            'basis': 'Área de concessão do Distrito Federal (antiga CEB-D).',
            'source': 'https://ri.neoenergia.com/a-companhia/perfil-corporativo-e-historico/',
        }
    return None


@dataclass(frozen=True)
class OfficialTariff:
    utility: str
    per_kwh: Decimal
    starts: date
    ends: date


def _get(params: dict, resource: str = RESOURCE) -> list[dict]:
    url = API + '?' + urlencode({'resource_id': resource, **params})
    with urlopen(Request(url, headers={'User-Agent': 'CustoClaro/1.0'}), timeout=15) as response:
        data = json.load(response)
    if not data.get('success'):
        raise ValueError('A consulta à ANEEL falhou.')
    return data['result']['records']


def search_distributors(query: str) -> list[str]:
    if len(query.strip()) < 3 or len(query) > 80:
        return []
    rows = _get({'q': query.strip(), 'limit': 200})
    return sorted({str(row['SigAgente']) for row in rows if row.get('SigAgente')}, key=str.casefold)


def parse_residential_tariff(rows: list[dict], utility: str, today: date) -> OfficialTariff | None:
    found = []
    for row in rows:
        try:
            if any(row.get(key) != value for key, value in {
                'SigAgente': utility,
                'DscBaseTarifaria': 'Base Econômica',
                'DscSubGrupo': 'B1',
                'DscModalidadeTarifaria': 'Convencional',
                'DscClasse': 'Residencial',
                'DscSubClasse': 'Residencial',
                'DscDetalhe': 'Não se aplica',
                'NomPostoTarifario': 'Não se aplica',
                'DscUnidadeTerciaria': 'MWh',
            }.items()):
                continue
            start, end = date.fromisoformat(row['DatInicioVigencia']), date.fromisoformat(row['DatFimVigencia'])
            te = Decimal(row['VlrTE'].replace('.', '').replace(',', '.'))
            tusd = Decimal(row['VlrTUSD'].replace('.', '').replace(',', '.'))
            if start <= today <= end and te >= 0 and tusd >= 0:
                found.append((start, (te + tusd) / 1000, end))
        except (ValueError, KeyError, TypeError, ArithmeticError):
            continue
    if not found:
        return None
    latest = max(start for start, _, _ in found)
    rates = {rate for start, rate, _ in found if start == latest}
    # Multiple conflicting tariffs for the same date mean the user must check the bill.
    if len(rates) != 1:
        return None
    start, rate, end = next((s, r, e) for s, r, e in found if s == latest)
    return OfficialTariff(utility, rate, start, end)


def lookup_residential_tariff(utility: str, today: date | None = None) -> OfficialTariff | None:
    fields = {'SigAgente': utility, 'DscSubGrupo': 'B1',
              'DscModalidadeTarifaria': 'Convencional', 'DscClasse': 'Residencial',
              'DscSubClasse': 'Residencial', 'DscDetalhe': 'Não se aplica',
              'DscBaseTarifaria': 'Base Econômica'}
    rows = _get({'filters': json.dumps(fields, ensure_ascii=False),
                 'sort': 'DatInicioVigencia desc', 'limit': 100})
    return parse_residential_tariff(rows, utility, today or date.today())


def current_flag(today: date | None = None) -> tuple[str, Decimal] | None:
    """ANEEL monthly flag, converted from R$/MWh into R$/kWh."""
    today = today or date.today()
    rows = _get({'sort': 'DatCompetencia desc', 'limit': 3}, FLAG_RESOURCE)
    for row in rows:
        if date.fromisoformat(row['DatCompetencia']) == today.replace(day=1):
            amount = Decimal(row['VlrAdicionalBandeira'].replace('.', '').replace(',', '.')) / 1000
            if 0 <= amount <= 1:
                return row['NomBandeiraAcionada'], amount
    return None


def reverse_location(latitude: float, longitude: float) -> tuple[str, str]:
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError('Coordenadas inválidas.')
    url = 'https://nominatim.openstreetmap.org/reverse?' + urlencode({
        'lat': round(latitude, 2), 'lon': round(longitude, 2),
        'format': 'jsonv2', 'zoom': 10, 'addressdetails': 1,
    })
    with urlopen(Request(url, headers={'User-Agent': 'CustoClaro/1.0 (https://github.com/fialho00/CustoClaro)'}), timeout=10) as response:
        address = json.load(response).get('address', {})
    return (address.get('city') or address.get('town') or address.get('municipality') or '',
            address.get('state') or '')
