"""Local Windows launcher. API credentials remain in process memory only."""
from pathlib import Path
import getpass
import os
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent


def normalize_key(value: str) -> str:
    value = value.strip()
    if '=' in value and re.match(r'^(GEMINI_API_KEY|GOOGLE_API_KEY)\s*=', value):
        value = value.partition('=')[2].strip()
    value = value.strip('"\'')
    if not value or any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError('Cole somente a chave, sem espacos ou quebras de linha.')
    return value


def main():
    os.chdir(ROOT)
    print('CustoClaro — fotografe, confira e calcule.')
    print('A chave fica somente na memoria durante esta execucao; nenhum .env sera criado.')
    key = ''
    while True:
        print('\n1 - Abrir app\n2 - Inserir/trocar chave da API (opcional)\n3 - Escolher foto e abrir app\n0 - Sair')
        choice = input('Opcao: ').strip()
        if choice == '0':
            return
        if choice == '2':
            try:
                key = normalize_key(getpass.getpass('Cole a chave ou GEMINI_API_KEY=...: '))
                print('Chave recebida somente nesta sessao. A validacao ocorre ao analisar a foto.')
            except ValueError as error:
                print(error)
            continue
        if choice not in ('1', '3'):
            continue
        env = os.environ.copy()
        env.pop('GOOGLE_API_KEY', None)
        env.pop('GEMINI_API_KEY', None)
        if key:
            env['GEMINI_API_KEY'] = key
        if choice == '3':
            try:
                import tkinter as tk
                from tkinter.filedialog import askopenfilename
                window = tk.Tk(); window.withdraw()
                try:
                    selected = askopenfilename(title='Foto da etiqueta', filetypes=[('Imagens', '*.jpg *.jpeg *.png *.webp')])
                finally:
                    window.destroy()
                if not selected:
                    continue
                env['CUSTOCLARO_INITIAL_IMAGE'] = selected
            except Exception:
                print('Seletor indisponivel. Envie a foto dentro do app.')
        print('Abra a pagina mostrada no navegador. Para parar, pressione Ctrl+C.')
        try:
            subprocess.run([sys.executable, '-m', 'streamlit', 'run', str(ROOT / 'app.py'),
                            '--server.address=127.0.0.1', '--server.headless=false',
                            '--browser.gatherUsageStats=false'], env=env, check=True)
        except KeyboardInterrupt:
            pass
        except subprocess.CalledProcessError:
            print('O app encerrou com erro. Confira a mensagem acima.')

if __name__ == '__main__':
    main()
