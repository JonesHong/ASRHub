def to_camel_case(s: str) -> str:
    return "".join(word.capitalize() for word in s.split("_"))

def add_title_prefix(title: str, s: str) -> str:
    return title + " " + s