# WattCola ⚡

**Entenda sua energia. Economize com ajuda da Nom Nom.**

Projeto do Hack Day desenvolvido por **Alexandre Bezerra, Maria Eduarda e Gabriel Fialho**. O WattCola ajuda a transformar informações de eletrodomésticos em estimativas compreensíveis de consumo e gasto — com uma IA dedicada ao assunto e cálculos reproduzíveis.

**Acesse o aplicativo:** [wattcola.vercel.app](https://wattcola.vercel.app).

## O que o aplicativo faz

| Recurso | Como funciona | Observação |
| --- | --- | --- |
| **Nom Nom · IA** | Chat sobre energia, tarifas, eficiência e aparelhos; sugere botões para abrir as ferramentas e pode preparar a inclusão de um item em Minha casa. | Uma inclusão feita pelo chat exige confirmação. A IA pode ficar indisponível por cota/rede. |
| **Analisar aparelho** | Fotografe ou envie a placa/etiqueta com potência, confira o valor extraído e simule kWh e reais por mês. | A câmera só abre por ação do visitante; é possível informar watts manualmente. |
| **Quanto isso consome?** | Pesquise marca/modelo com fontes, escolha um aparelho, obtenha previsão mensal e compare alternativas. | Especificações de terceiros devem ser conferidas; valores ausentes não são inventados. |
| **Produtos e lojas** | Pesquisa assistida e filtros de preço, consumo e eficiência para descobrir produtos. | Resultados são referências de pesquisa, não preços/estoque garantidos. |
| **Minha casa** | Cadastre vários aparelhos, quantidades e uso diário; veja gasto agregado e principais consumidores. | O inventário é armazenado neste navegador, sem login ou sincronização. |
| **Tarifas e região** | Sugestão de distribuidora mediante autorização de localização e consulta à ANEEL. | Localização não prova qual empresa atende uma conta; confirme na fatura. |
| **Histórico** | Reabra análises feitas durante a sessão. | Histórico é local e temporário. |

A IA é a interface de orientação; **contas de energia e dinheiro são calculadas pelo backend Python**, não por texto improvisado do modelo.

## Tecnologias e estrutura

- **Frontend:** React 19, TypeScript e Vite em `src/`; identidade visual com o coala-eletricista **Nom Nom** (`public/nomnom-logo.png`).
- **Backend:** FastAPI em `api/index.py`; matemática em `core.py`, IA/imagens em `vision.py`, tarifas em `tariffs.py` e pesquisa de produtos em `products.py` e `product_catalog.py`.
- **Produção:** frontend estático servido pela Vercel e rotas `/api/*` executadas por função Python, conforme `vercel.json`.
- **Windows:** `Executavel.bat` inicia o backend local e serve a interface já compilada em `dist/`.
- **Legado:** `app.py` é um protótipo Streamlit; não é a interface oficial.

## Configurar a API Gemini

A integração com Gemini **já está implementada**. Você precisa fornecer a chave **somente ao servidor** para habilitar respostas abertas da IA, leitura de etiquetas e pesquisas online. As simulações determinísticas continuam disponíveis sem Gemini.

### Na Vercel (para todos acessarem)

1. Gere ou confira sua chave em [Google AI Studio](https://aistudio.google.com/apikey). Consulte o plano, as cotas e eventuais cobranças.
2. Abra o [painel da Vercel](https://vercel.com/dashboard), selecione o projeto **`wattcola`** (repositório `fialho00/WattCola`) e entre em **Settings → Environment Variables**.
3. Adicione exatamente:
   - **Key:** `GEMINI_API_KEY`
   - **Value:** sua chave privada do Gemini (sem aspas extras ou espaços)
   - **Environment:** **Production**. Marque **Preview** também se quiser que as prévias usem IA; Development é opcional.
4. Salve. Depois abra **Deployments**, faça **Redeploy** da versão mais recente em Production (ou crie um novo deploy). Variáveis novas não ativam uma implantação já publicada automaticamente.
5. No **domínio real** do projeto, visite `https://SEU-DOMINIO/api/health`. O esperado é `{"status":"ok","ai_available":true}`. Isso **só comprova que a chave foi detectada**, não que o Gemini aceitou a requisição.
6. Confirme com uma **pergunta aberta sobre consumo no chat**, uma **pesquisa de modelo** e uma **foto de etiqueta legível**. Em caso de erro ou limite de cota, confira os logs da função na Vercel e os limites da chave no AI Studio.

**Segurança:**
- **Nunca** use `VITE_GEMINI_API_KEY`, insira a chave em `src/`, `public/`, README, commits, issues ou prints. Variáveis `VITE_*` podem entrar no JavaScript público.
- Não envie a chave para este chat. Não compartilhe `.env`; o `.env.example` tem somente o nome da variável.
- Se uma chave for publicada por engano, revogue-a no Google AI Studio, gere outra e atualize o segredo na Vercel.
- A Vercel hospeda o site para outros visitantes; **ela não fornece uma chave Gemini**. A chave, cota e eventual faturamento pertencem ao projeto Google configurado.

### No Windows (`Executavel.bat`)

1. Instale Python 3.10+.
2. Crie **`%USERPROFILE%\Documents\.env`** (fora do repositório) com:
   ```dotenv
   GEMINI_API_KEY=SUA_CHAVE_PRIVADA
   ```
3. Clique duas vezes em `Executavel.bat`. O iniciador usa essa chave no processo Python e abre o site em `http://127.0.0.1:8501` (ou outra porta local disponível).
4. Se modificar o frontend, execute `npm ci` e `npm run build` para atualizar `dist/` antes de usar o executável.

### No desenvolvimento

Em dois terminais abertos na raiz do projeto:

```powershell
# Terminal 1 — servidor Python (PowerShell)
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:GEMINI_API_KEY = "SUA_CHAVE_PRIVADA"
python -m uvicorn api.index:app --host 127.0.0.1 --port 8000
```

```bash
# Terminal 2 — interface Vite
npm ci
npm run dev
```

O Vite encaminha `/api/*` para `http://127.0.0.1:8000`. Sem chave, a API responde para cálculos locais, mas operações que dependem de Gemini podem ficar indisponíveis.

## Como é feita uma estimativa

1. Você informa o aparelho ou fotografa uma **placa de dados elétricos**, de preferência com o valor em W/kW visível.
2. Você revisa os dados, define tempo diário, dias no mês, quantidade e tarifa em R$/kWh.
3. Para potência constante, o backend usa:

   `kWh/mês = (W ÷ 1.000) × (minutos/dia ÷ 60) × dias × quantidade`

   `R$/mês = kWh/mês × tarifa`

4. Quando há um **consumo mensal padronizado em kWh/mês da etiqueta**, o sistema utiliza esse valor como base separada e **não** o multiplica de novo por horas de uso.
5. Você pode comparar consumo, preço informado e custo total aproximado de **compra + cinco anos de eletricidade**.

A tarifa inicial de **R$ 0,90/kWh é apenas um exemplo**. Tributos, iluminação pública, bandeiras não confirmadas, ciclos de funcionamento e variações reais de potência podem mudar bastante a conta. O WattCola faz **estimativas, não medições**, nem substitui a fatura.

## Verificar e testar

```bash
npm ci
npm run build
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Para verificar os modelos disponíveis com sua chave local, sem exibir o segredo:

```bash
python scripts/check_gemini.py        # consulta modelos disponíveis
python scripts/check_gemini.py --live # faz uma requisição curta; pode consumir cota
```

Cheque ainda:

- `dist/nomnom-logo.png` e o favicon após o build;
- `GET /api/health` e `POST /api/estimate` no backend real;
- chat e leitura de uma etiqueta **na Vercel**, com cota Gemini disponível;
- layout no celular, histórico e dados da casa após recarregar a página.

**Rotas principais:** `/api/health`, `/api/estimate`, `/api/house`, `/api/analyze`, `/api/chat`, `/api/products/discover`, `/api/products/forecast`, `/api/products/search`, `/api/distributors`, `/api/tariff`, `/api/location`.

## Privacidade, limitações e próximos passos

- A chave Gemini permanece **no servidor**; o navegador só chama rotas `/api/*`.
- Fotos são reduzidas e reenviadas sem EXIF; não são armazenadas pelo backend, mas a imagem escolhida pode ser transmitida ao Gemini para análise.
- Inventário de **Minha casa**, tarifa e distribuidora ficam em `localStorage`; histórico e buscas temporárias em `sessionStorage`. **Não há conta, backup ou sincronização**.
- A localização só é solicitada com permissão e aproxima a região; a identificação automática da distribuidora existe apenas em áreas com associação previamente verificada.
- Pesquisa web e busca de lojas dependem da cota, disponibilidade e qualidade das fontes externas; **não garantem ofertas ou especificações atuais**.
- Evoluções possíveis: validação de distribuidora pela fatura, decomposição de tributos, comparação com mais fontes, sincronização opcional e teste monitorado em produção.

Consulte `AGENTS.md` para as regras técnicas de manutenção. Licença em `LICENSE`.
