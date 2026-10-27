import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Info,
  LoaderCircle,
  Search,
  SlidersHorizontal,
  Sparkles,
} from "lucide-react";
import { formatDecimal, postJson } from "./api";

export type ExploreMode = "search" | "forecast" | "compare";

export type Product = {
  name: string;
  category: string;
  capacity: string;
  watts: string | null;
  label_kwh_month: string | null;
  price_brl: string | null;
  efficiency: string;
  source_url: string;
  source_kind: string;
};

export type Forecast = {
  monthly_kwh: string;
  monthly_kwh_label: string;
  monthly_brl_label: string;
  annual_brl_label: string;
  method: "etiqueta_padronizada" | "potencia_constante";
  notice: string;
};

export type ExploreContext = { selected: Product | null; products: Product[]; forecast: Forecast | null };

function money(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function decimal(value: string | null): number | null {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function monthlyKwh(product: Product, hours: number, days: number): number | null {
  const label = decimal(product.label_kwh_month);
  if (label !== null) return label;
  const watts = decimal(product.watts);
  return watts === null ? null : (watts / 1000) * hours * days;
}

function stored<T>(key: string, fallback: T): T {
  try {
    const value = sessionStorage.getItem(key);
    return value ? JSON.parse(value) as T : fallback;
  } catch {
    return fallback;
  }
}

export default function Explore({
  mode,
  setMode,
  prefill,
  tariff,
  onManual,
  onContextChange,
  onAssistantNote,
  onAddToHouse,
}: {
  mode: ExploreMode;
  setMode: (mode: ExploreMode) => void;
  prefill: string;
  tariff: number;
  onManual: () => void;
  onContextChange: (context: ExploreContext) => void;
  onAssistantNote: (text: string) => void;
  onAddToHouse: (product: Product, hours: number, days: number) => void;
}) {
  const [query, setQuery] = useState(prefill);
  const [results, setResults] = useState<Product[]>(() => stored('custo-found-products', []));
  const [saved, setSaved] = useState<Product[]>(() => stored('custo-compared-products', []));
  const [selected, setSelected] = useState<Product | null>(() => stored('custo-selected-product', null));
  const [hours, setHours] = useState(5);
  const [days, setDays] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [sort, setSort] = useState("energy");
  const [limitPrice, setLimitPrice] = useState(false);
  const [maxPrice, setMaxPrice] = useState(3000);
  const [manualName, setManualName] = useState("Meu aparelho");
  const [manualWatts, setManualWatts] = useState(0);
  const [userPrices, setUserPrices] = useState<Record<string, string>>({});

  const priceOf = (item: Product) => {
    if (userPrices[item.name] === undefined) return decimal(item.price_brl);
    const updated = Number(userPrices[item.name]);
    return Number.isFinite(updated) && updated > 0 ? updated : null;
  };

  useEffect(() => {
    setQuery(prefill);
  }, [prefill]);

  useEffect(() => {
    try {
      sessionStorage.setItem('custo-found-products', JSON.stringify(results));
      sessionStorage.setItem('custo-compared-products', JSON.stringify(saved));
      sessionStorage.setItem('custo-selected-product', JSON.stringify(selected));
    } catch {
      // Keep functioning without browser storage.
    }
  }, [results, saved, selected]);

  useEffect(() => {
    onContextChange({
      selected,
      products: [...saved, ...results.filter((item) => !saved.some((p) => p.name === item.name))].slice(0, 8),
      forecast,
    });
  }, [results, saved, selected, forecast, onContextChange]);

  async function lookup(event: FormEvent) {
    event.preventDefault();
    if (query.trim().length < 3 || busy) return;
    setBusy(true);
    setError("");
    try {
      const data = await postJson<{ items: Product[]; notice: string }>(
        "/api/products/discover",
        { query: query.trim() },
      );
      setResults(data.items);
      if (data.items.length)
        onAssistantNote(`Encontrei ${data.items.length} modelo(s) com referências de consumo. Confira as fontes e escolha um para calcular o gasto.`);
      if (!data.items.length)
        setError("Não encontrei especificações com fonte suficiente. Tente o código completo do modelo ou fotografe a etiqueta.");
    } catch (exc) {
      setError(exc instanceof Error ? exc.message : "Não foi possível pesquisar.");
    } finally {
      setBusy(false);
    }
  }

  function choose(product: Product) {
    setSelected(product);
    onAssistantNote(`Selecionei ${product.name}. O painel mostra a previsão calculada; você pode ajustar o uso ou comparar com outros modelos.`);
    setSaved((previous) =>
      previous.some((p) => p.name === product.name) ? previous : [...previous, product],
    );
    setMode("forecast");
  }

  useEffect(() => {
    if (!selected) {
      setForecast(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      postJson<Forecast>(
        "/api/products/forecast",
        {
          name: selected.name,
          watts: selected.watts,
          label_kwh_month: selected.label_kwh_month,
          hours,
          days,
          tariff,
        },
        controller.signal,
      )
        .then(setForecast)
        .catch((exc: Error) => {
          if (exc.name !== "AbortError") {
            setForecast(null);
            setError(exc.message);
          }
        });
    }, 180);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [selected, hours, days, tariff]);

  const pool = [...saved, ...results.filter((candidate) => !saved.some((item) => item.name === candidate.name))];
  const compared = pool
    .filter((item) => !limitPrice || (priceOf(item) !== null && priceOf(item)! <= maxPrice))
    .sort((a, b) => {
      const cost = (item: Product) => {
        const price = priceOf(item);
        const energy = monthlyKwh(item, hours, days);
        if (sort === "price") return price;
        if (sort === "total") return price !== null && energy !== null ? price + energy * tariff * 60 : null;
        return energy;
      };
      return (cost(a) ?? Number.POSITIVE_INFINITY) - (cost(b) ?? Number.POSITIVE_INFINITY);
    });

  return (
    <section className="card explore-panel" aria-label="Ferramentas de consumo da IA">
      <div className="explore-heading">
        <span className="square-icon"><Sparkles size={22} /></span>
        <div>
          <span className="eyebrow">FERRAMENTAS DA IA</span>
          <h2>Quanto isso consome?</h2>
          <p>Pesquise, simule e compare sem sair da conversa.</p>
        </div>
      </div>

      <div className="explore-tabs" role="tablist" aria-label="Ferramentas">
        {([[
          "search", "Pesquisar",
        ], ["forecast", "Previsão mensal"], ["compare", "Comparar"]] as const).map(([id, title]) => (
          <button key={id} type="button" role="tab" aria-selected={mode === id}
            className={mode === id ? "selected" : ""} onClick={() => setMode(id)}>{title}</button>
        ))}
      </div>

      {error && <div className="alert alert-error" role="alert"><Info size={18} /><span>{error}</span>
        <button className="icon-button" aria-label="Fechar aviso" onClick={() => setError("")}>×</button></div>}

      {mode === "search" && (
        <div className="explore-body">
          <div className="section-title"><h3>Encontre seu aparelho</h3>
            <p>Digite a marca e o modelo para consultar especificações energéticas.</p></div>
          <form className="explore-search" onSubmit={lookup}>
            <Search size={19} />
            <input aria-label="Pesquisar nome do produto" value={query} onChange={(event) => setQuery(event.target.value)}
              placeholder="Ex.: geladeira Electrolux IF43" minLength={3} maxLength={120} />
            <button type="submit" className="primary-button" disabled={busy || query.trim().length < 3}>
              {busy ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}
              <span>{busy ? "Buscando" : "Buscar"}</span>
            </button>
          </form>
          <div className="search-disclaimer"><Info size={15} /> Pesquisa assistida por IA. Confirme os dados na fonte antes da compra.</div>
          <div className="product-list">
            {results.map((product) => (
              <article key={product.name} className="product-card">
                <div className="product-card-top"><div><strong>{product.name}</strong>
                  <small>{[product.capacity, product.efficiency].filter(Boolean).join(" · ") || "Modelo encontrado"}</small></div>
                  <span className="product-type">{product.category || "Eletrodoméstico"}</span></div>
                <div className="product-facts">
                  <span><b>{product.label_kwh_month ? formatDecimal(Number(product.label_kwh_month)) + " kWh/mês" : product.watts ? formatDecimal(Number(product.watts), 0) + " W" : "Não informado"}</b>
                    <small>{product.label_kwh_month ? "Consumo declarado" : "Potência"}</small></span>
                  <span><b>{product.price_brl ? money(Number(product.price_brl)) : "Não informado"}</b><small>Preço encontrado</small></span>
                </div>
                <div className="product-actions">
                  <a href={product.source_url} target="_blank" rel="noopener noreferrer">Ver fonte</a>
                  <button className="outline-button" onClick={() => choose(product)}>Calcular gasto <ArrowRight size={16} /></button>
                </div>
              </article>
            ))}
          </div>
          {!results.length && !busy && <p className="empty-hint">Os resultados aparecerão aqui com potência, consumo e preço quando esses dados estiverem disponíveis.</p>}
          <div className="manual-options">
            <button className="outline-button" onClick={onManual}>Analisar uma etiqueta ou informar watts <ArrowRight size={16} /></button>
            <a href="https://pbe.inmetro.gov.br/" target="_blank" rel="noopener noreferrer">Consulta oficial do Inmetro</a>
          </div>
        </div>
      )}

      {mode === "forecast" && (
        <div className="explore-body">
          <div className="section-title"><h3>Previsão mensal</h3><p>Personalize a estimativa para sua realidade.</p></div>
          {!selected ? (
            <div className="manual-forecast">
              <p>Pesquise um produto ou comece com a potência de um aparelho que você já conhece.</p>
              <div className="input-grid">
                <label>Nome do aparelho<input value={manualName} maxLength={120} onChange={(event) => setManualName(event.target.value)} /></label>
                <label>Potência (W)<input type="number" min="0" max="1000000" value={manualWatts || ""}
                  placeholder="Ex.: 120" onChange={(event) => setManualWatts(Number(event.target.value))} /></label>
              </div>
              <button className="primary-button" disabled={manualWatts <= 0 || manualWatts > 1000000}
                onClick={() => choose({ name: manualName.trim() || "Meu aparelho", watts: String(manualWatts),
                  label_kwh_month: null, price_brl: null, category: "", capacity: "", efficiency: "",
                  source_url: "", source_kind: "informado pelo usuário" })}>Calcular com essa potência <ArrowRight size={16}/></button>
            </div>
          ) : (
            <>
              <div className="selected-product"><CheckCircle2 size={20} /><div><strong>{selected.name}</strong>
                <small>{selected.source_kind} · confirme os dados da pesquisa</small></div>
                <button onClick={() => setSelected(null)}>Trocar</button></div>
              {!selected.label_kwh_month ? (
                <div className="forecast-controls">
                  <div className="range-label"><span>Horas de uso por dia</span><strong>{formatDecimal(hours, 1)} h</strong></div>
                  <input className="time-slider" type="range" min="0" max="24" step="0.5" value={hours}
                    onChange={(event) => setHours(Number(event.target.value))} aria-label="Horas por dia" />
                  <div className="range-label"><span>Dias por mês</span><strong>{days}</strong></div>
                  <input className="time-slider" type="range" min="1" max="31" step="1" value={days}
                    onChange={(event) => setDays(Number(event.target.value))} aria-label="Dias por mês" />
                </div>
              ) : <div className="search-disclaimer"><Info size={17} /> Consumo mensal de etiqueta: o tempo de uso não deve ser escalado linearmente.</div>}
              {forecast ? (
                <div className="forecast-result">
                  <span>Gasto estimado por mês</span><strong>{forecast.monthly_brl_label}</strong>
                  <div><span>{forecast.monthly_kwh_label} por mês</span><span>{forecast.annual_brl_label} em 12 meses</span></div>
                  <small>Tarifa utilizada: {money(tariff)}/kWh. {forecast.notice}</small>
                </div>
              ) : <p className="empty-hint">Calculando previsão...</p>}
              <div className="product-actions">
                <button className="primary-button" onClick={() => onAddToHouse(selected, hours, days)} disabled={!forecast}>
                  Adicionar à minha casa <ArrowRight size={16}/>
                </button>
                <button className="outline-button" onClick={() => setMode("compare")}>Comparar este modelo <ArrowRight size={16}/></button>
              </div>
            </>
          )}
        </div>
      )}

      {mode === "compare" && (
        <div className="explore-body">
          <div className="section-title"><h3>Comparador inteligente</h3>
            <p>Considere modelos de função e capacidade semelhantes.</p></div>
          <div className="compare-filters">
            <label><SlidersHorizontal size={16} /> Ordenar por
              <select value={sort} onChange={(event) => setSort(event.target.value)}>
                <option value="energy">Menor consumo</option><option value="price">Menor preço</option>
                <option value="total">Compra + 5 anos de energia</option>
              </select></label>
            <label className="check-filter"><input type="checkbox" checked={limitPrice} onChange={(event) => setLimitPrice(event.target.checked)} /> Filtrar por preço</label>
            {limitPrice && <label>Preço máximo: {money(maxPrice)}<input type="range" min="500" max="15000" step="250" value={maxPrice}
              onChange={(event) => setMaxPrice(Number(event.target.value))}/></label>}
          </div>
          <div className="product-list">
            {compared.map((product) => {
              const usage = monthlyKwh(product, hours, days);
              const price = priceOf(product);
              return <article className="product-card" key={product.name}>
                <div className="product-card-top"><div><strong>{product.name}</strong><small>{product.capacity || "Capacidade não informada"}</small></div></div>
                <div className="product-facts"><span><b>{usage === null ? "Não informado" : formatDecimal(usage) + " kWh"}</b><small>Consumo mensal</small></span>
                  <span><b>{price === null ? "Não informado" : money(price)}</b><small>Preço de compra</small></span></div>
                {usage !== null && <p className="cost-projection">Energia: {money(usage * tariff)}/mês
                  {price !== null && <> · Total em 5 anos: {money(price + usage * tariff * 60)}</>}</p>}
                <label className="product-price-input">Preço de compra (R$) · opcional
                  <input type="number" min="0" max="10000000" step="0.01" value={userPrices[product.name] ?? (product.price_brl ?? "")}
                    placeholder="Informar preço" onChange={(event) => setUserPrices((previous) => ({ ...previous, [product.name]: event.target.value }))} />
                </label>
                <div className="product-actions"><button className="outline-button" onClick={() => choose(product)}>Ver previsão <ArrowRight size={16}/></button></div>
              </article>;
            })}
          </div>
          {!compared.length && <p className="empty-hint">{pool.length ? "Nenhum produto com preço informado atende ao filtro." : "Pesquise aparelhos para começar a comparação."}</p>}
          <button className="outline-button" onClick={() => setMode("search")}>Adicionar outro modelo <ArrowRight size={16} /></button>
          <p className="fineprint">Para aparelhos com potência variável, a previsão por W × horas é apenas aproximação. Preço e consumo encontrados pela IA devem ser confirmados.</p>
        </div>
      )}
    </section>
  );
}
