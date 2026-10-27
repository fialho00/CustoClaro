"""Windows-friendly setup menu; secrets never enter shell arguments."""
from pathlib import Path
import getpass
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent

def save_key(value):
    value = value.strip()
    if not value or any(c in value for c in '\r\n\x00') or not value.startswith('AIza'):
        raise ValueError('Cole somente a chave da API Google (iniciada por AIza).')
    target = ROOT / '.env'
    lines = target.read_text(encoding='utf-8-sig').splitlines() if target.exists() else []
    lines = [line for line in lines if not line.strip().startswith(('GEMINI_API_KEY=', 'GOOGLE_API_KEY='))]
    target.write_text('\n'.join(lines + ['GEMINI_API_KEY=' + value]) + '\n', encoding='utf-8')

def main():
    os.chdir(ROOT)
    while True:
        print('\nCustoClaro\n1 - Abrir aplicativo\n2 - Adicionar ou trocar chave Gemini API\n3 - Escolher imagem e abrir aplicativo\n0 - Sair')
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
