# CustoClaro

Uma etiqueta elétrica vira uma estimativa clara de consumo. Projeto de Alexandre Bezerra, Maria Eduarda e Gabriel Fialho para o Hack Day.

O novo aplicativo tem interface **React + Vite**, com design responsivo escuro, tela inicial para fotografar etiquetas, cálculo revisável, **Minha casa**, histórico de simulações e **Assistente CustoClaro** em destaque. O backend **FastAPI** reaproveita os módulos Python originais de matemática, leitura por IA e consulta de tarifas. O antigo protótipo Streamlit continua em `app.py`, mas não é mais a interface principal.

## Usar no Windows

1. Instale **Python 3.10 ou superior**. Node.js só é necessário para modificar e recompilar o frontend.
2. Abra `Executavel.bat`. Na primeira vez, aguarde instalar as dependências Python. O script usa a interface compilada incluída no repositório e abre o navegador em `http://127.0.0.1:8501` ou na próxima porta livre, se ela já estiver ocupada.
3. Se você já possui `GEMINI_API_KEY` no ambiente, ela é usada automaticamente. O iniciador também reconhece a chave privada em `Documentos/.env` (`%USERPROFILE%\Documents\.env`) **sem copiar esse arquivo para o projeto**.
4. Toque em **Tirar foto** ou **Enviar imagem**, confira a potência extraída da placa de dados (W ou kW), confirme e ajuste o tempo de uso. Também é possível informar os watts manualmente.

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

O frontend chama `/api/*`, e a função Python em `api/index.py` calcula resultados, consulta a tarifa e usa Gemini. Em ambiente publicado, é necessário validar o comportamento das reescritas FastAPI no domínio real.

## Como funciona

1. A pessoa fotografa uma **placa de dados elétricos** (não só o código de barras).
2. A IA extrai potência e mostra o trecho da etiqueta usado. Sem evidência confiável, o usuário informa a potência manualmente.
3. O cálculo determinístico Python usa `kWh/mês = (W ÷ 1.000) × (minutos/dia ÷ 60) × dias × quantidade` e `R$/mês = kWh/mês × tarifa`.
4. A pessoa compara tempos de uso, adiciona aparelhos à casa e conversa com o assistente sobre a simulação. Perguntas numéricas previsíveis usam o cálculo local; perguntas abertas podem usar IA.

Tarifa padrão de R$ 0,90/kWh é **apenas um exemplo**. A pessoa pode informar sua tarifa ou escolher uma distribuidora da ANEEL nas configurações. A geolocalização é opcional e **não identifica de forma inequívoca a distribuidora da conta**. Impostos, tributos, encargos municipais, bandeiras não confirmadas, potência variável e ciclos de funcionamento podem fazer a conta real ser diferente da estimativa.

## Privacidade e limites

- A chave Gemini fica no ambiente do servidor. O app não a solicita em campos públicos.
- Fotos não são persistidas pelo backend; uma cópia compactada e sem EXIF é enviada à API Gemini apenas após a pessoa escolher a imagem.
- Histórico e lista da casa ficam apenas em `sessionStorage` do navegador, sem conta de usuário nem sincronização.
- No chat, perguntas abertas podem enviar à IA a mensagem e dados numéricos necessários da simulação. O histórico completo da conversa não é enviado por padrão.
- A localização, quando permitida, é arredondada a duas casas decimais antes da consulta de cidade/estado; o serviço externo pode ficar indisponível.
- A estimativa não substitui medição de consumo nem análise da fatura.

O antigo protótipo pode ser aberto à parte com `python -m streamlit run app.py` após instalar `requirements-streamlit.txt`.
