"""Match an unfinished JSON object against a journal event schema instance."""
import json


SPACE = b" \t\r\n"
HEX = b"0123456789abcdef"


def matches(fragment, event):
    data = bytes(fragment)

    def whitespace(position):
        while position < len(data) and data[position] in SPACE:
            position += 1
        return position

    def literal(position, token):
        token = token.encode()
        for expected in token:
            if position == len(data):
                return position, True
            actual = data[position]
            if actual != expected and not (expected == 63 and actual in HEX):
                return position, False
            position += 1
        return position, None

    def members(position, remaining):
        position = whitespace(position)
        if position == len(data):
            return True
        if not remaining:
            return data[position:position + 1] == b"}" and not data[position + 1:].strip()
        for key in remaining:
            cursor, ending = literal(position, json.dumps(key))
            if ending is not None:
                if ending:
                    return True
                continue
            cursor = whitespace(cursor)
            if cursor == len(data):
                return True
            if data[cursor] != 58:
                continue
            cursor = whitespace(cursor + 1)
            cursor, ending = literal(cursor, json.dumps(event[key], separators=(",", ":")))
            if ending is not None:
                if ending:
                    return True
                continue
            cursor = whitespace(cursor)
            if cursor == len(data):
                return True
            following = tuple(item for item in remaining if item != key)
            if following and data[cursor] == 44 and members(cursor + 1, following):
                return True
            if not following and data[cursor] == 125 and not data[cursor + 1:].strip():
                return True
        return False

    start = whitespace(0)
    if start == len(data):
        return True
    return data[start] == 123 and members(start + 1, tuple(event))
