"""WattCola: photo-first, private-session energy estimate."""
from __future__ import annotations

import csv
from datetime import date
import hashlib
import io
import os
import re
from decimal import Decimal
from pathlib import Path

import streamlit as st
from PIL import Image, ImageOps, UnidentifiedImageError

from core import brl, calculate_energy, pt_number, safe_spreadsheet_text
from vision import MAX_UPLOAD_BYTES, LabelReading, read_label, configured_api_key, answer_about_estimate
from tariffs import SOURCE as TARIFF_SOURCE, current_flag, lookup_residential_tariff, reverse_location, search_distributors

st.set_page_config(page_title='WattCola', page_icon='⚡', layout='centered', initial_sidebar_state='collapsed')


def prepare_image(uploaded: object) -> tuple[bytes, str]:
    raw = uploaded.getvalue()  # type: ignore[attr-defined]
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError('A foto precisa ter até 8 MB.')
    try:
        with Image.open(io.BytesIO(raw)) as original:
            if original.width * original.height > 20_000_000:
                raise ValueError('Reduza a resolução da foto.')
            if original.format not in {'JPEG', 'PNG', 'WEBP'}:
                raise ValueError('Envie JPEG, PNG ou WebP.')
            image = ImageOps.exif_transpose(original).convert('RGB')
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            output = io.BytesIO()
            image.save(output, format='JPEG', quality=88, optimize=True)
            return output.getvalue(), 'image/jpeg'
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ValueError(f'Não consegui abrir a foto: {exc}') from exc


def csv_report(name: str, estimate: object, source: str = 'manual') -> bytes:
    """One row, stable headers, Excel-friendly UTF-8 and locale delimiter."""
    output = io.StringIO()
    output.write('sep=;\r\n')
    writer = csv.writer(output, delimiter=';', lineterminator='\r\n')
    writer.writerow(['Aparelho', 'Origem da potência', 'Potência (W)', 'Minutos por dia',
                     'Dias por mês', 'Tarifa (R$/kWh)', 'Consumo (kWh/mês)',
                     'Custo (R$/mês)', 'Custo (R$/ano)'])
    writer.writerow([safe_spreadsheet_text(name), safe_spreadsheet_text(source),
                     pt_number(estimate.watts), pt_number(estimate.hours_per_day * 60, 0),
                     estimate.days_per_month, pt_number(estimate.tariff_per_kwh, 5),
                     pt_number(estimate.monthly_kwh), pt_number(estimate.monthly_brl),
                     pt_number(estimate.annual_brl)])
    return ('\ufeff' + output.getvalue()).encode('utf-8')


def household_report(items: list[dict], tariff: float) -> bytes:
    """A row per appliance plus a total, without photos or credentials."""
    output = io.StringIO()
    output.write('sep=;\r\n')
    writer = csv.writer(output, delimiter=';', lineterminator='\r\n')
    writer.writerow(['Aparelho', 'Origem da potência', 'Potência (W)', 'Minutos por dia',
                     'Dias por mês', 'Unidades', 'Tarifa (R$/kWh)',
                     'Consumo (kWh/mês)', 'Custo (R$/mês)', 'Custo (R$/ano)'])
    total_kwh = total_month = total_year = Decimal(0)
    for item in items:
        result = calculate_energy(watts=item['watts'], hours_per_day=Decimal(item['minutes']) / 60,
                                  days_per_month=item['days'], tariff_per_kwh=tariff,
                                  units=item['units'])
        writer.writerow([safe_spreadsheet_text(item['name']), safe_spreadsheet_text(item['source']),
                         pt_number(result.watts), item['minutes'], item['days'], item['units'],
                         pt_number(tariff, 5), pt_number(result.monthly_kwh),
                         pt_number(result.monthly_brl), pt_number(result.annual_brl)])
        total_kwh += result.monthly_kwh
        total_month += result.monthly_brl
        total_year += result.annual_brl
    writer.writerow(['TOTAL', '', '', '', '', '', '', pt_number(total_kwh),
                     pt_number(total_month), pt_number(total_year)])
    return ('\ufeff' + output.getvalue()).encode('utf-8')


def contextual_reply(question: str, estimate: object | None, name: str) -> str:
    """Constrained assistant: interprets usage questions, never invents rates or wattage."""
    if estimate is None:
        return 'Primeiro envie uma foto com a potência em W ou informe os watts manualmente.'
    q = question.casefold()
    if any(word in q for word in ('tarifa', 'preço do kwh', 'preco do kwh')):
        return f'Estou usando R$ {pt_number(estimate.tariff_per_kwh, 5)}/kWh. Abra “Ajustar tarifa e dias” para usar a tarifa da sua conta.'
    match = re.search(r'(\d+(?:[.,]\d+)?)\s*(minutos?|min|horas?|h)\b', q)
    if match:
        amount = Decimal(match.group(1).replace(',', '.'))
        hours = amount / 60 if match.group(2).startswith('min') else amount
        if hours < 0 or hours > 24:
            return 'Use um tempo entre 0 e 24 horas por dia.'
        alt = calculate_energy(watts=estimate.watts, hours_per_day=hours,
                               days_per_month=estimate.days_per_month,
                               tariff_per_kwh=estimate.tariff_per_kwh, units=1)
        difference = estimate.monthly_brl - alt.monthly_brl
        comparison = (f' Economia de {brl(difference)}/mês em relação ao tempo atual.'
                      if difference > 0 else
                      f' Acréscimo de {brl(-difference)}/mês em relação ao tempo atual.'
                      if difference < 0 else '')
        return (f'Com {pt_number(hours * 60, 0)} minutos por dia, {name} consumiria '
                f'{pt_number(alt.monthly_kwh)} kWh/mês e custaria cerca de {brl(alt.monthly_brl)}/mês '
                f'({estimate.days_per_month} dias).{comparison}')
    if any(word in q for word in ('ano', 'anual', '12 meses')):
        return f'Em 12 meses iguais: {brl(estimate.annual_brl)}. A estimativa não prevê mudanças na tarifa ou no uso.'
    if any(word in q for word in ('como', 'conta', 'calcula', 'fórmula', 'formula')):
        return (f'{pt_number(estimate.watts)} W ÷ 1.000 × {pt_number(estimate.hours_per_day * 60, 0)} min ÷ 60 '
                f'× {estimate.days_per_month} dias = {pt_number(estimate.monthly_kwh)} kWh/mês. '
                f'Multiplicando pela tarifa: {brl(estimate.monthly_brl)}/mês.')
    return (f'{name}: {pt_number(estimate.monthly_kwh)} kWh e {brl(estimate.monthly_brl)} por mês. '
            'Pergunte, por exemplo: “e se eu usar 10 minutos?”, “qual o custo anual?” ou “como calcula?”.')


def household_reply(question: str, rows: list[tuple]) -> str:
    """Answer common home questions using only calculated numbers."""
    if not rows:
        return 'Adicione um aparelho para analisar sua casa.'
    total = sum((result.monthly_brl for _, result in rows), Decimal(0))
    total_kwh = sum((result.monthly_kwh for _, result in rows), Decimal(0))
    top_item, top_result = max(rows, key=lambda pair: pair[1].monthly_kwh)
    if any(word in question.casefold() for word in ('mais', 'maior', 'gasta', 'consome', 'prioridade')):
        return (f"Entre os itens adicionados, {top_item['name']} tem o maior consumo estimado: "
                f'{pt_number(top_result.monthly_kwh)} kWh/mês, cerca de {brl(top_result.monthly_brl)}/mês.')
    return (f'Os {len(rows)} aparelhos somam cerca de {pt_number(total_kwh)} kWh/mês '
            f'e {brl(total)}/mês. Pergunte “qual consome mais?” para ver por onde começar.')


for key, default in {'dark': False, 'watts': 0.0, 'minutes': 10, 'days': 30, 'units': 1,
                     'tariff': 0.90, 'name': 'Aparelho', 'reading': None,
                     'fingerprint': None, 'confirmed': False, 'source': 'manual',
                     'chat': [], 'location_label': None, 'distributors': [],
                     'tariff_source': 'exemplo', 'house': [], 'house_chat': [], 'photo_version': 0,
                     'initial_consumed': False}.items():
    st.session_state.setdefault(key, default)


def power_changed() -> None:
    if st.session_state.reading is not None:
        st.session_state.confirmed = False
        st.session_state.source = 'foto + ajuste manual'


def tariff_changed() -> None:
    st.session_state.tariff_source = 'informada por você'
    st.session_state.house_chat = []


def distributor_changed() -> None:
    st.session_state.distributors = []


def add_to_house() -> None:
    """Widget callbacks run before rendering, so the next photo can start cleanly."""
    if st.session_state.watts <= 0 or (st.session_state.reading and not st.session_state.confirmed):
        return
    st.session_state.house = [*st.session_state.house, {
        'name': st.session_state.name.strip() or 'Aparelho',
        'watts': st.session_state.watts, 'minutes': st.session_state.minutes,
        'days': st.session_state.days, 'units': st.session_state.units,
        'source': st.session_state.source,
    }]
    st.session_state.house_chat = []
    st.session_state.watts = 0.0
    st.session_state.name = 'Aparelho'
    st.session_state.units = 1
    st.session_state.reading = None
    st.session_state.confirmed = False
    st.session_state.fingerprint = None
    st.session_state.source = 'manual'
    st.session_state.photo_version += 1
    st.session_state.initial_consumed = True
    st.session_state.chat = []

# Deliberately do not persist keys, photos, conversation or calculations to disk.
background = '#0b171b' if st.session_state.dark else '#f6f8f5'
foreground = '#edf8f4' if st.session_state.dark else '#132e2c'
card = '#182d30' if st.session_state.dark else '#ffffff'
st.markdown(f'''<style>
.stApp {{background:radial-gradient(circle at 80% 0%,#52c9a018,transparent 35%),{background};color:{foreground}}}
.block-container {{max-width:760px;padding-top:1rem;padding-bottom:4rem}}
header[data-testid="stHeader"], #MainMenu, footer {{visibility:hidden}}
.hero {{position:relative;overflow:hidden;background:linear-gradient(125deg,#06483f 0%,#0e806b 58%,#1cb48b 100%);color:white;padding:2rem 2.2rem;border-radius:28px;margin:.5rem 0 1.2rem;box-shadow:0 20px 50px #073a2e30;animation:arrive .55s ease-out both}}
.hero:after {{content:'✦';position:absolute;right:1.5rem;top:0;font-size:9rem;color:#eaffd31c;line-height:1;animation:float 5s ease-in-out infinite;pointer-events:none}}
.hero .eyebrow {{font-size:.82rem;font-weight:700;letter-spacing:.14em;text-transform:uppercase;color:#bff6d7}}
.hero h1 {{color:white;margin:.25rem 0 .4rem;font-size:2.75rem;letter-spacing:-.055em;line-height:1.08;max-width:580px}}
.hero p {{margin:0;color:#e3fff5;font-size:1.05rem;max-width:540px}}
.hero .steps {{display:inline-block;margin-top:1.2rem;padding:.42rem .8rem;background:#ffffff20;border:1px solid #ffffff38;border-radius:100px;font-size:.85rem}}
.hint {{padding:.85rem 1rem;background:{card};border:1px solid #5f8e8538;border-radius:15px;margin:.4rem 0 1rem;line-height:1.5}}
[data-testid="stMetric"] {{background:{card};border:1px solid #5f8e8555;border-radius:18px;padding:1rem;box-shadow:0 8px 24px #092d2410;animation:arrive .4s ease-out both}}
div.stButton > button, div.stDownloadButton > button {{min-height:3.1rem;border-radius:14px;transition:transform .18s ease,box-shadow .18s ease}}
div.stButton > button:hover, div.stDownloadButton > button:hover {{transform:translateY(-2px);box-shadow:0 8px 22px #0b514326}}
[data-testid="stFileUploader"], [data-testid="stCameraInput"] {{border-radius:18px;overflow:hidden}}
[data-testid="stRadio"] label {{transition:transform .18s ease}}
[data-testid="stRadio"] label:hover {{transform:translateY(-2px)}}
@keyframes arrive {{from {{opacity:0;transform:translateY(12px)}} to {{opacity:1;transform:translateY(0)}}}}
@keyframes float {{50% {{transform:translateY(9px) rotate(7deg)}}}}
@media(prefers-reduced-motion:reduce) {{*,*:before,*:after {{animation:none !important;transition:none !important}}}}
@media(max-width:600px) {{.block-container {{padding:.5rem .9rem 4rem}} .hero {{padding:1.5rem 1.25rem;border-radius:22px}} .hero h1 {{font-size:2rem}} .hero:after {{font-size:6rem;right:-.3rem}} h3 {{font-size:1.25rem !important}}}}
{'''[data-testid="stAppViewContainer"] input, [data-testid="stAppViewContainer"] textarea {
background:#22383b !important;color:#f2faf8 !important;}
[data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] p {
color:#e5f3f0 !important;}''' if st.session_state.dark else ''}
</style>''', unsafe_allow_html=True)

if st.button('☾ Escuro' if not st.session_state.dark else '☀ Claro',
             help='Alternar aparência'):
    st.session_state.dark = not st.session_state.dark
    st.rerun()
st.markdown('''<div class="hero"><span class="eyebrow">WattCola · leitura com IA</span>
<h1>Da etiqueta ao custo, em poucos toques.</h1>
<p>Fotografe a potência do aparelho, confira a leitura da IA e descubra quanto ele pode gastar.</p>
<span class="steps">1 · Foto &nbsp; → &nbsp; 2 · Conferir &nbsp; → &nbsp; 3 · Calcular</span></div>''', unsafe_allow_html=True)

mode = st.radio('O que você quer calcular?', ['📷 Um aparelho', '🏠 Energia da casa'],
                horizontal=True, key='mode')
if mode == '🏠 Energia da casa':
    st.caption('Adicione um aparelho por vez. A soma aparece logo abaixo e fica apenas nesta sessão.')
st.subheader('1. Fotografe a etiqueta')
st.markdown('<div class="hint">Aponte para a <strong>placa de dados elétricos</strong> do aparelho: '
            'lateral, parte de trás ou embaixo. Deixe visível o número seguido de <strong>W</strong> '
            'ou <strong>kW</strong>. Uma foto só do código de barras não informa a potência.</div>',
            unsafe_allow_html=True)
source = st.radio('Como enviar a foto?', ['📸 Tirar foto agora', '🖼️ Escolher foto'],
                  horizontal=True, index=1 if (os.getenv('WATTCOLA_INITIAL_IMAGE') or os.getenv('CUSTOCLARO_INITIAL_IMAGE')) else 0)
if source == '📸 Tirar foto agora':
    uploaded = st.camera_input('Abrir câmera', key=f'camera_{st.session_state.photo_version}')
else:
    uploaded = st.file_uploader('Escolher imagem da etiqueta', type=['jpg', 'jpeg', 'png', 'webp'],
                                key=f'photo_{st.session_state.photo_version}')
initial_path = os.getenv('WATTCOLA_INITIAL_IMAGE') or os.getenv('CUSTOCLARO_INITIAL_IMAGE')
if uploaded is None and source == '🖼️ Escolher foto' and initial_path and not st.session_state.initial_consumed:
    if st.checkbox('Usar foto escolhida no iniciador', value=True):
        try:
            file = Path(initial_path)
            if file.stat().st_size > MAX_UPLOAD_BYTES:
                raise ValueError('Foto maior que 8 MB.')
            uploaded = io.BytesIO(file.read_bytes())
        except (OSError, ValueError):
            st.error('Não foi possível abrir a foto. Escolha outra acima.')
image_data = None
if uploaded is not None:
    try:
        image_data = prepare_image(uploaded)
        st.image(image_data[0], caption='Foto selecionada', use_container_width=True)
    except ValueError as exc:
        st.error(str(exc))
fingerprint = hashlib.sha256(image_data[0]).hexdigest() if image_data else None
if fingerprint != st.session_state.fingerprint:
    st.session_state.fingerprint = fingerprint
    st.session_state.reading = None
    st.session_state.confirmed = False
    st.session_state.source = 'manual'
    st.session_state.watts = 0.0
    st.session_state.name = 'Aparelho'
    st.session_state.chat = []

api_key = configured_api_key()
with st.expander('🔑 Chave para ler com IA', expanded=bool(image_data and not api_key)):
    user_key = st.text_input('Gemini API Key', type='password', help='Fica apenas nesta sessão e não aparece no CSV.')
    if user_key:
        from launcher import normalize_key
        try:
            api_key = normalize_key(user_key)
            st.success('Chave recebida. A conexão será testada ao analisar a foto.')
        except ValueError as exc:
            api_key = None
            st.error(str(exc))
    st.caption('A foto só é enviada ao Google quando você pede a leitura.')

if image_data is not None and not api_key:
    st.info('Para ler a foto, abra “Chave para ler com IA”. Você também pode digitar os watts abaixo.')

if image_data is not None and api_key and st.button('✨ Ler etiqueta com IA', type='primary', use_container_width=True):
    try:
        with st.spinner('Lendo a potência...'):
            result = read_label(*image_data, api_key=api_key)
        st.session_state.reading = result
        st.session_state.watts = float(result.power_watts or 0)
        st.session_state.name = result.appliance
        st.session_state.confirmed = False
        st.session_state.source = 'foto + IA'
        if result.power_watts is None:
            st.warning('Não encontrei uma potência confiável. Confira a foto ou digite os watts abaixo.')
        else:
            st.success(f'Potência encontrada: {pt_number(result.power_watts, 0)} W. Confira antes de calcular.')
    except Exception as exc:
        code = getattr(exc, 'code', None) or getattr(exc, 'status_code', None)
        if code in (400, 401, 403):
            st.error('Chave rejeitada ou modelo indisponível para esta chave. Confira no Google AI Studio.')
        elif code == 429:
            st.error('Limite de uso da API atingido. Tente mais tarde.')
        elif code in (500, 502, 503, 504):
            st.error('A API está temporariamente indisponível. Tente novamente.')
        else:
            st.error('Não consegui ler esta foto. Confira a conexão, a chave e tente outra imagem.')

if st.session_state.reading:
    reading: LabelReading = st.session_state.reading
    if reading.evidence:
        st.info(f'Na etiqueta: “{reading.evidence}”')
    if reading.notes:
        st.caption(reading.notes)

if st.session_state.reading:
    st.subheader('2. Confira a leitura da IA')
    st.number_input('Potência (W)', min_value=0.0, max_value=1_000_000.0, step=10.0,
                    key='watts', on_change=power_changed)
else:
    with st.expander('Não conseguiu ler a foto? Informe os watts', expanded=False):
        st.number_input('Potência (W)', min_value=0.0, max_value=1_000_000.0, step=10.0,
                        key='watts', on_change=power_changed)

if st.session_state.watts > 0:
    if mode == '🏠 Energia da casa':
        st.text_input('Nome do aparelho', key='name')
    st.number_input('Minutos de uso por dia', min_value=0, max_value=1440, step=5, key='minutes')
    if mode == '🏠 Energia da casa':
        st.number_input('Quantos iguais?', min_value=1, max_value=1000, step=1, key='units')
    with st.expander('Ajustar tarifa e dias', expanded=False):
        st.write('**Tarifa da sua região**')
        st.caption('Localização apenas com sua permissão. Coordenadas aproximadas são consultadas no OpenStreetMap; confirme a distribuidora da sua conta.')
        from streamlit_geolocation import streamlit_geolocation
        location = streamlit_geolocation()
        if isinstance(location, dict) and location.get('latitude') is not None and not st.session_state.location_label:
            try:
                city, state = reverse_location(float(location['latitude']), float(location['longitude']))
                st.session_state.location_label = f'{city}, {state}'.strip(', ')
            except (ValueError, OSError):
                st.warning('Não consegui identificar a região. Você pode procurar sua distribuidora abaixo.')
        if st.session_state.location_label:
            st.caption(f'Região aproximada: {st.session_state.location_label}. A localização não identifica sua distribuidora.')
        st.caption('Geocodificação: © OpenStreetMap contributors.')
        utility_query = st.text_input('Distribuidora da sua conta', placeholder='Ex.: Neoenergia Brasília',
                                      on_change=distributor_changed)
        if st.button('Procurar tarifa oficial', disabled=len(utility_query.strip()) < 3):
            try:
                st.session_state.distributors = search_distributors(utility_query)
            except (OSError, ValueError):
                st.warning('Consulta indisponível. Informe a tarifa da sua conta abaixo.')
        if st.session_state.distributors:
            utility = st.selectbox('Confirme a distribuidora', st.session_state.distributors)
            if st.button('Usar tarifa base da ANEEL'):
                try:
                    official = lookup_residential_tariff(utility, date.today())
                    if official:
                        try:
                            flag = current_flag(date.today())
                        except (OSError, ValueError, KeyError):
                            flag = None
                        extra = flag[1] if flag else Decimal(0)
                        st.session_state.tariff = float(official.per_kwh + extra)
                        st.session_state.house_chat = []
                        flag_label = f' · bandeira {flag[0]}' if flag else ' · bandeira não confirmada'
                        st.session_state.tariff_source = f'ANEEL · {utility}{flag_label} · vigente até {official.ends:%d/%m/%Y}'
                        st.success(f'Tarifa base: R$ {pt_number(official.per_kwh, 3)}/kWh'
                                   + (f' + bandeira {flag[0]}: R$ {pt_number(extra, 3)}/kWh.' if flag else '. Bandeira não confirmada.')
                                   + ' Tributos e iluminação pública não incluídos.')
                    else:
                        st.warning('Não encontrei uma tarifa residencial única e vigente. Use sua conta como referência.')
                except (OSError, ValueError):
                    st.warning('ANEEL indisponível agora. Digite a tarifa da sua conta.')
        st.number_input('Dias de uso no mês', min_value=1, max_value=31, step=1, key='days')
        official_rate = st.session_state.tariff_source.startswith('ANEEL')
        st.number_input('Tarifa (R$/kWh)', min_value=0.0, max_value=1000.0,
                        step=0.00001 if official_rate else 0.05,
                        format='%.5f' if official_rate else '%.2f',
                        key='tariff', on_change=tariff_changed)
        st.caption(f'Fonte: {st.session_state.tariff_source}. Tributos e iluminação pública não incluídos; '
                   f'a bandeira só entra se estiver indicada na fonte. '
                   f'Em sistemas isolados, a bandeira pode não se aplicar. '
                   f'[Dados oficiais]({TARIFF_SOURCE}).')

if st.session_state.watts > 0 and st.session_state.reading and not st.session_state.confirmed:
    if st.button('Confirmar potência', type='primary', use_container_width=True):
        st.session_state.confirmed = True
        st.rerun()

estimate = None
if st.session_state.watts > 0 and (not st.session_state.reading or st.session_state.confirmed):
    estimate = calculate_energy(watts=st.session_state.watts,
                                hours_per_day=Decimal(st.session_state.minutes) / 60,
                                days_per_month=st.session_state.days,
                                tariff_per_kwh=st.session_state.tariff,
                                units=st.session_state.units if mode == '🏠 Energia da casa' else 1)
    st.subheader('3. Veja o resultado')
    st.metric('Este aparelho por mês' if mode == '🏠 Energia da casa' else 'Custo estimado/mês',
              brl(estimate.monthly_brl))
    st.write(f'**{pt_number(estimate.monthly_kwh)} kWh/mês** · **{brl(estimate.annual_brl)} em 12 meses**')
    st.write(f'Cada dia de uso custa cerca de **{brl(estimate.monthly_brl / st.session_state.days)}**.')
    with st.expander('Como chegamos a esse valor?'):
        st.write(f'{pt_number(estimate.watts, 0)} W × {st.session_state.minutes} min/dia × '
                 f'{st.session_state.days} dias × {estimate.units} unidade(s) × '
                 f'R$ {pt_number(estimate.tariff_per_kwh, 5)}/kWh ÷ 60.000.')
        st.caption('Estimativa, não medição. Aparelhos com potência variável podem consumir diferente.')
    if mode == '🏠 Energia da casa':
        st.button('＋ Adicionar à minha casa', type='primary', use_container_width=True,
                  on_click=add_to_house)
    else:
        st.download_button('Baixar resultado (CSV)',
                           data=csv_report(st.session_state.name, estimate, st.session_state.source),
                           file_name='wattcola_resultado.csv', mime='text/csv', use_container_width=True)
elif st.session_state.reading and not st.session_state.confirmed:
    st.info('Confira e confirme a potência para ver o custo.')

if mode == '🏠 Energia da casa':
    st.subheader('Minha casa')
    if st.session_state.house:
        if st.session_state.watts <= 0:
            with st.expander('Ajustar tarifa da casa'):
                st.number_input('Tarifa (R$/kWh)', min_value=0.0, max_value=1000.0,
                                step=0.05, key='tariff', on_change=tariff_changed)
                st.caption('Use o valor da sua conta. Tributos e iluminação pública podem não estar incluídos.')
        house_rows = []
        for item in st.session_state.house:
            house_rows.append((item, calculate_energy(
                watts=item['watts'], hours_per_day=Decimal(item['minutes']) / 60,
                days_per_month=item['days'], tariff_per_kwh=st.session_state.tariff,
                units=item['units'])))
        st.metric('Total estimado por mês', brl(sum((result.monthly_brl for _, result in house_rows), Decimal(0))))
        st.caption(f'{pt_number(sum((result.monthly_kwh for _, result in house_rows), Decimal(0)))} kWh/mês '
                   f'· {len(house_rows)} aparelho(s) · tarifa R$ {pt_number(st.session_state.tariff, 5)}/kWh')
        for index, (item, result) in enumerate(house_rows):
            left, right = st.columns([4, 1])
            left.write(f"**{item['name']}** · {item['units']} × {pt_number(item['watts'], 0)} W "
                       f"· {item['minutes']} min/dia · **{brl(result.monthly_brl)}/mês**")
            if right.button('✕', key=f'remove_{index}', help=f"Remover {item['name']}"):
                st.session_state.house = [row for i, row in enumerate(st.session_state.house) if i != index]
                st.session_state.house_chat = []
                st.rerun()
        st.download_button('Baixar cálculo da casa (CSV)',
                           data=household_report(st.session_state.house, st.session_state.tariff),
                           file_name='wattcola_casa.csv', mime='text/csv', use_container_width=True)
        st.caption('Total aproximado dos aparelhos adicionados; a conta real pode incluir outros consumos, impostos e taxas.')
        st.subheader('✨ Pergunte à IA sobre sua casa')
        st.caption('Ex.: “qual consome mais?” ou “como reduzir o consumo?”')
        for role, message in st.session_state.house_chat[-6:]:
            with st.chat_message(role):
                st.write(message)
        if question := st.chat_input('Pergunte sobre os aparelhos da casa'):
            local = household_reply(question, house_rows)
            if api_key and not any(word in question.casefold() for word in
                                   ('mais', 'maior', 'gasta', 'consome', 'prioridade', 'total')):
                context = (f'Total da casa: {brl(sum((result.monthly_brl for _, result in house_rows), Decimal(0)))}/mês; '
                           f'{len(house_rows)} itens. Maiores consumos: ' + '; '.join(
                    f"{item['name']}: {pt_number(result.monthly_kwh)} kWh/mês, "
                    f'{brl(result.monthly_brl)}/mês' for item, result in
                    sorted(house_rows, key=lambda pair: pair[1].monthly_kwh, reverse=True)[:10]))
                try:
                    with st.spinner('Analisando sua casa...'):
                        answer = answer_about_estimate(question, context, api_key=api_key)
                except Exception:
                    answer = local
                    st.caption('IA indisponível agora. Resposta baseada nos cálculos locais.')
            else:
                answer = local
            st.session_state.house_chat = (st.session_state.house_chat +
                                           [('user', question), ('assistant', answer)])[-6:]
            with st.chat_message('user'):
                st.write(question)
            with st.chat_message('assistant'):
                st.write(answer)
    else:
        st.caption('Sua lista está vazia. Leia uma etiqueta ou informe os watts e toque em “Adicionar à minha casa”.')

if estimate is not None and mode == '📷 Um aparelho':
    st.subheader('Pergunte sobre esta conta')
    st.caption('Pergunte “e se usar 5 minutos?” ou “por que o valor é uma estimativa?”.')
    if api_key:
        st.caption('Perguntas abertas enviam a pergunta e os números desta simulação à API do Google. Comparações de minutos são calculadas aqui.')
    for role, message in st.session_state.chat[-6:]:
        with st.chat_message(role):
            st.write(message)
    if question := st.chat_input('Pergunte sobre o custo deste aparelho'):
        numeric_question = bool(re.search(r'\d+(?:[.,]\d+)?\s*(?:minutos?|min|horas?|h)\b', question.casefold()))
        if numeric_question or not api_key:
            answer = contextual_reply(question, estimate, st.session_state.name)
        else:
            context = (f'Aparelho: {st.session_state.name}; potência: {pt_number(estimate.watts)} W; '
                       f'uso: {st.session_state.minutes} minutos/dia; dias: {st.session_state.days}; '
                       f'tarifa: R$ {pt_number(estimate.tariff_per_kwh, 5)}/kWh; '
                       f'energia mensal: {pt_number(estimate.monthly_kwh)} kWh; '
                       f'custo mensal: {brl(estimate.monthly_brl)}; '
                       f'12 meses iguais: {brl(estimate.annual_brl)}.')
            try:
                with st.spinner('Respondendo sobre sua conta...'):
                    answer = answer_about_estimate(question, context, api_key=api_key)
            except Exception:
                answer = contextual_reply(question, estimate, st.session_state.name)
                st.caption('IA indisponível agora. Resposta baseada apenas nos cálculos locais.')
        st.session_state.chat = (st.session_state.chat + [('user', question), ('assistant', answer)])[-6:]
        with st.chat_message('user'):
            st.write(question)
        with st.chat_message('assistant'):
            st.write(answer)
