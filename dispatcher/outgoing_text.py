import re


def prepare_outgoing_text_for_ui(text: str | None) -> str:
    value = str(text or '').strip()
    if not value:
        return ''
    value = value.replace('\r\n', '\n').replace('\r', '\n')
    value = re.sub(r'\s*\n\s*', ' | ', value)
    value = re.sub(r'\s{2,}', ' ', value)
    return value.strip()
