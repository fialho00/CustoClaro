export type EstimateInput = {
  name: string;
  watts: number;
  minutes: number;
  days: number;
  units: number;
  tariff: number;
};

export type Estimate = {
  name: string;
  watts: string;
  minutes: string;
  days: number;
  units: number;
  tariff: string;
  monthly_kwh: string;
  monthly_kwh_label: string;
  monthly_brl: string;
  monthly_brl_label: string;
  annual_brl_label: string;
};

export type Reading = {
  appliance: string;
  power_watts: string | null;
  evidence: string;
  confidence: "alta" | "média" | "baixa";
  notes: string;
  model: string;
};

export type HouseResult = {
  items: Estimate[];
  total_kwh: string;
  total_kwh_label: string;
  total_brl: string;
  total_brl_label: string;
};

export async function request<T>(url: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(url, init);
  } catch {
    throw new Error(
      "Sem conexão com o servidor. Verifique sua internet e tente novamente.",
    );
  }
  if (!response.ok) {
    let message = "Não foi possível concluir. Tente novamente.";
    try {
      const data = (await response.json()) as { detail?: string };
      if (typeof data.detail === "string") message = data.detail;
    } catch {
      /* Keep the safe default */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export function postJson<T>(
  url: string,
  body: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export function formatDecimal(value: number, digits = 2): string {
  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}
