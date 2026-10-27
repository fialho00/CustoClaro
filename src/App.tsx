import { useEffect, useRef, useState } from "react";
import type { ChangeEvent } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bolt,
  Camera,
  Check,
  CheckCircle2,
  ChevronRight,
  Clock3,
  CloudOff,
  FileText,
  History,
  Home,
  ImagePlus,
  Info,
  Lightbulb,
  LoaderCircle,
  MapPin,
  Menu,
  Pencil,
  Plus,
  Send,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Wallet,
  X,
} from "lucide-react";
import { formatDecimal, postJson, request } from "./api";
import type { Estimate, EstimateInput, HouseResult, Reading } from "./api";

type Screen = "home" | "analyze" | "house" | "history";
type Message = { role: "user" | "assistant"; text: string };
type SavedEstimate = { id: string; savedAt: string; estimate: Estimate };
type TariffResponse = {
  utility: string;
  total: string;
  base: string;
  flag: string | null;
  valid_until: string;
  notice: string;
};

const DEFAULT_DRAFT: EstimateInput = {
  name: "Aparelho",
  watts: 0,
  minutes: 10,
  days: 30,
  units: 1,
  tariff: 0.9,
};

const NAV: { id: Screen; label: string; icon: LucideIcon }[] = [
  { id: "home", label: "Início", icon: Home },
  { id: "analyze", label: "Analisar aparelho", icon: Camera },
  { id: "house", label: "Minha casa", icon: Home },
  { id: "history", label: "Histórico", icon: History },
];

function readSession<T>(key: string, fallback: T): T {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function ErrorNote({
  message,
  close,
}: {
  message: string;
  close?: () => void;
}) {
  return (
    <div className="alert alert-error" role="alert">
      <Info size={18} />
      <span>{message}</span>
      {close && (
        <button
          className="icon-button"
          aria-label="Fechar aviso"
          onClick={close}
        >
          <X size={16} />
        </button>
      )}
    </div>
  );
}

function Brand({ small = false }: { small?: boolean }) {
  return (
    <div className={"brand " + (small ? "brand-small" : "")}>
      <Bolt className="brand-mark" size={small ? 35 : 42} strokeWidth={2.2} />
      <div>
        <div className="brand-name">
          Custo<span>Claro</span>
        </div>
        {!small && <div className="brand-tagline">Entenda sua energia.</div>}
      </div>
    </div>
  );
}

function uploadImage(file: File): Promise<File> {
  return new Promise((resolve, reject) => {
    if (!file.type.startsWith("image/")) {
      reject(new Error("Escolha uma imagem."));
      return;
    }
    if (file.size > 20 * 1024 * 1024) {
      reject(
        new Error("Esta imagem é muito grande. Use uma foto de até 20 MB."),
      );
      return;
    }
    const image = new Image();
    const url = URL.createObjectURL(file);
    image.onload = () => {
      URL.revokeObjectURL(url);
      const scale = Math.min(
        1,
        1600 / Math.max(image.naturalWidth, image.naturalHeight),
      );
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        reject(new Error("Não consegui preparar a foto."));
        return;
      }
      ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error("Não consegui comprimir a foto."));
            return;
          }
          if (blob.size > 4 * 1024 * 1024) {
            reject(
              new Error(
                "A foto continua muito grande. Tente uma resolução menor.",
              ),
            );
            return;
          }
          resolve(new File([blob], "etiqueta.jpg", { type: "image/jpeg" }));
        },
        "image/jpeg",
        0.82,
      );
    };
    image.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Não consegui abrir esta imagem."));
    };
    image.src = url;
  });
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("home");
  const [menuOpen, setMenuOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [aiOnline, setAiOnline] = useState<boolean | null>(null);
  const [draft, setDraft] = useState<EstimateInput>(DEFAULT_DRAFT);
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [reading, setReading] = useState<Reading | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [house, setHouse] = useState<EstimateInput[]>(() =>
    readSession("custo-house", []),
  );
  const [houseEstimate, setHouseEstimate] = useState<HouseResult | null>(null);
  const [history, setHistory] = useState<SavedEstimate[]>(() =>
    readSession("custo-history", []),
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [utilityQuery, setUtilityQuery] = useState("");
  const [distributors, setDistributors] = useState<string[]>([]);
  const [selectedUtility, setSelectedUtility] = useState("");
  const [locationText, setLocationText] = useState("");
  const [tariffInfo, setTariffInfo] = useState(
    "Exemplo: R$ 0,90/kWh. Ajuste pela sua fatura.",
  );
  const [settingsBusy, setSettingsBusy] = useState(false);
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    request<{ ai_available: boolean }>("/api/health")
      .then((data) => setAiOnline(data.ai_available))
      .catch(() => setAiOnline(false));
  }, []);
  useEffect(() => {
    try {
      sessionStorage.setItem("custo-house", JSON.stringify(house));
    } catch {
      /* session-only fallback */
    }
  }, [house]);
  useEffect(() => {
    try {
      sessionStorage.setItem("custo-history", JSON.stringify(history));
    } catch {
      /* session-only fallback */
    }
  }, [history]);

  useEffect(() => {
    if (screen !== "analyze" || !confirmed || draft.watts <= 0) {
      setEstimate(null);
      return;
    }
    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      postJson<Estimate>("/api/estimate", draft, controller.signal)
        .then(setEstimate)
        .catch((exc) => {
          if (exc.name !== "AbortError") {
            setEstimate(null);
            setError(exc.message);
          }
        });
    }, 180);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [draft, confirmed, screen]);

  useEffect(() => {
    if (!house.length) {
      setHouseEstimate(null);
      return;
    }
    const controller = new AbortController();
    postJson<HouseResult>("/api/house", house, controller.signal)
      .then(setHouseEstimate)
      .catch((exc) => {
        if (exc.name !== "AbortError") setError(exc.message);
      });
    return () => controller.abort();
  }, [house]);
  useEffect(() => {
    chatBottomRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "nearest",
    });
  }, [messages, sending]);

  function navigate(next: Screen) {
    setScreen(next);
    setMenuOpen(false);
    setError("");
  }
  function changeDraft<K extends keyof EstimateInput>(
    key: K,
    value: EstimateInput[K],
  ) {
    setDraft((previous) => ({ ...previous, [key]: value }));
    setError("");
  }
  function startManual() {
    setReading(null);
    setPreview(null);
    setEstimate(null);
    setConfirmed(true);
    setDraft((previous) => ({
      ...DEFAULT_DRAFT,
      tariff: previous.tariff,
      days: previous.days,
    }));
    navigate("analyze");
  }

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    setError("");
    setUploading(true);
    setReading(null);
    setEstimate(null);
    setConfirmed(false);
    const url = URL.createObjectURL(file);
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old);
      return url;
    });
    navigate("analyze");
    try {
      const optimized = await uploadImage(file);
      const data = new FormData();
      data.append("file", optimized);
      const result = await request<Reading>("/api/analyze", {
        method: "POST",
        body: data,
      });
      setReading(result);
      setDraft((previous) => ({
        ...previous,
        name: result.appliance || "Aparelho",
        watts: Number(result.power_watts) || 0,
      }));
      if (!result.power_watts)
        setError(
          "A foto não mostrou uma potência inequívoca. Informe os watts manualmente.",
        );
    } catch (exc) {
      setError(
        exc instanceof Error ? exc.message : "Não foi possível ler a foto.",
      );
    } finally {
      setUploading(false);
    }
  }

  async function sendMessage(custom?: string) {
    const text = (custom ?? question).trim();
    if (!text || sending) return;
    setQuestion("");
    setMessages((previous) => [...previous, { role: "user", text }]);
    setSending(true);
    try {
      const data = await postJson<{ reply: string }>("/api/chat", {
        question: text,
        appliance:
          screen === "analyze" && confirmed && draft.watts > 0 ? draft : null,
        house: screen === "house" ? house : [],
      });
      setMessages((previous) => [
        ...previous,
        { role: "assistant", text: data.reply },
      ]);
    } catch {
      setMessages((previous) => [
        ...previous,
        {
          role: "assistant",
          text: "Não consegui responder agora. Seus cálculos continuam disponíveis; tente novamente em instantes.",
        },
      ]);
    } finally {
      setSending(false);
    }
  }

  function addHouse() {
    if (!estimate || house.length >= 30) return;
    setHouse((previous) => [...previous, { ...draft }]);
    navigate("house");
  }
  function saveCurrent() {
    if (!estimate) return;
    setHistory((previous) =>
      [
        {
          id: crypto.randomUUID(),
          savedAt: new Date().toISOString(),
          estimate,
        },
        ...previous,
      ].slice(0, 30),
    );
  }
  function updateTariff(value: number) {
    const tariff = Math.max(0, Math.min(1000, value || 0));
    setDraft((previous) => ({ ...previous, tariff }));
    setHouse((previous) => previous.map((item) => ({ ...item, tariff })));
    setTariffInfo("Tarifa informada por você. Confira os tributos na fatura.");
  }
  function updateDays(days: number) {
    setDraft((previous) => ({ ...previous, days }));
    setHouse((previous) => previous.map((item) => ({ ...item, days })));
  }
  async function searchUtilities() {
    setSettingsBusy(true);
    setError("");
    try {
      const data = await request<{ items: string[] }>(
        "/api/distributors?q=" + encodeURIComponent(utilityQuery),
      );
      setDistributors(data.items);
      setSelectedUtility(data.items[0] || "");
      if (!data.items.length)
        setError("Nenhuma distribuidora encontrada. Confira o nome na conta.");
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSettingsBusy(false);
    }
  }
  async function useUtility() {
    if (!selectedUtility) return;
    setSettingsBusy(true);
    try {
      const data = await request<TariffResponse>(
        "/api/tariff?utility=" + encodeURIComponent(selectedUtility),
      );
      const rate = Number(data.total);
      updateTariff(rate);
      setTariffInfo(
        "ANEEL · " +
          data.utility +
          (data.flag
            ? " · bandeira " + data.flag
            : " · bandeira não confirmada") +
          " · até " +
          data.valid_until +
          ". Impostos não incluídos.",
      );
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSettingsBusy(false);
    }
  }
  function detectLocation() {
    if (!navigator.geolocation) {
      setError("Localização indisponível neste navegador.");
      return;
    }
    setSettingsBusy(true);
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const data = await postJson<{ city: string; state: string }>(
            "/api/location",
            {
              latitude: Math.round(position.coords.latitude * 100) / 100,
              longitude: Math.round(position.coords.longitude * 100) / 100,
            },
          );
          setLocationText([data.city, data.state].filter(Boolean).join(", "));
        } catch (exc) {
          setError((exc as Error).message);
        } finally {
          setSettingsBusy(false);
        }
      },
      () => {
        setError(
          "Não foi possível acessar a localização. Você pode procurar a distribuidora manualmente.",
        );
        setSettingsBusy(false);
      },
      { enableHighAccuracy: false, timeout: 10000 },
    );
  }

  const title =
    screen === "home"
      ? "Visão geral"
      : screen === "analyze"
        ? "Analisar aparelho"
        : screen === "house"
          ? "Energia da minha casa"
          : "Histórico";
  const suggestions =
    screen === "house"
      ? ["Qual aparelho mais pesa na conta?", "Como reduzir o consumo?"]
      : screen === "analyze" && estimate
        ? ["E se eu usar só 5 minutos?", "Como esse valor foi calculado?"]
        : ["Como funciona?", "Analisar minha casa"];

  return (
    <div className="shell">
      <aside className={"sidebar " + (menuOpen ? "sidebar-open" : "")}>
        <Brand small />
        <nav aria-label="Navegação principal" className="side-nav">
          {NAV.map((item) => (
            <button
              key={item.id}
              className={"nav-item " + (screen === item.id ? "active" : "")}
              onClick={() => navigate(item.id)}
            >
              <item.icon size={20} strokeWidth={1.9} /> {item.label}
            </button>
          ))}
          <button
            className="nav-item"
            onClick={() => {
              setSettingsOpen(true);
              setMenuOpen(false);
            }}
          >
            <Settings2 size={20} /> Configurações
          </button>
        </nav>
        <p className="sidebar-foot">Seu consumo, mais claro.</p>
      </aside>
      {menuOpen && (
        <button
          className="menu-shade"
          aria-label="Fechar menu"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <div className="content-shell">
        <header className="mobile-header">
          <button
            className="icon-button"
            aria-label="Abrir menu"
            onClick={() => setMenuOpen(true)}
          >
            <Menu size={23} />
          </button>
          <Brand small />
          <button
            className="icon-button"
            aria-label="Configurações"
            onClick={() => setSettingsOpen(true)}
          >
            <SlidersHorizontal size={22} />
          </button>
        </header>
        <div className="mobile-quicknav">
          <button
            className={screen === "home" ? "selected" : ""}
            onClick={() => navigate("home")}
          >
            Início
          </button>
          <button
            className={screen === "house" ? "selected" : ""}
            onClick={() => navigate("house")}
          >
            Minha casa{house.length ? " (" + house.length + ")" : ""}
          </button>
        </div>
        <div className="page-head">
          <h1>{title}</h1>
          <span
            className={"status-pill " + (aiOnline === false ? "offline" : "")}
          >
            {aiOnline === false ? (
              <CloudOff size={13} />
            ) : (
              <span className="status-dot" />
            )}
            {aiOnline === null
              ? "Conectando..."
              : aiOnline
                ? "IA disponível"
                : "Modo manual"}
          </span>
        </div>
        {error && !settingsOpen && (
          <ErrorNote message={error} close={() => setError("")} />
        )}
        <div className="work-layout">
          <main className="main-column">
            {screen === "home" && (
              <>
                <section className="hero card">
                  <div className="hero-copy">
                    <span className="eyebrow">
                      CUSTOCLARO · INTELIGÊNCIA EM ENERGIA
                    </span>
                    <h2>
                      Entenda quanto sua <em>energia custa.</em>
                    </h2>
                    <p>
                      Fotografe uma etiqueta, descubra o consumo e converse com
                      a IA.
                    </p>
                    <div className="upload-actions">
                      <button
                        className="upload-action primary"
                        onClick={() => cameraRef.current?.click()}
                      >
                        <Camera size={27} />
                        <span>
                          <strong>Tirar foto</strong>
                          <small>Use a câmera do seu aparelho</small>
                        </span>
                        <ChevronRight size={18} />
                      </button>
                      <button
                        className="upload-action"
                        onClick={() => galleryRef.current?.click()}
                      >
                        <ImagePlus size={27} />
                        <span>
                          <strong>Enviar imagem</strong>
                          <small>Escolha uma foto da etiqueta</small>
                        </span>
                        <ChevronRight size={18} />
                      </button>
                    </div>
                    <button className="text-link" onClick={startManual}>
                      <Pencil size={15} /> Informar potência manualmente
                    </button>
                  </div>
                  <div className="hero-art" aria-hidden="true">
                    <div className="label-illustration">
                      <span>Energia</span>
                      <small>Etiqueta de exemplo</small>
                      <div className="label-lines" />
                      <div className="energy-bars">
                        <i />
                        <i />
                        <i />
                        <i />
                        <i />
                      </div>
                      <b>W</b>
                    </div>
                  </div>
                </section>
                <section className="card how-card">
                  <div className="section-title">
                    <h3>Como funciona</h3>
                    <p>
                      Em poucos passos, você entende o custo dos seus aparelhos.
                    </p>
                  </div>
                  <div className="steps-grid">
                    <div>
                      <span className="step-icon">
                        <Camera size={23} />
                      </span>
                      <b>1. Foto</b>
                      <p>Capture a placa elétrica do aparelho.</p>
                    </div>
                    <div>
                      <span className="step-icon">
                        <FileText size={23} />
                      </span>
                      <b>2. Potência</b>
                      <p>A IA extrai os watts para você conferir.</p>
                    </div>
                    <div>
                      <span className="step-icon">
                        <BarChart3 size={23} />
                      </span>
                      <b>3. Custo</b>
                      <p>Simule o consumo usando sua tarifa.</p>
                    </div>
                  </div>
                </section>
                <section className="card example-card">
                  <div className="section-title">
                    <h3>Exemplo de cálculo</h3>
                    <p>Ilustrativo · tarifa de R$ 0,90/kWh, 30 dias de uso.</p>
                  </div>
                  <div className="example-content">
                    <span className="device-icon">
                      <Activity size={24} />
                    </span>
                    <div>
                      <b>Chuveiro elétrico</b>
                      <small>5.500 W · 10 minutos/dia</small>
                    </div>
                    <div className="example-number">
                      <b>R$ 24,75</b>
                      <small>por mês</small>
                    </div>
                    <button
                      className="round-next"
                      aria-label="Experimentar exemplo"
                      onClick={() => {
                        setReading(null);
                        setPreview(null);
                        setConfirmed(true);
                        setDraft((previous) => ({
                          ...previous,
                          name: "Chuveiro elétrico",
                          watts: 5500,
                          minutes: 10,
                          units: 1,
                        }));
                        navigate("analyze");
                      }}
                    >
                      <ArrowRight size={19} />
                    </button>
                  </div>
                </section>
              </>
            )}

            {screen === "analyze" && (
              <>
                <section className="card analysis-intro">
                  <div className="analysis-heading">
                    <span className="square-icon">
                      <Camera size={22} />
                    </span>
                    <div>
                      <h2>Da etiqueta ao custo.</h2>
                      <p>
                        Revise a potência, ajuste o tempo e veja sua estimativa.
                      </p>
                    </div>
                  </div>
                  <div className="secondary-actions">
                    <button onClick={() => cameraRef.current?.click()}>
                      <Camera size={18} /> Tirar foto
                    </button>
                    <button onClick={() => galleryRef.current?.click()}>
                      <ImagePlus size={18} /> Enviar imagem
                    </button>
                  </div>
                  {preview && (
                    <div className="photo-line">
                      <img src={preview} alt="Foto da etiqueta selecionada" />
                      <div>
                        {uploading ? (
                          <>
                            <LoaderCircle className="spin" size={20} />
                            <strong>Analisando a etiqueta...</strong>
                            <small>
                              Aguarde enquanto a IA encontra a potência.
                            </small>
                          </>
                        ) : reading ? (
                          <>
                            <CheckCircle2 className="success-text" size={22} />
                            <strong>Etiqueta analisada</strong>
                            <small>
                              {reading.evidence ||
                                "Nenhuma evidência textual encontrada."}
                            </small>
                            <small>Confiança: {reading.confidence}</small>
                          </>
                        ) : (
                          <>
                            <Info size={21} />
                            <strong>Foto selecionada</strong>
                            <small>
                              Você pode informar a potência manualmente.
                            </small>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                  {reading?.notes && (
                    <p className="reading-notes">{reading.notes}</p>
                  )}
                </section>
                <section className="card params-card">
                  <div className="card-title">
                    <SlidersHorizontal size={21} />
                    <h3>Cálculo e parâmetros</h3>
                  </div>
                  <div className="input-grid">
                    <label>
                      Nome do aparelho
                      <input
                        value={draft.name}
                        maxLength={120}
                        onChange={(event) =>
                          changeDraft("name", event.target.value)
                        }
                      />
                    </label>
                    <label>
                      Potência (W)
                      <input
                        type="number"
                        min="0"
                        max="1000000"
                        step="1"
                        value={draft.watts || ""}
                        placeholder="Ex.: 5500"
                        onChange={(event) => {
                          changeDraft("watts", Number(event.target.value));
                          if (reading) setConfirmed(false);
                        }}
                      />
                    </label>
                  </div>
                  {reading && !confirmed && draft.watts > 0 && (
                    <button
                      className="confirm-button"
                      onClick={() => setConfirmed(true)}
                    >
                      <Check size={18} /> Confirmar potência de{" "}
                      {formatDecimal(draft.watts, 0)} W
                    </button>
                  )}
                  <div className="range-label">
                    <span>Uso diário</span>
                    <strong>{formatDecimal(draft.minutes, 0)} min</strong>
                  </div>
                  <input
                    className="time-slider"
                    type="range"
                    min="0"
                    max="180"
                    step="5"
                    value={Math.min(180, draft.minutes)}
                    onChange={(event) =>
                      changeDraft("minutes", Number(event.target.value))
                    }
                    aria-label="Minutos de uso por dia"
                  />
                  <div className="param-row">
                    <span>Minutos exatos por dia</span>
                    <input
                      className="short-input"
                      aria-label="Minutos exatos por dia"
                      type="number"
                      min="0"
                      max="1440"
                      value={draft.minutes}
                      onChange={(event) =>
                        changeDraft("minutes", Number(event.target.value))
                      }
                    />
                  </div>
                  <button
                    className="tariff-line"
                    onClick={() => setSettingsOpen(true)}
                  >
                    <FileText size={19} />
                    <span>
                      Tarifa estimada: R$ {formatDecimal(draft.tariff)}/kWh
                    </span>
                    <strong>Editar</strong>
                    <ChevronRight size={17} />
                  </button>
                </section>
                {confirmed && estimate ? (
                  <section className="card result-card">
                    <div className="result-eyebrow">
                      <Activity size={19} /> {draft.name}
                    </div>
                    <div className="big-value">
                      {estimate.monthly_brl_label}
                    </div>
                    <p className="result-caption">Estimativa por mês</p>
                    <div className="metrics-row">
                      <div>
                        <Bolt size={22} />
                        <span>
                          <b>{estimate.monthly_kwh_label}/mês</b>
                          <small>Consumo estimado</small>
                        </span>
                      </div>
                      <div>
                        <BarChart3 size={22} />
                        <span>
                          <b>{estimate.annual_brl_label}/ano</b>
                          <small>12 meses iguais</small>
                        </span>
                      </div>
                    </div>
                    <div className="result-actions">
                      <button className="primary-button" onClick={addHouse}>
                        <Plus size={18} /> Adicionar à minha casa
                      </button>
                      <button className="outline-button" onClick={saveCurrent}>
                        <History size={18} /> Salvar análise
                      </button>
                    </div>
                    <p className="fineprint">
                      Estimativa, não medição. A potência pode variar durante o
                      funcionamento; tributos e iluminação pública podem não
                      estar incluídos.
                    </p>
                  </section>
                ) : (
                  <section className="card waiting-card">
                    <Lightbulb size={23} />
                    <div>
                      <strong>
                        {uploading
                          ? "Analisando sua fotografia"
                          : reading && !confirmed
                            ? "Confirme a potência encontrada"
                            : "Informe a potência para começar"}
                      </strong>
                      <p>
                        O cálculo aparecerá aqui assim que os watts forem
                        informados e confirmados.
                      </p>
                    </div>
                  </section>
                )}
              </>
            )}

            {screen === "house" && (
              <>
                <p className="page-description">
                  Compare aparelhos e descubra onde economizar.
                </p>
                <div className="summary-grid">
                  <div className="card summary-card">
                    <span>
                      <Wallet size={19} /> Custo mensal estimado
                    </span>
                    <strong>
                      {houseEstimate?.total_brl_label ?? "R$ 0,00"}
                    </strong>
                    <small>
                      {house.length
                        ? house.length + " aparelho(s) na simulação"
                        : "Adicione seus aparelhos"}
                    </small>
                  </div>
                  <div className="card summary-card">
                    <span>
                      <BarChart3 size={19} /> Consumo mensal
                    </span>
                    <strong>
                      {houseEstimate?.total_kwh_label ?? "0,00 kWh"}
                    </strong>
                    <small>Baseado nos aparelhos cadastrados</small>
                  </div>
                </div>
                <section className="card house-table">
                  <div className="section-title">
                    <h3>Aparelhos da minha casa</h3>
                    <p>
                      Valores estimados, atualizados com a tarifa informada.
                    </p>
                  </div>
                  {house.length && houseEstimate ? (
                    <div className="house-rows">
                      <div className="house-row house-header">
                        <span>Aparelho</span>
                        <span>Potência</span>
                        <span>Uso diário</span>
                        <span>Custo mensal</span>
                        <span />
                      </div>
                      {houseEstimate.items.map((item, index) => (
                        <div className="house-row" key={index}>
                          <span className="house-appliance">
                            <span className="device-icon small">
                              <Bolt size={20} />
                            </span>
                            <strong>{item.name}</strong>
                          </span>
                          <span>{formatDecimal(Number(item.watts), 0)} W</span>
                          <span>{item.minutes} min/dia</span>
                          <span className="cost-cell">
                            <strong>{item.monthly_brl_label}</strong>
                            <span className="cost-track">
                              <i
                                style={{
                                  width:
                                    Math.max(
                                      5,
                                      (Number(item.monthly_brl) /
                                        Math.max(
                                          1,
                                          ...houseEstimate.items.map((row) =>
                                            Number(row.monthly_brl),
                                          ),
                                        )) *
                                        100,
                                    ) + "%",
                                }}
                              />
                            </span>
                          </span>
                          <button
                            aria-label={"Remover " + item.name}
                            className="icon-button delete-button"
                            onClick={() =>
                              setHouse((previous) =>
                                previous.filter((_, i) => i !== index),
                              )
                            }
                          >
                            <Trash2 size={18} />
                          </button>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-state">
                      <Home size={35} />
                      <h3>Sua casa ainda está vazia.</h3>
                      <p>
                        Adicione o primeiro aparelho para começar a comparar o
                        consumo.
                      </p>
                    </div>
                  )}
                  <button className="add-appliance" onClick={startManual}>
                    <Plus size={20} /> Adicionar aparelho
                  </button>
                </section>
                <p className="fineprint">
                  A conta real pode incluir consumos não cadastrados, impostos e
                  tarifas específicas.
                </p>
              </>
            )}

            {screen === "history" && (
              <section className="card history-panel">
                <div className="section-title">
                  <h3>Simulações salvas</h3>
                  <p>
                    Guardadas apenas nesta sessão do navegador, sem fotos ou
                    chaves.
                  </p>
                </div>
                {history.length ? (
                  history.map((item) => (
                    <div className="history-row" key={item.id}>
                      <span className="device-icon small">
                        <Clock3 size={19} />
                      </span>
                      <div>
                        <strong>{item.estimate.name}</strong>
                        <small>
                          {new Date(item.savedAt).toLocaleString("pt-BR")}
                        </small>
                      </div>
                      <b>{item.estimate.monthly_brl_label}/mês</b>
                      <button
                        className="icon-button"
                        aria-label="Remover análise"
                        onClick={() =>
                          setHistory((previous) =>
                            previous.filter((row) => row.id !== item.id),
                          )
                        }
                      >
                        <Trash2 size={18} />
                      </button>
                    </div>
                  ))
                ) : (
                  <div className="empty-state">
                    <History size={35} />
                    <h3>Nenhuma análise salva.</h3>
                    <p>
                      Após calcular um aparelho, você poderá salvar o resultado
                      aqui.
                    </p>
                  </div>
                )}
                <button
                  className="outline-button"
                  onClick={() => navigate("analyze")}
                >
                  Nova análise <ArrowRight size={17} />
                </button>
              </section>
            )}
          </main>

          <aside className="assistant card" aria-label="Assistente CustoClaro">
            <div className="assistant-heading">
              <span className="assistant-symbol">
                <Sparkles size={22} />
              </span>
              <h3>Assistente CustoClaro</h3>
              <span
                className={"online-status " + (aiOnline ? "" : "unavailable")}
              >
                <span className="status-dot" />
                {aiOnline ? "Online" : "Guias locais"}
              </span>
            </div>
            <div className="assistant-messages" aria-live="polite">
              {!messages.length && (
                <div className="welcome-message">
                  <div className="bot-mark">
                    <Bolt size={21} />
                  </div>
                  <div className="bubble assistant-bubble">
                    Olá! Posso analisar uma etiqueta, explicar sua conta de
                    energia ou ajudar a encontrar os aparelhos que mais consomem
                    na sua casa.
                  </div>
                </div>
              )}
              {messages.map((message, index) => (
                <div className={"message " + message.role} key={index}>
                  {message.role === "assistant" && (
                    <span className="bot-mark">
                      <Bolt size={19} />
                    </span>
                  )}
                  <div className="bubble">{message.text}</div>
                </div>
              ))}
              {sending && (
                <div className="message assistant">
                  <span className="bot-mark">
                    <Bolt size={19} />
                  </span>
                  <div className="bubble typing">
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
              )}
              <div ref={chatBottomRef} />
            </div>
            <div className="assistant-bottom">
              <div className="suggestions">
                {suggestions.map((label) => (
                  <button
                    key={label}
                    onClick={() => sendMessage(label)}
                    disabled={sending}
                  >
                    {label}
                    <ChevronRight size={15} />
                  </button>
                ))}
              </div>
              <form
                className="chat-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  void sendMessage();
                }}
              >
                <input
                  aria-label="Pergunte ao assistente"
                  placeholder={
                    screen === "house"
                      ? "Pergunte sobre sua casa..."
                      : "Pergunte sobre energia..."
                  }
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  maxLength={800}
                />
                <button
                  type="submit"
                  disabled={!question.trim() || sending}
                  aria-label="Enviar mensagem"
                >
                  <Send size={19} />
                </button>
              </form>
            </div>
          </aside>
        </div>
      </div>

      <input
        ref={cameraRef}
        className="visually-hidden"
        type="file"
        accept="image/*"
        capture="environment"
        onChange={onFile}
      />
      <input
        ref={galleryRef}
        className="visually-hidden"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        onChange={onFile}
      />

      {settingsOpen && (
        <div
          className="modal-backdrop"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setSettingsOpen(false);
          }}
        >
          <div
            className="settings-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="settings-title"
          >
            <div className="modal-head">
              <div>
                <h2 id="settings-title">Configurações</h2>
                <p>Personalize a estimativa para sua realidade.</p>
              </div>
              <button
                className="icon-button"
                aria-label="Fechar configurações"
                onClick={() => {
                  setSettingsOpen(false);
                  setError("");
                }}
              >
                <X size={22} />
              </button>
            </div>
            {error && <ErrorNote message={error} close={() => setError("")} />}
            <div className="settings-section">
              <h3>
                <Bolt size={18} /> Tarifa e período
              </h3>
              <div className="input-grid">
                <label>
                  Tarifa (R$/kWh)
                  <input
                    type="number"
                    min="0"
                    max="1000"
                    step="0.01"
                    value={draft.tariff}
                    onChange={(event) =>
                      updateTariff(Number(event.target.value))
                    }
                  />
                </label>
                <label>
                  Dias de uso por mês
                  <input
                    type="number"
                    min="1"
                    max="31"
                    step="1"
                    value={draft.days}
                    onChange={(event) =>
                      updateDays(
                        Math.max(
                          1,
                          Math.min(31, Number(event.target.value) || 1),
                        ),
                      )
                    }
                  />
                </label>
              </div>
              <p className="setting-note">{tariffInfo}</p>
            </div>
            <div className="settings-section">
              <h3>
                <MapPin size={18} /> Sua região
              </h3>
              <p>
                Localização opcional. A região não identifica automaticamente a
                distribuidora da sua conta.
              </p>
              <button
                className="outline-button"
                onClick={detectLocation}
                disabled={settingsBusy}
              >
                <MapPin size={17} />{" "}
                {locationText || "Identificar região aproximada"}
              </button>
              <div className="utility-search">
                <input
                  placeholder="Distribuidora na sua fatura"
                  value={utilityQuery}
                  onChange={(event) => setUtilityQuery(event.target.value)}
                  maxLength={80}
                />
                <button
                  className="outline-button"
                  onClick={searchUtilities}
                  disabled={utilityQuery.trim().length < 3 || settingsBusy}
                >
                  Buscar
                </button>
              </div>
              {!!distributors.length && (
                <div className="utility-choice">
                  <select
                    aria-label="Confirme sua distribuidora"
                    value={selectedUtility}
                    onChange={(event) => setSelectedUtility(event.target.value)}
                  >
                    {distributors.map((item) => (
                      <option key={item}>{item}</option>
                    ))}
                  </select>
                  <button
                    className="primary-button"
                    onClick={useUtility}
                    disabled={settingsBusy}
                  >
                    Aplicar tarifa ANEEL
                  </button>
                </div>
              )}
            </div>
            <div className="settings-section secure-section">
              <h3>
                <ShieldCheck size={19} /> Integração com IA
              </h3>
              <p>
                {aiOnline
                  ? "A IA está configurada no servidor. Não é necessário inserir uma chave."
                  : "Sem chave Gemini configurada no servidor. O cálculo manual continua disponível."}
              </p>
            </div>
            <button
              className="primary-button modal-done"
              onClick={() => {
                setSettingsOpen(false);
                setError("");
              }}
            >
              Concluir <Check size={18} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
