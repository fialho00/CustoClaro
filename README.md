# CustoClaro

Uma etiqueta elétrica vira uma estimativa clara de consumo. Projeto de Alexandre Bezerra, Maria Eduarda e Gabriel Fialho para o Hack Day.

O aplicativo tem interface **React + Vite**, leitura de etiquetas com câmera, cálculo revisável, **Minha casa**, pesquisa e comparação de modelos e lojas, histórico e **Nom Nom**, a assistente dedicada a energia. A aba **Quanto isso consome?** permite pesquisa, previsão e comparação; **Produtos e lojas** consulta ofertas. A Nom Nom oferece acesso a essas ferramentas e prepara cadastros na casa mediante confirmação. O backend **FastAPI** reaproveita os módulos Python de matemática, leitura por IA e consulta de tarifas. O antigo protótipo Streamlit continua em `app.py`, mas não é mais a interface principal.

## Objetivo do CustoClaro

**Transformar consumo elétrico em decisões simples e econômicas, com a Nom Nom como principal forma de interação.** A pessoa deve conseguir entender o custo de um eletrodoméstico, estimar gastos mensais de sua casa, comparar alternativas mais eficientes e descobrir formas práticas de economizar sem precisar conhecer fórmulas, tarifas ou especificações técnicas.

- **IA primeiro:** a Nom Nom, representada por um coala com capacete de eletricista e raio, explica resultados em português claro e encaminha para ações reais do app (fotografar etiqueta, pesquisar aparelhos, calcular e organizar a casa). A conversa fica restrita a energia, eficiência, tarifas e despesas relacionadas.
- **Transparência:** cada estimativa deve mostrar os dados usados, distinguir leitura de etiqueta de hipótese e permitir correção pelo usuário. A IA interpreta e explica; **cálculos financeiros e energéticos são determinísticos**.
- **Automação com consentimento:** pedir localização somente quando necessária e autorizada; sugerir distribuidoras e tarifas, mas permitir conferência da conta. Uma coordenada geográfica, sozinha, não comprova a distribuidora contratada.
- **Comparação útil:** permitir pesquisar produtos reais, analisar consumo, eficiência, preço e custo mensal com fontes verificáveis. Não inventar ofertas, fichas técnicas ou preços ausentes.
- **Privacidade e acessibilidade:** não expor segredos no navegador, não armazenar fotos no servidor e manter a interface rápida, responsiva e legível no celular.

### Estado atual e evolução

**Implementado no repositório:** foto ou câmera com leitura assistida por IA; conferência manual da potência; estimativa de kWh e reais; cadastro temporário de aparelhos em **Minha casa**; chat Nom Nom, com respostas locais para cálculos simples e Gemini para perguntas abertas; pesquisa fundamentada de eletrodomésticos; consulta aproximada de tarifas e localização mediante permissão; histórico nesta sessão.

**Próximos objetivos (não confundir com recursos já garantidos):** memória persistente e sincronizada da casa, identificação assistida da distribuidora pela fatura/CEP com confirmação, decomposição auditável de tributos e bandeiras, recomendações personalizadas e comparação ampliada entre lojas. Medições reais e preços atualizados exigirão fontes e integrações confiáveis.

## Logo e identidade

A identidade visual usa verde-petróleo, verde-menta e amarelo elétrico. O mascote e símbolo do app é **Nom Nom**, um coala de capacete amarelo com um raio. O arquivo principal fica em `public/nomnom-logo.png` e é usado no cabeçalho, no chat e como favicon. Para evolução do projeto e critérios de qualidade, consulte `AGENTS.md`.

## Configurar a API Gemini

**A integração com o Gemini já existe.** Não é preciso adicionar a chave ao código nem à interface. Ela é usada **somente pelo servidor Python**, para interpretar etiquetas e responder perguntas relacionadas a energia. Os cálculos manuais funcionam sem API.

1. Gere uma chave no [Google AI Studio](https://aistudio.google.com/apikey). Verifique limites de uso e faturamento aplicáveis à sua conta.
2. **Windows com `Executavel.bat` (mais simples):** crie `%USERPROFILE%\Documents\.env` e coloque uma linha `GEMINI_API_KEY=SUA_CHAVE`. O iniciador já lê esse arquivo privado, sem movê-lo para o repositório.
3. **Desenvolvimento com FastAPI:** defina a variável `GEMINI_API_KEY` no ambiente do processo que executa `uvicorn`. No PowerShell, para **apenas o terminal atual**: `$env:GEMINI_API_KEY = "SUA_CHAVE"`. Reinicie o servidor depois da alteração.
4. **Hospedagem na Vercel:** em *Project → Settings → Environment Variables*, crie `GEMINI_API_KEY` para os ambientes desejados (por exemplo, Production) e faça um novo deploy.
5. Teste `/api/health`: `ai_available: true` indica **somente que a chave foi detectada**. Depois confirme com uma pergunta real no chat e uma etiqueta com potência legível; esse é o teste efetivo da API.

**Segurança:** nunca publique seu `.env`, cole chaves em issues/prints, use `VITE_GEMINI_API_KEY`, nem chame a API Gemini diretamente do JavaScript do visitante. O arquivo `.env.example` é apenas um modelo sem segredo. Se uma chave for exposta, revogue-a no Google AI Studio e gere outra. A chave não deve ser enviada a este chat.

## Usar no Windows

1. Instale **Python 3.10 ou superior**. Node.js só é necessário para modificar e recompilar o frontend.
2. Abra `Executavel.bat`. Na primeira vez, aguarde instalar as dependências Python. O script usa a interface compilada incluída no repositório e abre o navegador em `http://127.0.0.1:8501` ou na próxima porta livre, se ela já estiver ocupada.
3. Se você já possui `GEMINI_API_KEY` no ambiente, ela é usada automaticamente. O iniciador também reconhece a chave privada em `Documentos/.env` (`%USERPROFILE%\Documents\.env`) **sem copiar esse arquivo para o projeto**.
4. Toque em **Tirar foto** ou **Enviar imagem**, confira a potência extraída da placa de dados (W ou kW), confirme e ajuste o tempo de uso. Também é possível informar os watts manualmente.
5. Para pesquisar um eletrodoméstico pelo nome, abra **Quanto isso consome?**, procure a marca e o modelo e confira a fonte antes de escolher **Calcular gasto**. O comparador aceita filtros por consumo e preço, inclusive preço informado manualmente. A aba **Produtos e lojas** oferece pesquisa e filtros específicos de ofertas.
6. Em **Minha casa**, adicione aparelhos por busca, foto ou formulário. O assistente também entende frases com dados explícitos, como **"Adicione 2 ventiladores de 80 W por 8 horas por dia"**, e mostra uma prévia para confirmação. A lista persiste no navegador; não exige cadastro.
7. Para tentar identificar a distribuidora, clique em **Detectar pela minha região** e autorize a localização. Se já houver permissão concedida, a tentativa ocorre automaticamente. A distribuidora é reconhecida automaticamente **apenas em regiões com correspondência verificada** (inicialmente Distrito Federal → Neoenergia Brasília). Em outros casos, confirme a distribuidora nas configurações.

A câmera não é ativada até o usuário tocar em **Tirar foto**. O envio reduz a imagem e remove metadados EXIF. A chave de API não aparece em nenhuma tela nem é enviada ao navegador.

## Desenvolvimento

```bash
python -m venv .venv
# Ative o ambiente virtual
python -m pip install -r requirements.txt
npm ci
npm run dev
```

O Vite encaminha `/api/*` para `http://127.0.0.1:8000`; em outro terminal, execute:

```bash
python -m uvicorn api.index:app --host 127.0.0.1 --port 8000
```

Para validar a versão compilada localmente (ou regenerá-la depois de editar React/CSS):

```bash
npm run build
python -m uvicorn api.index:app --host 127.0.0.1 --port 8501
python -m unittest discover -s tests -v
```

Os testes originais que importam o protótipo Streamlit também precisam das dependências em `requirements-streamlit.txt`.

## Publicar na Vercel

1. Importe este repositório GitHub para a [Vercel](https://vercel.com/new).
2. Use o framework **Vite**, build `npm run build`, diretório de saída `dist` e mantenha as configurações de roteamento de `vercel.json`.
3. Adicione a variável de ambiente de **servidor** `GEMINI_API_KEY` na Vercel. Nunca adicione `VITE_GEMINI_API_KEY`: qualquer variável `VITE_` pode ser incorporada ao JavaScript do visitante.
4. Faça o deploy e **teste `/api/health`, uma foto real e o chat** no domínio publicado antes da apresentação. O endpoint `/api/health` retorna apenas a disponibilidade da IA, jamais a chave.

O frontend chama `/api/*`, e a função Python em `api/index.py` calcula resultados, consulta a tarifa e usa Gemini. Em ambiente publicado, é necessário validar o comportamento das reescritas FastAPI no domínio real. O projeto deve usar segredos no ambiente **do servidor**, nunca em variáveis `VITE_*`.

## Como funciona

1. A pessoa fotografa uma **placa de dados elétricos** (não só o código de barras).
2. A IA extrai potência e mostra o trecho da etiqueta usado. Sem evidência confiável, o usuário informa a potência manualmente.
3. O cálculo determinístico Python usa `kWh/mês = (W ÷ 1.000) × (minutos/dia ÷ 60) × dias × quantidade` e `R$/mês = kWh/mês × tarifa`.
4. A pessoa compara tempos de uso, adiciona aparelhos à casa e conversa com o assistente sobre a simulação. Perguntas numéricas previsíveis usam o cálculo local; perguntas abertas podem usar IA.
5. A função **Quanto isso consome?** usa pesquisa web embasada pelo Gemini, com preferência por dados de fabricante/Inmetro. Retorna apenas candidatos com fonte e potência ou consumo mensal informado; o usuário deve conferir essas referências.
6. A **Previsão mensal** calcula a partir de potência e horas de uso **ou**, quando disponível, do consumo mensal padronizado da etiqueta. Esses métodos não devem ser misturados: o segundo não é escalado linearmente com o tempo de uso. O **Comparador** apresenta consumo, preço disponível e custo total estimado de compra + cinco anos de energia.
7. **Minha casa** calcula o consumo agregado com as duas metodologias, incluindo quantidade de unidades. O chat recebe o inventário em qualquer aba e pode mostrar o maior custo e sugestões. Toda inclusão proposta pelo chat requer confirmação explícita.

Tarifa padrão de R$ 0,90/kWh é **apenas um exemplo**. A pessoa pode informar sua tarifa ou escolher uma distribuidora da ANEEL nas configurações. A localização identifica a região, não diretamente a rede elétrica ou o titular da fatura; a correspondência só é aplicada automaticamente em áreas de concessão sem ambiguidade documentada. Impostos, tributos, encargos municipais, bandeiras não confirmadas, potência variável e ciclos de funcionamento podem fazer a conta real ser diferente da estimativa.

## Privacidade e limites

- A chave Gemini fica no ambiente do servidor. O app não a solicita em campos públicos.
- Fotos não são persistidas pelo backend; uma cópia compactada e sem EXIF é enviada à API Gemini apenas após a pessoa escolher a imagem.
- A lista de **Minha casa**, a tarifa e o nome da distribuidora ficam em `localStorage`, inclusive após fechar o navegador. O histórico de análises e as pesquisas temporárias continuam em `sessionStorage`. Não há conta de usuário, sincronização entre aparelhos nem armazenamento do inventário no servidor.
- No chat, perguntas abertas podem enviar à IA a mensagem e dados numéricos necessários da simulação. O histórico completo da conversa não é enviado por padrão.
- A pesquisa por nome usa Google Search Grounding no Gemini, depende de disponibilidade e da cota do projeto Google e **pode gerar cobranças** conforme o plano. Especificações ou preços de terceiros não são garantidos; dados ausentes permanecem vazios. Os modelos comparados ficam somente na sessão do navegador.
- A localização, quando permitida, é arredondada a duas casas decimais antes da consulta de cidade/estado; o serviço externo pode ficar indisponível. As coordenadas não são persistidas. O navegador exige a permissão do visitante, caso não tenha sido concedida anteriormente.
- A estimativa não substitui medição de consumo nem análise da fatura.

O antigo protótipo pode ser aberto à parte com `python -m streamlit run app.py` após instalar `requirements-streamlit.txt`.
