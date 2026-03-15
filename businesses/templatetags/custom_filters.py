from django import template

register = template.Library()

@register.filter
def k_format(value):
    """
    Sayıyı '1K', '10.5K' formatına çevirir.
    """
    try:
        value = float(value)
        if value >= 1000:
            formatted = value / 1000.0
            # Eğer tam sayıysa (ör: 10.0) sadece '10K' yaz, değilse '10.5K' yaz
            if formatted.is_integer():
                return f"{int(formatted)}K"
            return f"{formatted:.1f}K"
        return int(value)
    except (ValueError, TypeError):
        return value