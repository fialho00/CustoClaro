"""Open the CustoClaro web experience locally, without exposing API keys in the UI."""

from pathlib import Path
import os
import re
import socket
import threading
import webbrowser

ROOT = Path(__file__).resolve().parent


def normalize_key(value: str) -> str:
    value = value.strip()
    if '=' in value and re.match(r'^(GEMINI_API_KEY|GOOGLE_API_KEY)\s*=', value):
        value = value.partition('=')[2].strip()
    value = value.strip('"\'')
    if not value or any(ch.isspace() or ord(ch) < 32 for ch in value):
        raise ValueError('Cole somente a chave, sem espacos ou quebras de linha.')
    return value


def load_key_from_documents() -> str | None:
    """Support the user's existing private Documents/.env without copying it."""
    path = Path.home() / 'Documents' / '.env'
    if not path.is_file():
        return None
    try:
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            if re.match(r'^\s*(GEMINI_API_KEY|GOOGLE_API_KEY)\s*=', line):
                return normalize_key(line.strip())
    except (OSError, UnicodeError, ValueError):
        pass
    return None


def available_port(start: int = 8501, attempts: int = 20) -> int:
    """Keep existing local servers untouched when the default port is occupied."""
    for port in range(start, start + attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
                probe.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    raise RuntimeError('Nenhuma porta local livre para abrir o CustoClaro.')


def main() -> None:
    os.chdir(ROOT)
    if not (ROOT / 'dist' / 'index.html').is_file():
        raise SystemExit('A interface ainda nao foi compilada. Execute Executavel.bat.')
    if not os.getenv('GEMINI_API_KEY') and not os.getenv('GOOGLE_API_KEY'):
        key = load_key_from_documents()
        if key:
            os.environ['GEMINI_API_KEY'] = key
    port = available_port()
    local_url = f'http://127.0.0.1:{port}'
    print(f'CustoClaro - abrindo {local_url}')
    print('A IA usa a chave do servidor. Nenhuma chave aparece no navegador.')
    print('Para encerrar, pressione Ctrl+C nesta janela.')
    threading.Timer(1.6, lambda: webbrowser.open(local_url)).start()
    import uvicorn
    uvicorn.run('api.index:app', host='127.0.0.1', port=port, log_level='warning')


if __name__ == '__main__':
    main()
