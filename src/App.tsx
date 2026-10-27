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
  MessageCircle,
  Pencil,
  Plus,
  Search,
  Send,
  Settings2,
  ShoppingBag,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  Wallet,
  X,
} from "lucide-react";
import { formatDecimal, formatPower, postJson, request } from "./api";
import type { Estimate, EstimateInput, HouseResult, ProductResult, ProductSearchResult, Reading } from "./api";
import Explore from "./Explore";
import type { ExploreContext, ExploreMode, Product } from "./Explore";

type Screen = "home" | "nomnom" | "products" | "explore" | "analyze" | "house" | "history";
type ToolAction = "products" | "compare" | "forecast" | "analyze" | "house";
type Message = { role: "user" | "assistant"; text: string; action?: ToolAction; houseProposal?: EstimateInput };
type SavedEstimate = { id: string; savedAt: string; estimate: Estimate };
type TariffResponse = {
  utility: string;
  total: string;
  base: string;
  flag: string | null;
  valid_until: string;
  notice: string;
};
type UtilityMatch = { utility: string; confidence: "alta"; basis: string; source: string };
type ApproximateRegion = { city: string; state: string; distributor: UtilityMatch | null };

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
  { id: "nomnom", label: "Nom Nom · IA", icon: MessageCircle },
  { id: "explore", label: "Quanto isso consome?", icon: Search },
  { id: "products", label: "Produtos e lojas", icon: ShoppingBag },
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

function readPersistent<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : readSession(key, fallback);
  } catch {
    return readSession(key, fallback);
  }
}

function validHouseItem(item: EstimateInput): boolean {
  return Boolean(item.name.trim()) && item.name.length <= 120 &&
    Number.isInteger(item.units) && item.units >= 1 && item.units <= 1000 &&
    Number.isInteger(item.days) && item.days >= 1 && item.days <= 31 &&
    Number.isFinite(item.tariff) && item.tariff >= 0 && item.tariff <= 1000 &&
    (item.label_kwh_month != null
      ? Number.isFinite(item.label_kwh_month) && item.label_kwh_month > 0 && item.label_kwh_month <= 1000000
      : Number.isFinite(item.watts) && item.watts > 0 && item.watts <= 1000000 &&
        Number.isFinite(item.minutes) && item.minutes >= 0 && item.minutes <= 1440);
}

function normalizeHouseItem(item: EstimateInput): EstimateInput {
  // Decimal values are serialized as strings by the API; normalize before validation.
  return {
    name: String(item.name || ""),
    watts: Number(item.watts),
    label_kwh_month: item.label_kwh_month == null ? null : Number(item.label_kwh_month),
    minutes: Number(item.minutes),
    days: Number(item.days),
    units: Number(item.units),
    tariff: Number(item.tariff),
  };
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
      <img
        className="brand-logo"
        src="/nomnom-logo.png"
        alt=""
        aria-hidden="true"
        width={small ? 35 : 42}
        height={small ? 35 : 42}
      />
      <div>
        <div className="brand-name">
          Watt<span>Cola</span>
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
  const [draft, setDraft] = useState<EstimateInput>(() => ({
    ...DEFAULT_DRAFT, tariff: readPersistent("custo-tariff", 0.9),
  }));
  const [estimate, setEstimate] = useState<Estimate | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const [reading, setReading] = useState<Reading | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [house, setHouse] = useState<EstimateInput[]>(() =>
    readPersistent("custo-house", []),
  );
  const [houseFormOpen, setHouseFormOpen] = useState(false);
  const [editingHouseIndex, setEditingHouseIndex] = useState<number | null>(null);
  const [houseDraft, setHouseDraft] = useState<EstimateInput>({ ...DEFAULT_DRAFT, name: "" });
  const [houseEstimate, setHouseEstimate] = useState<HouseResult | null>(null);
  const [history, setHistory] = useState<SavedEstimate[]>(() =>
    readSession("custo-history", []),
  );
  const [messages, setMessages] = useState<Message[]>([]);
  const [exploreMode, setExploreMode] = useState<ExploreMode>("search");
  const [exploreQuery, setExploreQuery] = useState("");
  const [exploreContext, setExploreContext] = useState<ExploreContext>({ selected: null, products: [], forecast: null });
  const [question, setQuestion] = useState("");
  const [sending, setSending] = useState(false);
  const [productQuery, setProductQuery] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [hoursPerDay, setHoursPerDay] = useState("4");
  const [productSort, setProductSort] = useState("consumption");
  const [products, setProducts] = useState<ProductResult[]>([]);
  const [productSearching, setProductSearching] = useState(false);
  const [productSearched, setProductSearched] = useState(false);
  const [productError, setProductError] = useState("");
  const [cameraOpen, setCameraOpen] = useState(false);
  const [cameraBusy, setCameraBusy] = useState(false);
  const [utilityQuery, setUtilityQuery] = useState("");
  const [distributors, setDistributors] = useState<string[]>([]);
  const [selectedUtility, setSelectedUtility] = useState(() => readPersistent("custo-utility", ""));
  const [locationText, setLocationText] = useState(() => readPersistent("custo-region", ""));
  const [tariffInfo, setTariffInfo] = useState(() => readPersistent(
    "custo-tariff-info", "Tarifa inicial ilustrativa. Identifique sua distribuidora para atualizar.",
  ));
  const [settingsBusy, setSettingsBusy] = useState(false);
  const [locationStatus, setLocationStatus] = useState("");
  const geolocationAttempted = useRef(false);
  const cameraRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);
  const cameraVideoRef = useRef<HTMLVideoElement>(null);
  const cameraStreamRef = useRef<MediaStream | null>(null);
  const chatScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    request<{ ai_available: boolean }>("/api/health")
      .then((data) => setAiOnline(data.ai_available))
      .catch(() => setAiOnline(false));
  }, []);
  useEffect(() => {
    try {
      localStorage.setItem("custo-house", JSON.stringify(house));
    } catch {
      /* The user can still simulate without browser storage. */
    }
  }, [house]);
  useEffect(() => {
    try {
      localStorage.setItem("custo-tariff", JSON.stringify(draft.tariff));
      localStorage.setItem("custo-utility", JSON.stringify(selectedUtility));
      localStorage.setItem("custo-region", JSON.stringify(locationText));
      localStorage.setItem("custo-tariff-info", JSON.stringify(tariffInfo));
    } catch { /* Storage is optional. */ }
  }, [draft.tariff, selectedUtility, locationText, tariffInfo]);
  useEffect(() => {
    // Reuse a location permission already granted, without prompting again.
    if (geolocationAttempted.current || !navigator.geolocation || !navigator.permissions) return;
    geolocationAttempted.current = true;
    navigator.permissions.query({ name: "geolocation" }).then((permission) => {
      if (permission.state === "granted") detectLocation();
    }).catch(() => { /* The user can request location via the visible button. */ });
  }, []);
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
    if (chatScrollRef.current) {
      const panel = chatScrollRef.current;
      panel.scrollTop = panel.scrollHeight;
    }
  }, [messages, sending, screen]);

  useEffect(() => {
    if (cameraOpen && cameraVideoRef.current && cameraStreamRef.current) {
      cameraVideoRef.current.srcObject = cameraStreamRef.current;
      void cameraVideoRef.current.play().catch(() => undefined);
    }
  }, [cameraOpen]);

  useEffect(() => () => {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
  }, []);

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

  function openTool(action: ToolAction, query = "") {
    if (action === "house") {
      navigate("house");
      return;
    }
    if (action === "analyze") {
      navigate("analyze");
      return;
    }
    if (action === "compare") setExploreMode("compare");
    else if (action === "forecast") setExploreMode("forecast");
    else setExploreMode("search");
    if (query && action === "products") setExploreQuery(query.slice(0, 120));
    navigate("explore");
  }

  async function processFile(file: File) {
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

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (file) void processFile(file);
  }

  function closeCamera() {
    cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
    cameraStreamRef.current = null;
    setCameraOpen(false);
    setCameraBusy(false);
  }

  async function openCamera() {
    if (cameraBusy) return;
    setCameraBusy(true);
    setError("");
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        cameraRef.current?.click();
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: false, video: { facingMode: { ideal: "environment" } },
      });
      cameraStreamRef.current?.getTracks().forEach((track) => track.stop());
      cameraStreamRef.current = stream;
      setCameraOpen(true);
    } catch {
      // Mobile browsers may support the native camera even without WebRTC permission.
      cameraRef.current?.click();
    } finally {
      setCameraBusy(false);
    }
  }

  function captureCamera() {
    const video = cameraVideoRef.current;
    if (!video || !video.videoWidth || !video.videoHeight) {
      setError("A câmera ainda está iniciando. Tente novamente.");
      return;
    }
    const canvas = document.createElement("canvas");
    const scale = Math.min(1, 1600 / Math.max(video.videoWidth, video.videoHeight));
    canvas.width = Math.round(video.videoWidth * scale);
    canvas.height = Math.round(video.videoHeight * scale);
    const context = canvas.getContext("2d");
    if (!context) return;
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((blob) => {
      if (!blob) {
        setError("Não foi possível capturar a foto.");
        return;
      }
      closeCamera();
      void processFile(new File([blob], "etiqueta-camera.jpg", { type: "image/jpeg" }));
    }, "image/jpeg", 0.86);
  }

  async function searchProducts() {
    const query = productQuery.trim();
    if (query.length < 3 || productSearching) return;
    setProductSearching(true);
    setProductSearched(false);
    setProductError("");
    setProducts([]);
    try {
      const result = await postJson<ProductSearchResult>("/api/products/search", {
        query,
        tariff: draft.tariff,
        hours_per_day: Number(hoursPerDay),
        days: draft.days,
        max_price: maxPrice ? Number(maxPrice) : null,
        sort: productSort,
      });
      setProducts(result.products);
      setProductSearched(true);
    } catch (exc) {
      setProductError(exc instanceof Error ? exc.message : "Falha ao pesquisar produtos.");
    } finally {
      setProductSearching(false);
    }
  }

  async function sendMessage(custom?: string) {
    const text = (custom ?? question).trim();
    if (!text || sending) return;
    setQuestion("");
    setMessages((previous) => [...previous, { role: "user", text }]);
    setSending(true);
    try {
      const data = await postJson<{ reply: string; action?: ToolAction; house_proposal?: EstimateInput }>("/api/chat", {
        question: text,
        appliance: confirmed && draft.watts > 0 ? draft : null,
        house,
        tariff: draft.tariff,
        utility: selectedUtility,
        region: locationText,
        product_context: exploreContext,
        products: products.map((product) => ({
          name: product.name,
          monthly_kwh: product.monthly_kwh,
          price_brl: product.price_brl,
        })),
      });
      setMessages((previous) => [
        ...previous,
        { role: "assistant", text: data.reply, action: data.action, houseProposal: data.house_proposal },
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
    if (!estimate || house.length >= 30 || !validHouseItem(draft)) return;
    setHouse((previous) => [...previous, { ...draft }]);
    setMessages((previous) => [...previous, { role: "assistant", text: `${draft.name} foi adicionado à sua casa. Já atualizei a previsão mensal. Você pode me perguntar qual aparelho consome mais.` }]);
    navigate("house");
  }
  function addSelectedProduct(product: Product, hours: number, days: number) {
    if (house.length >= 30) {
      setError("Sua casa já possui o limite de 30 aparelhos.");
      return;
    }
    const item: EstimateInput = {
      name: product.name,
      watts: Number(product.watts) || 0,
      label_kwh_month: product.label_kwh_month == null ? null : Number(product.label_kwh_month),
      minutes: hours * 60,
      days,
      units: 1,
      tariff: draft.tariff,
    };
    if (!validHouseItem(item)) {
      setError("Esse produto ainda não tem um valor energético confiável. Informe a potência manualmente.");
      return;
    }
    setHouse((previous) => [...previous, item]);
    setMessages((previous) => [...previous, { role: "assistant", text: `Adicionei ${product.name} à Minha casa com os valores da simulação. Você pode revisar os dados e ajustar a quantidade.` }]);
    navigate("house");
  }
  function openHouseForm(index: number | null = null) {
    setEditingHouseIndex(index);
    setHouseDraft(index === null ? { ...DEFAULT_DRAFT, name: "", tariff: draft.tariff } : { ...house[index] });
    setHouseFormOpen(true);
  }
  function commitHouseDraft() {
    const item = { ...houseDraft, name: houseDraft.name.trim(), tariff: draft.tariff };
    if (!validHouseItem(item)) {
      setError("Informe nome, consumo e uso válidos (até 24 horas/dia). Confira também a quantidade.");
      return;
    }
    if (editingHouseIndex === null && house.length >= 30) {
      setError("Limite de 30 aparelhos atingido.");
      return;
    }
    setHouse((previous) => editingHouseIndex === null
      ? [...previous, item]
      : previous.map((current, index) => index === editingHouseIndex ? item : current));
    setHouseFormOpen(false);
    setEditingHouseIndex(null);
    setError("");
  }
  function confirmHouseProposal(item: EstimateInput) {
    const next = { ...normalizeHouseItem(item), tariff: draft.tariff };
    if (!validHouseItem(next) || house.length >= 30) {
      setError("Não foi possível adicionar. Revise o limite e os dados do aparelho.");
      return;
    }
    setHouse((previous) => [...previous, next]);
    setMessages((previous) => [...previous, { role: "assistant", text: `${next.name} foi incluído. A previsão de Minha casa foi recalculada com a sua tarifa.` }]);
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
      await applyOfficialUtility(selectedUtility);
    } catch (exc) {
      setError((exc as Error).message);
    } finally {
      setSettingsBusy(false);
    }
  }
  async function applyOfficialUtility(name: string) {
    const data = await request<TariffResponse>(
      "/api/tariff?utility=" + encodeURIComponent(name),
    );
    updateTariff(Number(data.total));
    setSelectedUtility(data.utility);
    setTariffInfo(
      "ANEEL · " + data.utility + (data.flag ? " · bandeira " + data.flag : " · bandeira não confirmada") +
      " · válido até " + data.valid_until + ". Tributos e iluminação não incluídos.",
    );
    setLocationStatus("Distribuidora identificada e tarifa pública aplicada.");
  }
  function detectLocation() {
    if (!navigator.geolocation) {
      setError("Localização indisponível neste navegador.");
      return;
    }
    setSettingsBusy(true);
    setLocationStatus("Identificando sua região e distribuidora...");
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const data = await postJson<ApproximateRegion>(
            "/api/location",
            {
              latitude: Math.round(position.coords.latitude * 100) / 100,
              longitude: Math.round(position.coords.longitude * 100) / 100,
            },
          );
          setLocationText([data.city, data.state].filter(Boolean).join(", "));
          if (data.distributor?.confidence === "alta") {
            setSelectedUtility(data.distributor.utility);
            try {
              await applyOfficialUtility(data.distributor.utility);
            } catch {
              setLocationStatus(`Região identificada: ${data.distributor.utility}. Não consegui consultar a tarifa ANEEL agora.`);
            }
          } else {
            setLocationStatus("Região identificada, mas a distribuidora não pode ser confirmada automaticamente. Consulte sua fatura.");
          }
        } catch (exc) {
          setError((exc as Error).message);
          setLocationStatus("");
        } finally {
          setSettingsBusy(false);
        }
      },
      () => {
        setError(
          "Não foi possível acessar a localização. Você pode procurar a distribuidora manualmente.",
        );
        setSettingsBusy(false);
        setLocationStatus("Sem permissão para localização. A busca por distribuidora continua disponível.");
      },
      { enableHighAccuracy: false, timeout: 10000 },
    );
  }

  const title =
    screen === "home"
      ? "Visão geral"
      : screen === "explore"
        ? "Quanto isso consome?"
      : screen === "nomnom"
        ? "Nom Nom"
        : screen === "products"
          ? "Produtos e lojas"
      : screen === "analyze"
        ? "Analisar aparelho"
        : screen === "house"
          ? "Energia da minha casa"
          : "Histórico";
  const suggestions =
    screen === "house"
      ? ["Qual aparelho mais pesa na conta?", "Quanto minha casa gasta?", "Como adicionar um aparelho?"]
      : screen === "analyze" && estimate
        ? ["E se eu usar só 5 minutos?", "Como esse valor foi calculado?"]
        : ["Como posso economizar energia?", "Qual aparelho consome mais?", "Compare os produtos pesquisados"];

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
            className={screen === "nomnom" ? "selected" : ""}
            onClick={() => navigate("nomnom")}
          >
            Nom Nom
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
        <div className={"work-layout " + (screen === "nomnom" ? "single-layout" : "with-assistant")}>
          <main className="main-column">
            {screen === "home" && (
              <>
                <section className="hero card">
                  <div className="hero-copy">
                    <span className="eyebrow">
                      WATTCOLA · INTELIGÊNCIA EM ENERGIA
                    </span>
                    <h2>
                      Sua energia, <em>explicada pela IA.</em>
                    </h2>
                    <p>
                      Pergunte sobre qualquer aparelho, pesquise pelo modelo e
                      encontre maneiras de gastar menos.
                    </p>
                    <button className="hero-research" onClick={() => openTool("products")}>
                      <Search size={19} /> Quanto isso consome? <ArrowRight size={18} />
                    </button>
                    <button className="text-link" onClick={() => openTool("house")}>
                      <Home size={16} /> Montar minha casa e prever a conta <ArrowRight size={16} />
                    </button>
                    <div className="upload-actions">
                      <button
                        className="upload-action primary"
                        onClick={() => void openCamera()}
                      >
                        <Camera size={27} />
                        <span>
                          <strong>Tirar foto</strong>
                          <small>Deixe a IA analisar a etiqueta</small>
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
                          <small>Descubra o consumo com uma foto</small>
                        </span>
                        <ChevronRight size={18} />
                      </button>
                    </div>
                    <button className="text-link" onClick={startManual}>
                      <Pencil size={15} /> Informar potência manualmente
                    </button>
                    <div className="hero-shortcuts">
                      <button onClick={() => navigate("nomnom")}>
                        <MessageCircle size={17} /> Conversar com Nom Nom
                      </button>
                      <button onClick={() => navigate("products")}>
                        <Search size={17} /> Pesquisar eletrodomésticos
                      </button>
                    </div>
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
              </>
            )}

            {screen === "explore" && (
              <Explore mode={exploreMode} setMode={setExploreMode} prefill={exploreQuery}
                tariff={draft.tariff} onManual={startManual} onContextChange={setExploreContext}
                onAddToHouse={addSelectedProduct}
                onAssistantNote={(text) => setMessages((previous) => [...previous, { role: "assistant", text }])} />
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
                    <button onClick={() => void openCamera()}>
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
                        step="any"
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
                      {formatPower(draft.watts)} W
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
                <section className="card house-intro">
                  <div className="house-intro-copy">
                    <span className="eyebrow"><Sparkles size={15} /> SUA CASA COM AJUDA DA IA</span>
                    <h2>Vamos descobrir para onde vai sua energia?</h2>
                    <p>Me diga quais aparelhos você tem, envie fotos das etiquetas ou pesquise os modelos. Eu organizo tudo para você acompanhar o gasto estimado.</p>
                    <div className="house-quick-actions">
                      <button className="primary-button" onClick={() => openTool("products")}><Search size={17} /> Buscar por nome</button>
                      <button className="outline-button" onClick={() => galleryRef.current?.click()}><Camera size={17} /> Ler etiqueta</button>
                      <button className="outline-button" onClick={() => openHouseForm()}><Plus size={17} /> Informar watts</button>
                    </div>
                  </div>
                  <div className="house-location">
                    <span><MapPin size={17} /> Sua tarifa de energia</span>
                    <strong>{selectedUtility || "Distribuidora a identificar"}</strong>
                    <small>{locationText || "Localização ainda não informada"} · R$ {formatDecimal(draft.tariff)}/kWh</small>
                    {!selectedUtility && <small>Valor inicial ilustrativo, não tarifa oficial.</small>}
                    {locationStatus && <p>{locationStatus}</p>}
                    <button className="text-link" onClick={detectLocation} disabled={settingsBusy}><MapPin size={14} /> {settingsBusy ? "Identificando..." : "Detectar pela minha região"}</button>
                    <button className="text-link" onClick={() => setSettingsOpen(true)}><Settings2 size={14} /> Corrigir distribuidora/tarifa</button>
                  </div>
                </section>
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
                        ? house.reduce((total, item) => total + item.units, 0) + " unidade(s) na simulação"
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
                            <strong>{item.units > 1 ? item.units + "× " : ""}{item.name}</strong>
                          </span>
                          <span>{item.method === "etiqueta_padronizada" ? "Etiqueta" : formatPower(Number(item.watts)) + " W"}</span>
                          <span>{item.method === "etiqueta_padronizada" ? "kWh/mês" : item.minutes + " min/dia"}</span>
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
                          <div className="house-row-actions">
                            <button aria-label={"Editar " + item.name} className="icon-button" onClick={() => openHouseForm(index)}><Pencil size={16} /></button>
                            <button aria-label={"Remover " + item.name} className="icon-button delete-button" onClick={() => setHouse((previous) => previous.filter((_, i) => i !== index))}><Trash2 size={17} /></button>
                          </div>
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
                  <button className="add-appliance" onClick={() => openHouseForm()}>
                    <Plus size={20} /> Adicionar aparelho
                  </button>
                </section>
                {house.length > 0 && houseEstimate && (
                  <section className="card house-insight">
                    <Sparkles size={21} />
                    <div>
                      <strong>Um ponto de atenção</strong>
                      <p>{[...houseEstimate.items].sort((a, b) => Number(b.monthly_brl) - Number(a.monthly_brl))[0].name} representa o maior gasto dos aparelhos cadastrados. Pergunte à IA como reduzi-lo.</p>
                      <button className="text-link" onClick={() => { navigate("nomnom"); void sendMessage("Como reduzir o consumo do aparelho que mais gasta na minha casa?"); }}>Perguntar à Nom Nom <ArrowRight size={14}/></button>
                    </div>
                  </section>
                )}
                <p className="fineprint">
                  Os itens ficam salvos apenas neste navegador, mesmo após fechá-lo. Esta não é uma leitura do medidor: aparelhos ausentes, tributos, iluminação pública e variações de uso não estão incluídos.
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
            {screen === "products" && (
              <section className="card product-panel">
                <div className="product-title">
                  <span className="square-icon"><ShoppingBag size={24} /></span>
                  <div>
                    <h2>Descubra antes de comprar.</h2>
                    <p>Pesquise pelo nome ou modelo. Compare consumo, custo mensal e preços encontrados em lojas.</p>
                  </div>
                </div>
                <form className="product-search-form" onSubmit={(event) => {
                  event.preventDefault();
                  void searchProducts();
                }}>
                  <label className="product-query-label">
                    Nome do eletrodoméstico ou modelo
                    <div className="product-query-control">
                      <Search size={20} />
                      <input
                        aria-label="Pesquisar eletrodoméstico"
                        placeholder="Ex.: geladeira inverter 300 litros"
                        value={productQuery}
                        maxLength={120}
                        onChange={(event) => setProductQuery(event.target.value)}
                      />
                    </div>
                  </label>
                  <div className="product-filters">
                    <label>Preço máximo (R$)
                      <input type="number" min="1" step="1" placeholder="Qualquer preço"
                        value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} />
                    </label>
                    <label>Uso diário (horas)
                      <input type="number" min="0.1" max="24" step="0.5"
                        value={hoursPerDay} onChange={(event) => setHoursPerDay(event.target.value)} />
                    </label>
                    <label>Ordenar por
                      <select value={productSort} onChange={(event) => setProductSort(event.target.value)}>
                        <option value="consumption">Menor consumo</option>
                        <option value="price">Menor preço</option>
                        <option value="efficiency">Eficiência energética</option>
                      </select>
                    </label>
                  </div>
                  <button className="product-submit" type="submit" disabled={productSearching || productQuery.trim().length < 3}>
                    {productSearching ? <LoaderCircle className="spin" size={18} /> : <Search size={18} />}
                    {productSearching ? "Pesquisando fontes..." : "Pesquisar e comparar"}
                  </button>
                </form>
                {productError && <ErrorNote message={productError} close={() => setProductError("")} />}
                {productSearching && <p className="search-notice">A Nom Nom está procurando fichas de produtos e preços. Isso pode levar alguns segundos.</p>}
                {productSearched && !products.length && (
                  <div className="empty-state">
                    <Search size={32} />
                    <h3>Sem resultados verificáveis.</h3>
                    <p>Tente um modelo mais específico ou retire o filtro de preço. A Nom Nom não inventa dados ausentes.</p>
                  </div>
                )}
                {products.length > 0 && (
                  <>
                    <div className="product-results-heading">
                      <h3>{products.length} produto{products.length > 1 ? "s" : ""} encontrado{products.length > 1 ? "s" : ""}</h3>
                      <span>Tarifa usada: R$ {formatDecimal(draft.tariff)}/kWh</span>
                    </div>
                    <div className="product-results">
                      {products.map((product, index) => (
                        <article className="product-card" key={`${product.source_url}-${index}`}>
                          <div className="product-card-head">
                            <span className="product-index">{index + 1}</span>
                            <div><h3>{product.name}</h3><small>{product.model || "Modelo não informado"} · {product.store}</small></div>
                          </div>
                          <div className="product-metrics">
                            <div><span>Estimativa mensal</span><strong>{product.monthly_brl_label || "Indisponível"}</strong></div>
                            <div><span>Consumo/mês</span><strong>{product.monthly_kwh_label || "Não informado"}</strong></div>
                            <div><span>Preço encontrado</span><strong>{product.price_label || "Não informado"}</strong></div>
                          </div>
                          <div className="product-meta">
                            <span>Eficiência: {product.efficiency || "Não informada"}</span>
                            <span>{product.calculation_basis === "etiqueta mensal"
                              ? "Consumo mensal declarado na etiqueta" : product.watts
                                ? `${formatPower(Number(product.watts))} W · ${hoursPerDay} h/dia`
                                : "Consumo não confirmado"}</span>
                          </div>
                          <div className="product-actions">
                            <a href={product.source_url} target="_blank" rel="noopener noreferrer">Conferir fonte <ArrowRight size={15} /></a>
                            {product.watts && <button onClick={() => {
                              setDraft((old) => ({ ...old, name: product.name, watts: Number(product.watts), minutes: Number(hoursPerDay) * 60 }));
                              setReading(null); setConfirmed(true); navigate("analyze");
                            }}>Simular este aparelho</button>}
                          </div>
                        </article>
                      ))}
                    </div>
                    <p className="search-notice">Os dados vêm de resultados de pesquisa e podem mudar. Confirme preço, estoque e especificações na fonte. O cálculo é uma estimativa.</p>
                    <button className="outline-button" onClick={() => {
                      setQuestion("Qual dos produtos pesquisados é mais econômico e por quê?");
                      navigate("nomnom");
                    }}><MessageCircle size={17} /> Perguntar à Nom Nom sobre a comparação</button>
                  </>
                )}
              </section>
            )}
          </main>

          <section className={"assistant card " + (screen === "nomnom" ? "assistant-page" : "assistant-sidebar")} aria-label="Chat com a Nom Nom">
            <div className="assistant-heading">
              <img
                className="assistant-avatar"
                src="/nomnom-logo.png"
                alt="Nom Nom, coala com capacete de eletricista"
              />
              <div className="assistant-identity">
                <h3>Nom Nom</h3>
                <small>Sua assistente de energia e consumo</small>
              </div>
              <span
                className={"online-status " + (aiOnline ? "" : "unavailable")}
              >
                <span className="status-dot" />
                {aiOnline ? "Online" : "Guias locais"}
              </span>
            </div>
            <div className="assistant-messages" aria-live="polite" ref={chatScrollRef}>
              <div className="conversation-inner">
              {!messages.length && (
                <div className="welcome-message">
                  <div className="bot-mark">
                    <img src="/nomnom-logo.png" alt="" />
                  </div>
                  <div className="bubble assistant-bubble">
                    Oi! Sou a Nom Nom. Posso pesquisar o consumo dos aparelhos,
                    comparar modelos, montar sua casa e prever seu gasto mensal.
                    Escolha uma ação ou me pergunte naturalmente.
                    <div className="chat-actions">
                      <button onClick={() => openTool("house")}>Montar minha casa <ArrowRight size={15}/></button>
                      <button onClick={() => openTool("products")}>Quanto isso consome? <ArrowRight size={15}/></button>
                      <button onClick={() => openTool("compare")}>Comparar aparelhos <ArrowRight size={15}/></button>
                      <button onClick={() => openTool("forecast")}>Previsão mensal <ArrowRight size={15}/></button>
                    </div>
                  </div>
                </div>
              )}
              {messages.map((message, index) => (
                <div className={"message " + message.role} key={index}>
                  {message.role === "assistant" && (
                    <span className="bot-mark">
                      <img src="/nomnom-logo.png" alt="" />
                    </span>
                  )}
                  <div className="bubble">
                    {message.text}
                    {message.role === "assistant" && message.action && (
                      <div className="chat-actions">
                        <button onClick={() => openTool(message.action!, message.action === "products" ? messages[index - 1]?.text : "")}>
                          {message.action === "products" ? "Pesquisar produto" :
                            message.action === "compare" ? "Abrir comparador" :
                              message.action === "forecast" ? "Abrir previsão" :
                                message.action === "house" ? "Abrir Minha casa" : "Analisar etiqueta"}
                          <ArrowRight size={15}/>
                        </button>
                      </div>
                    )}
                    {message.role === "assistant" && message.houseProposal && (
                      <div className="chat-actions">
                        <button onClick={() => {
                          confirmHouseProposal(message.houseProposal!);
                          setMessages((previous) => previous.map((current, i) => i === index ? { ...current, houseProposal: undefined } : current));
                        }}><Check size={15} /> Confirmar e adicionar</button>
                        <button onClick={() => {
                          navigate("house");
                          setEditingHouseIndex(null);
                          setHouseDraft({ ...normalizeHouseItem(message.houseProposal!), tariff: draft.tariff });
                          setHouseFormOpen(true);
                        }}><Pencil size={15} /> Revisar dados</button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
              {sending && (
                <div className="message assistant">
                  <span className="bot-mark">
                    <img src="/nomnom-logo.png" alt="" />
                  </span>
                  <div className="bubble typing">
                    <i />
                    <i />
                    <i />
                  </div>
                </div>
              )}
              </div>
            </div>
            <div className="assistant-bottom">
              <div className="assistant-tools">
                <button onClick={() => navigate("products")}><ShoppingBag size={17} /> Quanto isso consome?</button>
                <button onClick={() => void openCamera()}><Camera size={17} /> Ler etiqueta</button>
                <button onClick={() => navigate("house")}><Home size={17} /> Minha casa</button>
              </div>
              <div className="suggestions">
                {suggestions.map((label) => (
                  <button
                    key={label}
                    onClick={() => {
                      if (label === "Quanto isso consome?") openTool("products");
                      else if (label === "Comparar aparelhos") openTool("compare");
                      else if (label === "Previsão mensal") openTool("forecast");
                      else void sendMessage(label);
                    }}
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
                  aria-label="Pergunte à Nom Nom"
                  placeholder="Pergunte sobre energia, aparelhos e consumo..."
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
          </section>
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

      {cameraOpen && (
        <div className="modal-backdrop camera-overlay" onMouseDown={(event) => {
          if (event.currentTarget === event.target) closeCamera();
        }}>
          <div className="camera-dialog" role="dialog" aria-modal="true" aria-labelledby="camera-title">
            <div className="modal-head">
              <div><h2 id="camera-title">Fotografar etiqueta</h2><p>Enquadre a placa com a potência em W ou kW.</p></div>
              <button className="icon-button" aria-label="Fechar câmera" onClick={closeCamera}><X size={22} /></button>
            </div>
            <video ref={cameraVideoRef} autoPlay playsInline muted className="camera-live" />
            <div className="camera-actions">
              <button className="outline-button" onClick={closeCamera}>Cancelar</button>
              <button className="product-submit" onClick={captureCamera}><Camera size={19} /> Capturar foto</button>
            </div>
          </div>
        </div>
      )}
      <input
        ref={galleryRef}
        className="visually-hidden"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        onChange={onFile}
      />

      {houseFormOpen && (
        <div className="modal-backdrop" onMouseDown={(event) => { if (event.target === event.currentTarget) setHouseFormOpen(false); }}>
          <div className="settings-modal house-editor" role="dialog" aria-modal="true" aria-labelledby="house-editor-title">
            <div className="modal-head">
              <div><h2 id="house-editor-title">{editingHouseIndex === null ? "Adicionar aparelho à casa" : "Editar aparelho"}</h2>
                <p>Confirme os dados. A IA usará estes números para calcular o gasto.</p></div>
              <button className="icon-button" aria-label="Fechar" onClick={() => setHouseFormOpen(false)}><X size={21}/></button>
            </div>
            {error && <ErrorNote message={error} close={() => setError("")}/>}
            <div className="input-grid house-editor-fields">
              <label>Nome do aparelho<input maxLength={120} value={houseDraft.name} onChange={(event) => setHouseDraft((current) => ({ ...current, name: event.target.value }))} placeholder="Ex.: ventilador do quarto" /></label>
              {houseDraft.label_kwh_month != null ? (
                <label>Consumo declarado (kWh/mês)<input type="number" min="0.01" max="1000000" step="any" value={houseDraft.label_kwh_month} onChange={(event) => setHouseDraft((current) => ({ ...current, label_kwh_month: Number(event.target.value) }))}/></label>
              ) : (
                <label>Potência (W)<input type="number" min="1" max="1000000" value={houseDraft.watts || ""} placeholder="Ex.: 100" onChange={(event) => setHouseDraft((current) => ({ ...current, watts: Number(event.target.value) }))}/></label>
              )}
              {houseDraft.label_kwh_month == null && <>
                <label>Minutos de uso por dia<input type="number" min="0" max="1440" value={houseDraft.minutes} onChange={(event) => setHouseDraft((current) => ({ ...current, minutes: Number(event.target.value) }))}/></label>
                <label>Dias de uso por mês<input type="number" min="1" max="31" value={houseDraft.days} onChange={(event) => setHouseDraft((current) => ({ ...current, days: Number(event.target.value) }))}/></label>
              </>}
              <label>Quantidade de aparelhos<input type="number" min="1" max="1000" value={houseDraft.units} onChange={(event) => setHouseDraft((current) => ({ ...current, units: Number(event.target.value) }))}/></label>
            </div>
            {houseDraft.label_kwh_month != null && <p className="setting-note">Etiquetas com kWh/mês usam a condição padronizada do fabricante; não multiplicamos esse valor pelas horas informadas.</p>}
            <p className="setting-note">Tarifa considerada: R$ {formatDecimal(draft.tariff)}/kWh. Você pode alterá-la nas configurações.</p>
            <div className="house-editor-footer"><button className="outline-button" onClick={() => setHouseFormOpen(false)}>Cancelar</button>
              <button className="primary-button" onClick={commitHouseDraft}><Check size={17}/> {editingHouseIndex === null ? "Adicionar à minha casa" : "Salvar alterações"}</button></div>
          </div>
        </div>
      )}

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
                A detecção usa sua localização atual aproximada, com sua permissão. Confirme se ela corresponde à sua casa. Aplicamos automaticamente a tarifa pública apenas quando há correspondência segura da distribuidora.
              </p>
              <button
                className="outline-button"
                onClick={detectLocation}
                disabled={settingsBusy}
              >
                <MapPin size={17} />{" "}
                {locationText || "Identificar região aproximada"}
              </button>
              {locationStatus && <p className="setting-note">{locationStatus}</p>}
              {selectedUtility && <p className="setting-note">Distribuidora atual: <strong>{selectedUtility}</strong></p>}
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
