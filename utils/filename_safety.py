def safe_name_long(name: str) -> str:
    import re
    name = re.sub(r'[\\/:*?"<>|]', '', name)
    name = name.rstrip('. ')
    # shorten to 50 chars max
    return (name[:50] + "…") if len(name) > 50 else name