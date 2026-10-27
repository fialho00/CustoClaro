# Diretrizes do projeto WattCola

## Objetivo

WattCola é um assistente de consumo elétrico para pessoas comuns. Sua interface principal é a Nom Nom, um coala-eletricista que ajuda o usuário a entender o custo mensal de aparelhos, estimar o consumo de sua casa, comparar eletrodomésticos e tomar decisões de economia de energia. A IA orienta; os cálculos e fatos verificáveis têm fontes independentes.

## Estado e arquitetura

- Interface oficial: React + TypeScript + Vite (`src/`); entrada `index.html`.
- API oficial: FastAPI (`api/index.py`) com `core.py` para cálculo, `vision.py` para etiquetas/Gemini, `tariffs.py` para consulta de tarifas e `products.py` e `product_catalog.py` para pesquisa de produtos.
- `app.py` é um protótipo antigo de Streamlit e não deve substituir a interface oficial.
- Logo oficial: `public/nomnom-logo.png`. Nome da IA: **Nom Nom**. Não voltar a nomes antigos; manter verde-petróleo, menta e amarelo elétrico.
- `dist/` contém a interface compilada usada por `Executavel.bat`: reconstruir e incluir `dist` quando o frontend mudar, ou o executável mostrará versão desatualizada.

## Prioridades de produto

1. A Nom Nom deve oferecer caminhos acionáveis para analisar etiqueta, comparar custo de aparelhos e gerenciar **Minha casa**.
2. Toda resposta financeira/energética calculável usa `core.py`, não números improvisados pelo modelo. Mostrar hipóteses (W, minutos/dia, dias/mês, tarifa, unidades) e permitir correção.
3. O chat é restrito a energia elétrica, consumo, economia, tarifas e produtos relacionados. Recusar cordialmente perguntas fora do tema.
4. A câmera só é aberta por interação do usuário. Fotografias e localização exigem consentimento, não devem vazar dados ou segredos.
5. Tarifas, tributos, bandeiras, distribuidoras e preços devem ter fonte e data. Geolocalização aproxima opções, mas não identifica com certeza a distribuidora; confirmar pela fatura/usuário.
6. Comparações externas precisam de fonte verificável; nunca inventar ofertas. Distinguir **estimativa** de **medição**.
7. Design responsivo, chat sem sobreposição de mensagens, foco na IA e controle claro de estados carregando/sem internet/erro.

## Segurança e API

- A integração Gemini já está implementada no backend; usar `GEMINI_API_KEY` ou `GOOGLE_API_KEY` **apenas no ambiente do servidor**. Nunca inserir chave em código, logs, README, commits, React ou variáveis `VITE_*`.
- `launcher.py` lê opcionalmente `%USERPROFILE%\Documents\.env` no Windows. Na Vercel, configurar `GEMINI_API_KEY` nas variáveis do projeto e fazer redeploy.
- `/api/health` indica presença da chave; não certifica autenticação, quotas, modelo nem disponibilidade remota. Validar com chamadas reais.
- Preservar `.gitignore`, consentimento de geolocalização, ausência de persistência das fotos e regras de leitura conservadora da etiqueta.

## Fluxo de trabalho

1. Auditar o código existente antes de alterar; não reescrever por hábito. Verificar `git status`.
2. Preferir mudanças pequenas com testes/regressão para leitura de etiquetas, aritmética, API, chat e navegação.
3. Validar com `python -m unittest discover -s tests -v` e `npm ci && npm run build` após mudança no frontend. Dependências Streamlit antigas ficam em `requirements-streamlit.txt`.
4. Sempre conferir se `public/nomnom-logo.png` aparece no build `dist/nomnom-logo.png` e se `index.html` aponta ao favicon.
5. Não afirmar que integração externa funciona sem um teste real. Documentar limites de dados e serviços disponíveis.
6. Atualizar README ao mudar comportamento, configuração, privacidade ou recursos.

Leia `README.md` para o estado atual e como configurar a API. Ideias futuras não são funcionalidades já implementadas.
