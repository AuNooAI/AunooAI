def masked_string(string):
    return f"{string[:4]}...{string[-4:]}" if len(string) > 8 else "[SET]"