from django.utils.text import slugify

def unicode_slugify(value):
    return slugify(value, allow_unicode=True)