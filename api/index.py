"""Stateless API: the browser handles UI state; Python owns all calculations."""

from __future__ import annotations

import io
import os
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from PIL import Image, ImageOps, UnidentifiedImageError
from starlette.staticfiles import StaticFiles

from core import brl, calculate_energy, pt_number
from product_catalog import search_appliances
from tariffs import current_flag, lookup_residential_tariff, reverse_location, search_distributors
from vision import configured_api_key, read_label, answer_about_estimate


app = FastAPI(title="CustoClaro", docs_url=None, redoc_url=None)
PREFERRED_MODEL = os.getenv("CUSTOCLARO_MODEL", "gemini-3.1-flash-lite")
MAX_IMAGE_BYTES = 4 * 1024 * 1024


class EstimateInput(BaseModel):
    name: str = Field(default="Aparelho", max_length=120)
    watts: Decimal
    minutes: Decimal = Decimal("10")
    days: int = 30
    units: int = 1
    tariff: Decimal = Decimal("0.90")


class ComparedProduct(BaseModel):
    name: str = Field(max_length=120)
    monthly_kwh: Decimal | None = None
    price_brl: Decimal | None = None


class ChatInput(BaseModel):
    question: str = Field(min_length=1, max_length=800)
    appliance: EstimateInput | None = None
    house: list[EstimateInput] = Field(default_factory=list, max_length=30)
    products: list[ComparedProduct] = Field(default_factory=list, max_length=6)


class ProductSearchInput(BaseModel):
    query: str = Field(min_length=3, max_length=120)
    tariff: Decimal = Decimal("0.90")
    hours_per_day: Decimal = Decimal("4")
    days: int = 30
    max_price: Decimal | None = None
    sort: str = "consumption"


class LocationInput(BaseModel):
    latitude: float
    longitude: float


def estimate_for(values: EstimateInput):
    return calculate_energy(
        watts=values.watts,
        hours_per_day=values.minutes / 60,
        days_per_month=values.days,
        tariff_per_kwh=values.tariff,
        units=values.units,
    )


def serialized_estimate(values: EstimateInput) -> dict:
    result = estimate_for(values)
    return {
        "name": values.name,
        "watts": str(result.watts),
        "minutes": str(values.minutes),
        "days": result.days_per_month,
        "units": result.units,
        "tariff": str(result.tariff_per_kwh),
        "monthly_kwh": str(result.monthly_kwh),
        "monthly_kwh_label": f"{pt_number(result.monthly_kwh)} kWh",
        "monthly_brl": str(result.monthly_brl),
        "monthly_brl_label": brl(result.monthly_brl),
        "annual_brl_label": brl(result.annual_brl),
    }


@app.get("/api/health")
def health():
    return {"status": "ok", "ai_available": bool(configured_api_key())}


@app.post("/api/estimate")
def estimate(values: EstimateInput):
    try:
        return serialized_estimate(values)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/house")
def estimate_house(items: list[EstimateInput]):
    if len(items) > 30:
        raise HTTPException(status_code=422, detail="Adicione no máximo 30 aparelhos.")
    try:
        rows = [serialized_estimate(item) for item in items]
        total_kwh = sum((Decimal(row["monthly_kwh"]) for row in rows), Decimal(0))
        total_brl = sum((Decimal(row["monthly_brl"]) for row in rows), Decimal(0))
        return {
            "items": rows,
            "total_kwh": str(total_kwh),
            "total_kwh_label": f"{pt_number(total_kwh)} kWh",
            "total_brl": str(total_brl),
            "total_brl_label": brl(total_brl),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...)):
    if file.content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Envie JPEG, PNG ou WebP.")
    key = configured_api_key()
    if not key:
        raise HTTPException(status_code=503, detail="A leitura por IA não está configurada neste servidor.")
    content = await file.read(MAX_IMAGE_BYTES + 1)
    if len(content) > MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="A foto deve ter até 4 MB.")
    try:
        with Image.open(io.BytesIO(content)) as source:
            if source.width * source.height > 20_000_000:
                raise ValueError("Reduza a resolução da foto.")
            prepared = ImageOps.exif_transpose(source).convert("RGB")
            prepared.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
            buffer = io.BytesIO()
            prepared.save(buffer, format="JPEG", quality=85, optimize=True)
        reading = read_label(buffer.getvalue(), "image/jpeg", model=PREFERRED_MODEL, api_key=key)
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Não foi possível analisar a foto: {exc}") from exc
    except Exception as exc:
        code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if code in (401, 403):
            message = "A chave de IA do servidor não foi autorizada."
        elif code == 429:
            message = "O limite da IA foi atingido. Tente novamente mais tarde."
        else:
            message = "A IA demorou a responder. Tente novamente ou informe a potência manualmente."
        raise HTTPException(status_code=503, detail=message) from exc
    return {
        "appliance": reading.appliance,
        "power_watts": str(reading.power_watts) if reading.power_watts is not None else None,
        "evidence": reading.evidence,
        "confidence": reading.confidence,
        "notes": reading.notes,
        "model": reading.model,
    }


def local_chat_reply(payload: ChatInput) -> str | None:
    question = payload.question.casefold()
    comparable = [item for item in payload.products if item.monthly_kwh is not None and item.monthly_kwh >= 0]
    if comparable and any(x in question for x in ("mais econômico", "mais economico", "menos consome", "mais eficiente")):
        winner = min(comparable, key=lambda item: item.monthly_kwh)
        return (f"Entre os modelos pesquisados com dados suficientes, {winner.name} apresenta o menor consumo "
                f"estimado: {pt_number(winner.monthly_kwh)} kWh/mês. Confirme as especificações na fonte antes de comprar.")
    if payload.house and any(x in question for x in ("mais gasta", "mais consome", "maior", "mais pesa", "prioridade")):
        ranking = [(entry, estimate_for(entry)) for entry in payload.house]
        entry, result = max(ranking, key=lambda row: row[1].monthly_brl)
        return f"Nesta simulação, {entry.name} tem o maior custo: {brl(result.monthly_brl)}/mês. Isso depende da potência e do tempo informado."
    if payload.house and any(x in question for x in ("total", "todos", "minha casa")):
        total = sum((estimate_for(entry).monthly_brl for entry in payload.house), Decimal(0))
        return f"Os {len(payload.house)} aparelhos adicionados somam aproximadamente {brl(total)} por mês."
    if payload.appliance:
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(minutos?|min|horas?|h)\b", question)
        if match:
            amount = Decimal(match.group(1).replace(",", "."))
            minutes = amount * 60 if match.group(2).startswith(("h", "hora")) else amount
            if not 0 <= minutes <= 1440:
                return "Informe um tempo de uso entre 0 e 24 horas por dia."
            changed = payload.appliance.model_copy(update={"minutes": minutes})
            current = estimate_for(payload.appliance)
            alternative = estimate_for(changed)
            difference = current.monthly_brl - alternative.monthly_brl
            movement = "economia" if difference >= 0 else "aumento"
            return (f"Usando {pt_number(minutes, 0)} minutos por dia, o custo estimado seria "
                    f"{brl(alternative.monthly_brl)}/mês — {movement} de {brl(abs(difference))}/mês "
                    "em relação à simulação atual.")
        if any(x in question for x in ("tarifa", "preço do kwh", "preco do kwh")):
            return f"A tarifa desta simulação é {brl(payload.appliance.tariff)}/kWh. Você pode ajustá-la nos parâmetros."
    return None


ENERGY_TERMS = re.compile(
    r"energia|el[eé]tric|eletro|consum|gasto|conta|tarifa|kwh|watt|pot[eê]ncia|"
    r"economi|efici[eê]n|aparelho|geladeira|freezer|micro.?ondas|ar.?condicionado|"
    r"chuveiro|l[aâ]mpada|lavadora|m[aá]quina de lavar|televis|tv\b|"
    r"computador|notebook|ventilador|secador|aquecedor|produto|modelo|loja|"
    r"pre[çc]o|custo|minha casa|etiqueta|fotograf|analis",
    re.IGNORECASE,
)
INTRO_TERMS = re.compile(r"^(oi|ol[aá]|bom dia|boa tarde|boa noite|como funciona\??|ajuda\??)[.!? ]*$", re.IGNORECASE)
UNRELATED_TERMS = re.compile(
    r"ra[çc]as? de cachorr|ra[çc]as? de gato|cachorro|c[aã]es\b|"
    r"receita de bolo|conte.*piada|futebol|hor[oó]scopo|namoro|pol[ií]tica|"
    r"ignore.*instru[çc]|desconsidere.*regras",
    re.IGNORECASE,
)
OUT_OF_SCOPE = (
    "Sou a Nom Nom e ajudo exclusivamente com energia elétrica: consumo de aparelhos, "
    "estimativas de custo, economia e comparação de eficiência. Quer analisar algum aparelho?"
)


def on_topic(payload: ChatInput) -> bool:
    question = payload.question.strip()
    if UNRELATED_TERMS.search(question):
        return False
    return bool(ENERGY_TERMS.search(question) or INTRO_TERMS.fullmatch(question)
                or payload.appliance or payload.house or payload.products)


@app.post("/api/chat")
def chat(payload: ChatInput):
    if not on_topic(payload):
        return {"reply": OUT_OF_SCOPE, "source": "escopo"}
    try:
        local = local_chat_reply(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if local:
        return {"reply": local, "source": "calculo"}
    context = "Sem aparelho analisado no momento."
    if payload.appliance:
        row = serialized_estimate(payload.appliance)
        context = (f"Aparelho: {row['name']}; potência: {row['watts']} W; "
                   f"uso: {row['minutes']} min/dia; tarifa: {row['tariff']} R$/kWh; "
                   f"custo: {row['monthly_brl_label']}/mês; energia: {row['monthly_kwh_label']}.")
    if payload.house:
        parts = [f"{entry.name}: {brl(estimate_for(entry).monthly_brl)}/mês" for entry in payload.house[:10]]
        context += " Itens da casa: " + "; ".join(parts)
    if payload.products:
        parts = [f"{entry.name}: {pt_number(entry.monthly_kwh)} kWh/mês" if entry.monthly_kwh is not None else entry.name
                 for entry in payload.products]
        context += " Produtos encontrados na pesquisa: " + "; ".join(parts)
    key = configured_api_key()
    if key:
        try:
            return {"reply": answer_about_estimate(payload.question, context, api_key=key, model=PREFERRED_MODEL), "source": "ia"}
        except Exception:
            pass
    if not payload.appliance and not payload.house:
        reply = "Envie uma foto da etiqueta ou informe a potência em watts. Depois posso comparar cenários e explicar os custos."
    else:
        reply = "Posso explicar o custo, a tarifa ou comparar outro tempo de uso. Experimente perguntar: 'E se eu usar 5 minutos?'."
    return {"reply": reply, "source": "orientacao"}


@app.post("/api/products/search")
def products_search(payload: ProductSearchInput):
    if not 0 < payload.tariff <= 1000 or not 0 < payload.hours_per_day <= 24 or not 1 <= payload.days <= 31:
        raise HTTPException(status_code=422, detail="Revise tarifa, horas por dia e dias do mês.")
    if payload.max_price is not None and not 0 < payload.max_price <= 1000000:
        raise HTTPException(status_code=422, detail="Informe um preço máximo válido.")
    if payload.sort not in {"consumption", "price", "efficiency"}:
        raise HTTPException(status_code=422, detail="Ordenação inválida.")
    key = configured_api_key()
    if not key:
        raise HTTPException(status_code=503, detail="A pesquisa de produtos por IA não está configurada.")
    try:
        return search_appliances(payload.query, api_key=key, tariff=payload.tariff,
                                 hours_per_day=payload.hours_per_day, days=payload.days,
                                 max_price=payload.max_price, sort=payload.sort)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="A busca em lojas está indisponível agora. Tente novamente.") from exc


@app.get("/api/distributors")
def distributors(q: str = ""):
    try:
        return {"items": search_distributors(q)[:50]}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Consulta à ANEEL temporariamente indisponível.") from exc


@app.get("/api/tariff")
def tariff(utility: str):
    try:
        found = lookup_residential_tariff(utility, date.today())
        if not found:
            raise HTTPException(status_code=404, detail="Não há tarifa residencial única e vigente para esta distribuidora.")
        try:
            flag = current_flag(date.today())
        except (OSError, ValueError, KeyError):
            flag = None
        extra = flag[1] if flag else Decimal(0)
        return {
            "utility": found.utility,
            "base": str(found.per_kwh),
            "flag": flag[0] if flag else None,
            "flag_extra": str(extra),
            "total": str(found.per_kwh + extra),
            "valid_until": found.ends.isoformat(),
            "notice": "Tarifa base; impostos, contribuição de iluminação e regras da fatura não estão incluídos.",
        }
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail="Consulta à ANEEL temporariamente indisponível.") from exc


@app.post("/api/location")
def location(coords: LocationInput):
    try:
        city, state = reverse_location(coords.latitude, coords.longitude)
        return {"city": city, "state": state}
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=503, detail="Não foi possível identificar a região.") from exc


# Local executable: serve the same compiled Vite interface at localhost:8501.
# In Vercel the static build is hosted by the CDN and /api routes by Python.
DIST = Path(__file__).resolve().parents[1] / "dist"
if DIST.is_dir():
    if (DIST / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/")
    def home():
        return FileResponse(DIST / "index.html")

    @app.get("/{path:path}")
    def single_page(path: str):
        candidate = (DIST / path).resolve()
        if candidate.is_file() and candidate.is_relative_to(DIST.resolve()):
            return FileResponse(candidate)
        return FileResponse(DIST / "index.html")
