"""Deterministic electrical-energy estimates for WattCola."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def as_decimal(value: object, name: str) -> Decimal:
    """Convert user-provided values without binary-floating-point calculations."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} precisa ser numérico.") from exc
    if not number.is_finite():
        raise ValueError(f"{name} precisa ser finito.")
    return number


@dataclass(frozen=True)
class EnergyEstimate:
    watts: Decimal
    hours_per_day: Decimal
    days_per_month: int
    units: int
    tariff_per_kwh: Decimal
    daily_kwh: Decimal
    monthly_kwh: Decimal
    monthly_brl: Decimal
    annual_kwh: Decimal
    annual_brl: Decimal


def calculate_energy(
    *,
    watts: object,
    hours_per_day: object,
    days_per_month: int,
    tariff_per_kwh: object,
    units: int = 1,
) -> EnergyEstimate:
    """Estimate energy use assuming steady draw at the entered power.

    Annual numbers represent twelve identical simulated months, not 365 days.
    The price is user-entered and is not an official utility tariff.
    """
    power = as_decimal(watts, "Potência")
    hours = as_decimal(hours_per_day, "Horas diárias")
    tariff = as_decimal(tariff_per_kwh, "Tarifa")

    if not 0 < power <= Decimal("1000000"):
        raise ValueError("Potência deve estar entre 0 e 1.000.000 W.")
    if not 0 <= hours <= 24:
        raise ValueError("Horas diárias devem estar entre 0 e 24.")
    if type(days_per_month) is not int or not 1 <= days_per_month <= 31:
        raise ValueError("Dias por mês devem estar entre 1 e 31.")
    if type(units) is not int or not 1 <= units <= 1000:
        raise ValueError("Quantidade deve estar entre 1 e 1000.")
    if not 0 <= tariff <= Decimal("1000"):
        raise ValueError("Tarifa deve estar entre R$ 0 e R$ 1.000/kWh.")

    daily = (power / Decimal(1000)) * hours * units
    monthly = daily * days_per_month
    price = monthly * tariff
    return EnergyEstimate(
        watts=power,
        hours_per_day=hours,
        days_per_month=days_per_month,
        units=units,
        tariff_per_kwh=tariff,
        daily_kwh=daily,
        monthly_kwh=monthly,
        monthly_brl=price,
        annual_kwh=monthly * 12,
        annual_brl=price * 12,
    )


def calculate_label_energy(
    *, monthly_kwh: object, tariff_per_kwh: object, units: int = 1
) -> EnergyEstimate:
    """A label's standardized monthly kWh is not equivalent to continuous watts.

    Never scale standardized label consumption by guessed hours or days.
    """
    monthly_per_unit = as_decimal(monthly_kwh, "Consumo de etiqueta")
    tariff = as_decimal(tariff_per_kwh, "Tarifa")
    if not 0 < monthly_per_unit <= Decimal("1000000"):
        raise ValueError("Consumo de etiqueta deve ser positivo e até 1.000.000 kWh/mês.")
    if type(units) is not int or not 1 <= units <= 1000:
        raise ValueError("Quantidade deve estar entre 1 e 1000.")
    if not 0 <= tariff <= Decimal("1000"):
        raise ValueError("Tarifa deve estar entre R$ 0 e R$ 1.000/kWh.")
    monthly = monthly_per_unit * units
    cost = monthly * tariff
    return EnergyEstimate(
        watts=Decimal(0),
        hours_per_day=Decimal(0),
        days_per_month=30,
        units=units,
        tariff_per_kwh=tariff,
        daily_kwh=monthly / 30,
        monthly_kwh=monthly,
        monthly_brl=cost,
        annual_kwh=monthly * 12,
        annual_brl=cost * 12,
    )


def brl(value: object) -> str:
    amount = as_decimal(value, "Valor").quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}"


def pt_number(value: object, places: int = 2) -> str:
    amount = as_decimal(value, "Valor")
    precision = Decimal("1").scaleb(-places)
    formatted = f"{amount.quantize(precision, rounding=ROUND_HALF_UP):,.{places}f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def safe_spreadsheet_text(value: str) -> str:
    """Keep untrusted text from becoming a formula when a CSV is opened."""
    if value.startswith(("\t", "\r", "\n")) or value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
