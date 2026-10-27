# CustoClaro ⚡

**Da foto de uma etiqueta elétrica a uma estimativa compreensível de consumo.**

MVP open-source para o Hacktoberfest Hack Day Brasília x SENAI DF (27/10/2026),
voltado às categorias **Best Open-Source AI Project** e **Best Use of Gemma 4**.

## Equipe

- Alexandre Bezerra
- Maria Eduarda
- Gabriel Fialho

## O que ele faz

1. O usuário envia uma foto (JPEG/PNG/WebP) da etiqueta de um aparelho.
2. **Gemma 4**, modelo de pesos abertos, interpreta a imagem pela **Gemini API**,
   procura um valor explícito de potência nominal (W/kW) e cita o trecho encontrado.
3. O usuário **confirma ou corrige** a potência. Os cálculos só aparecem após
   essa confirmação, quando há um resultado da IA. Se a IA não tiver certeza,
   é possível preencher tudo manualmente.
4. O aplicativo calcula o consumo com uma fórmula determinística, exibe custo
   mensal e em 12 meses, e compara dois cenários de horas de uso.
5. A simulação pode ser exportada em CSV.

> **Importante:** usar apenas os campos manuais não demonstra integração com IA.
> Para disputar a categoria Gemma 4, configure a API e demonstre uma leitura real.

## Início rápido no Windows

1. Instale Python 3.10 ou superior (marque **Add Python to PATH**).
2. Baixe o repositório em **Code → Download ZIP** e extraia todos os arquivos.
3. Dê dois cliques em **Iniciar_CustoClaro.bat**. A primeira execução instala as dependências e precisa de internet.
4. Escolha **2** para cadastrar sua Gemini API Key (entrada oculta, salva apenas no `.env` local).
5. Escolha **3** para selecionar uma imagem e abrir o aplicativo, ou **1** para abrir sem imagem.
6. No navegador, clique em **Analisar etiqueta**, revise a potência e confirme antes de calcular.

No menu, a opção **4** verifica se a chave foi aceita e se o modelo está acessível,
sem enviar foto. Cole a chave diretamente ou como `GEMINI_API_KEY=...` na opção 2.
Se a API rejeitar a chave, crie ou copie uma chave válida no Google AI Studio.
Essa verificação não substitui o teste de leitura com imagem real.

Selecionar a foto não a envia automaticamente ao Google. Também é possível enviar fotos diretamente no navegador. Feche o servidor com Ctrl+C na janela do iniciador. Nunca compartilhe a pasta com seu `.env`; compartilhe o link do GitHub.

## Instalação (Python 3.10+)

Windows/PowerShell:

```powershell
cd custoclaro
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env
streamlit run app.py
```

Linux/macOS:

```bash
cd custoclaro
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

O navegador abrirá no endereço local apresentado pelo Streamlit
(normalmente `http://localhost:8501`).

**Chave de API:** obtenha em https://aistudio.google.com/apikey e preencha
`GEMINI_API_KEY` no arquivo `.env`. Não publique nem compartilhe esse arquivo.
Quando a chave não está configurada, a análise de imagem é desativada, mas o
simulador manual continua disponível.

**Modelo:** `gemma-4-26b-a4b-it` pela biblioteca oficial `google-genai`.
O projeto não usa `gemini-flash` como substituto silencioso e não exige GPU local.
Documentação: https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api

**Termos dos pesos do modelo:** consulte
https://ai.google.dev/gemma/terms — *modelo open-weight* não implica que
os pesos estejam sob licença MIT. A licença MIT deste repositório cobre somente
o código escrito para esta aplicação.

## Como demonstrar em 90 segundos

1. Abra o aplicativo e mostre que o modelo configurado é Gemma 4.
2. Envie uma foto real de uma etiqueta **com potência em W claramente visível**.
3. Clique em **Analisar etiqueta com Gemma 4** e mostre potência e evidência.
4. Confirme o valor. Configure uma tarifa **de exemplo** e horas de uso.
5. Mostre o custo do mês, a fórmula e a comparação entre dois cenários.
6. Exporte o CSV. Explique que estimativas não substituem um medidor de energia.

### Cenário de demonstração sem API

O botão **Carregar ventilador de exemplo** usa dados fictícios:
60 W × 8 h/dia × 30 dias = **14,4 kWh**; a R$ 0,90/kWh, **R$ 12,96/mês**.
Esse modo mostra os cálculos e a interface, mas **não testa a IA**.

## Fórmula e limitações

`kWh/mês = (W ÷ 1000) × horas/dia × dias/mês × quantidade`

`R$/mês = kWh/mês × tarifa informada (R$/kWh)`

- O algoritmo de cálculo fica em `core.py` e não depende do texto da IA.
- Estima consumo **constante** à potência fornecida; não mede o uso real.
- Dispositivos com compressor, termostato, modos variáveis e standby podem
  divergir muito da estimativa.
- O custo anual representa **12 meses equivalentes**, sem reajustes.
- A tarifa é fornecida pelo usuário. Não buscamos preços atuais de distribuidoras,
  nem incluímos automaticamente impostos, bandeiras, tarifas mínimas ou encargos.
- A foto é reduzida, convertida para JPEG sem EXIF e enviada ao Google somente
  após clicar em **Analisar etiqueta**. O projeto não salva a imagem em disco.
- A leitura da IA pode estar errada: requer confirmação humana.
- Não tente obter consumo apenas de tensão (V) e corrente (A): o fator de potência
  e o comportamento real do equipamento podem impedir inferências confiáveis.

## Arquitetura

```text
Imagem ──> Streamlit/Pillow ──> Gemma 4 (Google GenAI) ──> Leitura + evidência
                                                          │
Entrada manual ────────────────────────────────────────────┤
                                                          ▼
                                                  Revisão do usuário
                                                          │
                                                          ▼
                                                  core.py (Decimal)
                                                          │
                                      KPIs + gráfico + CSV + fórmula
```

Arquivos:

- `app.py`: interface, fluxo, limites da imagem, exportação.
- `vision.py`: prompt de extração, Gemini API, parser validado.
- `core.py`: matemática determinística e formatação monetária.
- `tests/`: testes unitários que **não necessitam chave de API**.

## Testes

Dentro da pasta do projeto:

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py core.py vision.py
```

Além dos testes unitários, faça um teste manual com uma foto real e uma chave
de API válida. **Nenhum teste mockado prova acesso real ao endpoint Gemma 4.**

## Entrega para o Hack Day

- Publicar em repositório GitHub **público** com este README e `LICENSE`.
- Registrar o que foi efetivamente desenvolvido durante o evento e confirmar
  com o organizador se a preparação prévia é permitida.
- Não subir `.env`, tokens ou fotos pessoais para o repositório.
- Um integrante envia o projeto no OrganizerHQ antes do prazo do evento,
  selecionando as categorias às quais ele atende.

## Licença

Código original sob MIT. Ver `LICENSE`. Gemma 4 e componentes de terceiros
seguem suas próprias licenças/termos.
