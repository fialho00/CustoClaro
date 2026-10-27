"""Open the CustoClaro web experience locally, without exposing API keys in the UI."""

from pathlib import Path
import os
import re
import threading
import webbrowser

ROOT = Path(__file__).resolve().parent
LOCAL_URL = 'http://127.0.0.1:8501'


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


def main() -> None:
    os.chdir(ROOT)
    if not (ROOT / 'dist' / 'index.html').is_file():
        raise SystemExit('A interface ainda nao foi compilada. Execute Executavel.bat.')
    if not os.getenv('GEMINI_API_KEY') and not os.getenv('GOOGLE_API_KEY'):
        key = load_key_from_documents()
        if key:
            os.environ['GEMINI_API_KEY'] = key
    print(f'CustoClaro - abrindo {LOCAL_URL}')
    print('A IA usa a chave do servidor. Nenhuma chave aparece no navegador.')
    print('Para encerrar, pressione Ctrl+C nesta janela.')
    threading.Timer(1.6, lambda: webbrowser.open(LOCAL_URL)).start()
    import uvicorn
    uvicorn.run('api.index:app', host='127.0.0.1', port=8501, log_level='warning')


if __name__ == '__main__':
    main()
