import re


def has_chinese(text):
    return bool(re.search(r'[一-鿿]', text))
