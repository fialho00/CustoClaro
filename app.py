"""CustoClaro — visual, explainable household energy cost estimator."""

from __future__ import annotations

import csv
import hashlib
import io
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from PIL import Image, ImageOps, UnidentifiedImageError

from core import brl, calculate_energy, pt_number, safe_spreadsheet_text
from vision import DEFAULT_MODEL, MAX_UPLOAD_BYTES, LabelReading, read_label

load_dotenv(Path(__file__).resolve().parent / ".env")

st.set_page_config(
    page_title="CustoClaro | Entenda sua conta de luz",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .stApp { background: #f7f8fb; color: #182336; }
      .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1230px; }
      h1, h2, h3 { color: #142437; letter-spacing: -.025em; }
      h1 { font-size: 2.6rem !important; margin-bottom: .2rem; }
      [data-testid="stMetric"] {
        background: white; border: 1px solid #e5eaf0; border-radius: 17px;
        padding: 1.25rem; box-shadow: 0 8px 30px rgba(28,47,75,.04);
      }
      [data-testid="stSidebar"] { background: #edf4f2; }
      div.stButton > button[kind="primary"] {
        background: #087d66; color: white; border-radius: 10px; border: 0;
      }
      div.stButton > button[kind="primary"]:hover { background: #006957; color: white; }
      .eyebrow { color: #087d66; font-weight: 800; font-size: .84rem;
        letter-spacing: .15em; text-transform: uppercase; }
      .subline { color: #56667b; font-size: 1.05rem; max-width: 55rem; }
      .formula { background: #eaf5f1; border: 1px solid #c8e9dc;
        border-radius: 12px; padding: 1.1rem 1.25rem; color: #185745; }
      .disclaimer { background: #fff8e9; border-radius: 12px;
        border: 1px solid #f4deb0; padding: .85rem 1rem; color: #66502b; }
      .hero { background: linear-gradient(120deg, #123e39, #087d66); color: white;
        border-radius: 20px; padding: 1.65rem 2rem; margin-bottom: 1.5rem; }
      .hero h1 { color: white !important; margin: .25rem 0 .4rem; }
      .hero p { color: #e4f8f1; margin: 0; max-width: 48rem; }
      .hero .eyebrow { color: #b9f1db; }
    </style>
    """,
    unsafe_allow_html=True,
)


def prepare_image(uploaded: object) -> tuple[bytes, str]:
    """Validate and normalize photo bytes before sending to the remote model."""
    raw = uploaded.getvalue()  # type: ignore[attr-defined]
    if not raw or len(raw) > MAX_UPLOAD_BYTES:
        raise ValueError("Imagem vazia ou maior que 8 MB.")

    try:
        with Image.open(io.BytesIO(raw)) as original:
            if original.width * original.height > 20_000_000:
                raise ValueError("A imagem tem resolução excessiva.")
            if original.format not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Arquivo inválido. Escolha JPEG, PNG ou WebP.")
            image = ImageOps.exif_transpose(original).convert("RGB")
            image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=88, optimize=True)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise ValueError(f"Não foi possível ler essa imagem: {exc}") from exc
    return buffer.getvalue(), "image/jpeg"


def csv_report(name: str, estimate: object, alternative: object) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Projeto", "CustoClaro"])
    writer.writerow(["Aparelho", safe_spreadsheet_text(name)])
    writer.writerow(["Potência (W)", pt_number(estimate.watts)])  # type: ignore[attr-defined]
    writer.writerow(["Unidades", estimate.units])  # type: ignore[attr-defined]
    writer.writerow(["Dias por mês", estimate.days_per_month])  # type: ignore[attr-defined]
    writer.writerow(["Tarifa informada (R$/kWh)", pt_number(estimate.tariff_per_kwh)])  # type: ignore[attr-defined]
    writer.writerow([])
    writer.writerow(["Cenário", "Horas/dia", "kWh/mês", "R$/mês"])
    for label, item in (("Atual", estimate), ("Alternativo", alternative)):
        writer.writerow(
            [label, pt_number(item.hours_per_day), pt_number(item.monthly_kwh), pt_number(item.monthly_brl)]
        )
    writer.writerow([])
    writer.writerow(["Nota", "Estimativas com potência constante; não substituem medição."])
    return ("\ufeff" + buffer.getvalue()).encode("utf-8")


for key, default in {
    "device_name": "",
    "watts_field": 0.0,
    "hours_field": 2.0,
    "days_field": 30,
    "units_field": 1,
    "tariff_field": 0.90,
    "label_reading": None,
    "power_confirmed": False,
    "source_kind": "manual",
    "photo_fingerprint": None,
}.items():
    st.session_state.setdefault(key, default)


def mark_manual_power_change() -> None:
    if st.session_state.get("label_reading") is not None:
        st.session_state["power_confirmed"] = False
        st.session_state["source_kind"] = "ajustada manualmente após leitura com Gemma 4 — pendente de confirmação"
    elif st.session_state.get("source_kind") == "exemplo manual — sem IA":
        st.session_state["source_kind"] = "manual"

st.markdown(
    '<div class="hero"><div class="eyebrow">⚡ Energia em números claros</div>'
    '<h1>CustoClaro</h1><p>Fotografe a etiqueta, confirme a potência e descubra '
    'quanto o aparelho pode custar por mês. Sem foto? Preencha manualmente.</p></div>',
    unsafe_allow_html=True,
)

with st.sidebar:
    st.header("Sobre este projeto")
    st.write("**IA:** Gemma 4 (modelo open-weight) pela Gemini API.")
    model = DEFAULT_MODEL
    st.code(model)
    has_key = bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))
    if has_key:
        st.success("Chave encontrada. Teste a conexão usando uma foto real.")
    else:
        st.warning("Sem chave de API: cálculo manual disponível; leitura por IA desativada.")
    st.caption("A imagem é enviada à API do Google apenas quando você clica em **Analisar etiqueta**.")
    st.divider()
    st.subheader("Exemplo rápido")
    if st.button("Carregar ventilador de exemplo", use_container_width=True):
        st.session_state.update(
            device_name="Ventilador (exemplo fictício)",
            watts_field=60.0,
            hours_field=8.0,
            days_field=30,
            tariff_field=0.90,
            units_field=1,
            label_reading=None,
            power_confirmed=True,
            source_kind="exemplo manual — sem IA",
        )
        st.rerun()
    st.caption("Dados de demonstração fictícios, não extraídos de uma imagem.")

st.markdown("### 1. Fotografe a etiqueta")
left, right = st.columns([1.03, 1], gap="large")

with left:
    mode = st.radio(
        "Origem da imagem", ["Arquivo", "Câmera"], horizontal=True, label_visibility="collapsed"
    )
    if mode == "Arquivo":
        uploaded = st.file_uploader(
            "Imagem da etiqueta (JPEG, PNG ou WebP)", type=["jpg", "jpeg", "png", "webp"]
        )
    else:
        uploaded = st.camera_input("Fotografe a etiqueta de potência")
    initial_path = os.getenv("CUSTOCLARO_INITIAL_IMAGE")
    if uploaded is None and mode == "Arquivo" and initial_path:
        if st.checkbox("Usar imagem selecionada no iniciador", value=True):
            try:
                selected_path = Path(initial_path)
                if selected_path.stat().st_size > MAX_UPLOAD_BYTES:
                    raise ValueError("Imagem maior que 8 MB.")
                uploaded = io.BytesIO(selected_path.read_bytes())
            except (OSError, ValueError):
                st.error("Nao foi possivel abrir a imagem selecionada. Escolha outro arquivo acima.")
    image_data: tuple[bytes, str] | None = None
    if uploaded is not None:
        try:
            image_data = prepare_image(uploaded)
            st.image(image_data[0], caption="Prévia da imagem selecionada", use_container_width=True)
        except ValueError as exc:
            st.error(str(exc))

    fingerprint = hashlib.sha256(image_data[0]).hexdigest() if image_data else None
    if fingerprint != st.session_state["photo_fingerprint"]:
        if st.session_state["label_reading"] is not None:
            # Do not display the old picture's wattage or evidence for a new one.
            st.session_state["watts_field"] = 0.0
            st.session_state["device_name"] = ""
        st.session_state["label_reading"] = None
        st.session_state["power_confirmed"] = False
        st.session_state["source_kind"] = "manual"
        st.session_state["photo_fingerprint"] = fingerprint

    analyze = st.button(
        "🔎 Analisar etiqueta com Gemma 4",
        type="primary",
        disabled=image_data is None or not has_key,
        use_container_width=True,
    )
    if analyze and image_data:
        try:
            with st.spinner("A Gemma 4 está procurando a potência nominal na etiqueta..."):
                reading = read_label(*image_data, model=model)
            st.session_state["label_reading"] = reading
            st.session_state["power_confirmed"] = False
            st.session_state["source_kind"] = f"Gemma 4 ({model}) — pendente de revisão humana"
            st.session_state["device_name"] = reading.appliance
            st.session_state["watts_field"] = float(reading.power_watts or 0)
            if reading.power_watts is None:
                st.warning("A potência não foi identificada com segurança. Preencha manualmente.")
            else:
                st.success("Leitura concluída. Verifique a potência antes de calcular.")
        except ValueError as exc:
            st.error(str(exc))
        except Exception as exc:
            st.error("A chamada à Gemma 4 falhou. Verifique chave, acesso ao modelo e internet.")
            st.caption(f"Tipo da falha: {type(exc).__name__}")

with right:
    st.markdown("#### Sua estimativa em três passos")
    st.write("**1.** Envie a etiqueta ou informe a potência em W.")
    st.write("**2.** Confira a leitura e indique horas de uso e tarifa.")
    st.write("**3.** Compare custos e exporte o resultado.")
    reading: LabelReading | None = st.session_state.get("label_reading")
    if reading:
        with st.container(border=True):
            st.markdown("**Trecho encontrado na etiqueta**")
            st.code(reading.evidence or "Nenhum trecho confiável detectado")
            st.caption(f"Confiança informada pela IA: {reading.confidence}. {reading.notes}")
    with st.expander("Como a IA lê a etiqueta e quais são os limites?"):
        st.write("A Gemma 4 procura potência explícita em W ou kW e cita o trecho lido. "
                 "Ela pode errar: confira a foto e confirme o valor. Tarifa, tempo de uso "
                 "e consumo real não são inferidos pela IA.")

st.divider()
st.markdown("### 2. Confirme os dados e simule")
st.caption(f"Origem da potência: {st.session_state['source_kind']}. Tarifa inicial ilustrativa: R$ 0,90/kWh.")
col1, col2, col3 = st.columns([1.8, 1.05, 1], gap="medium")
with col1:
    name = st.text_input("Aparelho", key="device_name", placeholder="Ex.: ventilador")
with col2:
    watts = st.number_input(
        "Potência nominal (W)", min_value=0.0, max_value=1000000.0,
        step=10.0, key="watts_field", on_change=mark_manual_power_change,
    )
with col3:
    units = st.number_input("Quantidade de aparelhos", min_value=1, max_value=1000, step=1, key="units_field")

col4, col5, col6 = st.columns(3, gap="medium")
with col4:
    hours = st.number_input("Horas de uso por dia", min_value=0.0, max_value=24.0, step=0.5, key="hours_field")
with col5:
    days = st.number_input("Dias de uso por mês", min_value=1, max_value=31, step=1, key="days_field")
with col6:
    tariff = st.number_input("Tarifa estimada (R$/kWh)", min_value=0.0, max_value=1000.0, step=0.05, format="%.2f", key="tariff_field")

if st.session_state["label_reading"] is not None and watts > 0 and not st.session_state["power_confirmed"]:
    st.warning("Antes de calcular, confira a potência indicada na etiqueta e confirme o valor.")
    if st.button("✓ Confirmar potência e calcular", type="primary"):
        st.session_state["power_confirmed"] = True
        if "ajustada manualmente" in st.session_state["source_kind"]:
            st.session_state["source_kind"] = "ajustada manualmente após leitura com Gemma 4 — confirmada pelo usuário"
        else:
            st.session_state["source_kind"] = f"Gemma 4 ({model}) — confirmado pelo usuário"
        st.rerun()

if watts <= 0:
    st.info("Informe uma potência maior que zero para ver os resultados. Você pode carregar o exemplo no menu lateral.")
elif st.session_state["label_reading"] is not None and not st.session_state["power_confirmed"]:
    st.info("A estimativa aparecerá após a confirmação humana do valor sugerido pela IA.")
else:
    try:
        estimate = calculate_energy(
            watts=watts,
            hours_per_day=hours,
            days_per_month=days,
            tariff_per_kwh=tariff,
            units=units,
        )
    except ValueError as exc:
        st.error(f"Dados inválidos: {exc}")
        st.stop()

    st.divider()
    st.markdown("### 3. Resultado transparente")
    a, b, c = st.columns(3, gap="medium")
    a.metric("Consumo mensal", f"{pt_number(estimate.monthly_kwh)} kWh")
    b.metric("Custo mensal estimado", brl(estimate.monthly_brl))
    c.metric("Custo em 12 meses iguais", brl(estimate.annual_brl))

    st.markdown(
        '<div class="formula"><strong>Como calculamos:</strong> '
        'consumo (kWh/mês) = potência (W) ÷ 1.000 × horas/dia × dias/mês × aparelhos.<br>'
        'Custo (R$/mês) = consumo (kWh/mês) × tarifa informada (R$/kWh).</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Aplicando seus números: {pt_number(estimate.watts)} W ÷ 1.000 × "
        f"{pt_number(estimate.hours_per_day)} h × {days} dias × {units} = "
        f"{pt_number(estimate.monthly_kwh)} kWh/mês."
    )

    st.markdown("### 4. E se mudarmos o tempo de uso?")
    alternative_hours = st.slider(
        "Horas diárias no cenário alternativo", min_value=0.0, max_value=24.0,
        value=min(24.0, round(hours * 0.75 * 2) / 2), step=0.5,
    )
    alternative = calculate_energy(
        watts=watts,
        hours_per_day=alternative_hours,
        days_per_month=days,
        tariff_per_kwh=tariff,
        units=units,
    )
    saving = estimate.monthly_brl - alternative.monthly_brl
    d, e = st.columns([1.2, 1], gap="large")
    with d:
        graph = pd.DataFrame(
            {
                "Cenário": ["Uso informado", "Uso alternativo"],
                "Custo estimado (R$/mês)": [
                    float(estimate.monthly_brl), float(alternative.monthly_brl)
                ],
            }
        ).set_index("Cenário")
        st.bar_chart(graph, color="#087d66", horizontal=True)
    with e:
        st.metric("Diferença mensal", brl(saving))
        st.write(
            "Valor positivo representa economia no cenário alternativo. "
            "Valor negativo representa gasto adicional."
        )
        st.download_button(
            "⬇️ Exportar simulação (CSV)",
            data=csv_report(name or "Aparelho sem nome", estimate, alternative),
            file_name="custoclaro_simulacao.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.markdown(
        '<div class="disclaimer"><strong>Atenção:</strong> esta é uma simulação baseada na '
        'potência informada e em uso constante. Aparelhos com termostato, ciclos, modos de '
        'potência ou consumo variável podem gastar mais ou menos. A tarifa é ilustrativa e '
        'não inclui automaticamente impostos, bandeiras e outras cobranças.</div>',
        unsafe_allow_html=True,
    )

st.divider()
st.caption("CustoClaro • Projeto open-source • Cálculos determinísticos + leitura assistida por Gemma 4")

