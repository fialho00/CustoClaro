"""Windows-friendly setup menu; secrets never enter shell arguments."""
from pathlib import Path
import getpass
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def save_key(value):
    value = value.strip()
    if value.startswith('GEMINI_API_KEY='):
        value = value.partition('=')[2].strip().strip('"\'')
    if not value or any(c in value for c in '\r\n\x00') or not value.startswith('AIza'):
        raise ValueError('Cole somente a chave da API Google (iniciada por AIza).')
    target = ROOT / '.env'
    lines = target.read_text(encoding='utf-8-sig').splitlines() if target.exists() else []
    lines = [line for line in lines if not line.strip().startswith(('GEMINI_API_KEY=', 'GOOGLE_API_KEY='))]
    target.write_text('\n'.join(lines + ['GEMINI_API_KEY=' + value]) + '\n', encoding='utf-8')

def test_key():
    """Verify key/model access without uploading an image or exposing the secret."""
    import json
    from urllib import error, request
    from vision import DEFAULT_MODEL, configured_api_key

    key = configured_api_key()
    if not key:
        print('Nenhuma chave configurada. Escolha a opcao 2 primeiro.')
        return
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{DEFAULT_MODEL}'
    try:
        with request.urlopen(request.Request(url, headers={'x-goog-api-key': key}), timeout=20) as response:
            json.load(response)
        print('Chave aceita e modelo acessivel. A leitura da imagem ainda precisa ser testada no app.')
    except error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            print(f'Chave rejeitada ou sem acesso ao modelo (HTTP {exc.code}). Confira a chave no Google AI Studio.')
        elif exc.code == 429:
            print('Limite de chamadas atingido (HTTP 429).')
        else:
            print(f'API indisponivel ou erro de acesso (HTTP {exc.code}).')
    except OSError:
        print('Nao foi possivel conectar a API. Confira a internet.')

def main():
    os.chdir(ROOT)
    while True:
        print('\nCustoClaro\n1 - Abrir aplicativo\n2 - Adicionar ou trocar chave Gemini API\n3 - Escolher imagem e abrir aplicativo\n4 - Testar chave e acesso ao modelo\n0 - Sair')
        choice = input('Opcao: ').strip()
        if choice == '0':
            return
        if choice == '2':
            try:
                save_key(getpass.getpass('Cole a chave (entrada oculta) e pressione Enter: '))
                print('Chave salva somente no .env local.')
            except (ValueError, OSError) as error:
                print('Nao foi possivel salvar:', error)
            continue
        if choice == '4':
            test_key()
            continue
        if choice not in ('1', '3'):
            continue
        env = os.environ.copy()
        if choice == '3':
            try:
                import tkinter as tk
                from tkinter.filedialog import askopenfilename
                window = tk.Tk(); window.withdraw()
                try:
                    selected = askopenfilename(title='Escolha a etiqueta', filetypes=[('Imagens', '*.jpg *.jpeg *.png *.webp')])
                finally:
                    window.destroy()
                if not selected:
                    continue
                env['CUSTOCLARO_INITIAL_IMAGE'] = selected
            except Exception:
                print('Seletor indisponivel. Envie a imagem dentro do aplicativo.')
        print('Abrindo no navegador. A imagem so sera enviada ao Google ao clicar em Analisar.\nPara encerrar, pressione Ctrl+C nesta janela.')
        try:
            subprocess.run([sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'app.py'), '--server.address=127.0.0.1', '--server.headless=false'], env=env, check=True)
        except KeyboardInterrupt:
            pass
        except subprocess.CalledProcessError:
            print('O aplicativo encerrou com erro. Consulte a mensagem acima.')

if __name__ == '__main__':
    main()
