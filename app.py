"""CustoClaro: photo-first, private-session energy estimate."""
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

st.set_page_config(page_title='CustoClaro', page_icon='⚡', layout='centered', initial_sidebar_state='collapsed')


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


for key, default in {'dark': False, 'watts': 0.0, 'minutes': 10, 'days': 30,
                     'tariff': 0.90, 'name': 'Aparelho', 'reading': None,
                     'fingerprint': None, 'confirmed': False, 'source': 'manual',
                     'chat': [], 'location_label': None, 'distributors': [],
                     'tariff_source': 'exemplo'}.items():
    st.session_state.setdefault(key, default)


def power_changed() -> None:
    if st.session_state.reading is not None:
        st.session_state.confirmed = False
        st.session_state.source = 'foto + ajuste manual'


def tariff_changed() -> None:
    st.session_state.tariff_source = 'informada por você'


def distributor_changed() -> None:
    st.session_state.distributors = []

# Deliberately do not persist keys, photos, conversation or calculations to disk.
background = '#101b20' if st.session_state.dark else '#f7faf9'
foreground = '#ecf6f4' if st.session_state.dark else '#172d2a'
card = '#1d3033' if st.session_state.dark else '#ffffff'
st.markdown(f'''<style>
.stApp {{background:{background};color:{foreground}}}
.block-container {{max-width:700px;padding-top:.75rem;padding-bottom:3rem}}
header[data-testid="stHeader"], #MainMenu, footer {{visibility:hidden}}
.hero {{background:linear-gradient(135deg,#075e52,#15967c);color:white;padding:1.25rem 1.5rem;border-radius:18px;margin-bottom:.65rem}}
.hero h1 {{color:white;margin:0;font-size:2.1rem}}
.hero p {{margin:.35rem 0 0;color:#e3fff5}}
[data-testid="stMetric"] {{background:{card};border:1px solid #5f8e8555;border-radius:14px;padding:1rem}}
div.stButton > button, div.stDownloadButton > button {{min-height:2.85rem;border-radius:12px}}
@media(max-width:600px) {{.block-container {{padding:.5rem .85rem 4rem}} .hero {{padding:1rem 1.15rem}} .hero h1 {{font-size:1.55rem}} h3 {{font-size:1.25rem !important}}}}
{'''[data-testid="stAppViewContainer"] input, [data-testid="stAppViewContainer"] textarea {
background:#22383b !important;color:#f2faf8 !important;}
[data-testid="stAppViewContainer"] label, [data-testid="stAppViewContainer"] p {
color:#e5f3f0 !important;}''' if st.session_state.dark else ''}
</style>''', unsafe_allow_html=True)

if st.button('☾ Modo escuro' if not st.session_state.dark else '☀ Modo claro',
             help='Alternar aparência'):
    st.session_state.dark = not st.session_state.dark
    st.rerun()
st.markdown('<div class="hero"><h1>⚡ CustoClaro</h1><p>Foto da etiqueta → custo da energia em poucos passos.</p></div>', unsafe_allow_html=True)

st.subheader('Fotografe a etiqueta')
st.caption('A potência precisa aparecer em W ou kW; só o código de barras não basta.')
source = st.radio('Foto', ['Enviar foto', 'Usar câmera'], horizontal=True, label_visibility='collapsed')
if source == 'Usar câmera':
    uploaded = st.camera_input('Fotografe a etiqueta')
else:
    uploaded = st.file_uploader('Escolha a foto', type=['jpg', 'jpeg', 'png', 'webp'])
initial_path = os.getenv('CUSTOCLARO_INITIAL_IMAGE')
if uploaded is None and source == 'Enviar foto' and initial_path:
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
with st.expander('Ativar leitura por IA', expanded=bool(image_data and not api_key)):
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
    st.info('Para ler a foto, adicione a chave em “Ativar leitura por IA”. Ou informe a potência manualmente.')

if image_data is not None and api_key and st.button('Ler potência da foto', type='primary', use_container_width=True):
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
    st.subheader('Confira a potência')
    st.number_input('Potência (W)', min_value=0.0, max_value=1_000_000.0, step=10.0,
                    key='watts', on_change=power_changed)
else:
    with st.expander('Não conseguiu ler a foto? Informe os watts', expanded=False):
        st.number_input('Potência (W)', min_value=0.0, max_value=1_000_000.0, step=10.0,
                        key='watts', on_change=power_changed)

if st.session_state.watts > 0:
    st.number_input('Minutos de uso por dia', min_value=0, max_value=1440, step=5, key='minutes')
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
                                tariff_per_kwh=st.session_state.tariff)
    st.metric('Custo estimado/mês', brl(estimate.monthly_brl))
    st.write(f'**{pt_number(estimate.monthly_kwh)} kWh/mês** · **{brl(estimate.annual_brl)} em 12 meses**')
    st.write(f'Cada uso de {st.session_state.minutes} minutos custa cerca de '
             f'**{brl(estimate.monthly_brl / st.session_state.days)}**.')
    with st.expander('Como chegamos a esse valor?'):
        st.write(f'{pt_number(estimate.watts, 0)} W × {st.session_state.minutes} min/dia × '
                 f'{st.session_state.days} dias × R$ {pt_number(estimate.tariff_per_kwh, 5)}/kWh.')
        st.caption('Estimativa, não medição. Aparelhos com potência variável podem consumir diferente.')
    st.download_button('Baixar resultado (CSV)',
                       data=csv_report(st.session_state.name, estimate, st.session_state.source),
                       file_name='custoclaro_resultado.csv', mime='text/csv', use_container_width=True)
elif st.session_state.reading and not st.session_state.confirmed:
    st.info('Confira e confirme a potência para ver o custo.')

if estimate is not None:
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
