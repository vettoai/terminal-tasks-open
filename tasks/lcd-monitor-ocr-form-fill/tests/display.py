import re


def normalise(value):
    if not isinstance(value, str):
        return ''
    return ' '.join(value.translate(str.maketrans('–—−', '---')).split())


def within_limits(value, specification):
    text = normalise(value)
    if 'format' in specification:
        return re.fullmatch(specification['format'], text) is not None
    suffix = r'\s+' + re.escape(specification['unit']) if specification['unit'] else ''
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d+)?|\.\d+))' + suffix, text)
    if match is None:
        return False
    number = float(match.group(1))
    return specification['min'] <= number <= specification['max']
