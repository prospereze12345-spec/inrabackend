from decimal import Decimal

# Maps a user's country code -> currency code.
# Add new countries here and nowhere else; every other
# file should derive currency through get_user_currency().
COUNTRY_CURRENCY = {
    'NG': 'NGN',
    'KE': 'KES',
    'GH': 'GHS',
    'ZA': 'ZAR',
    'EG': 'EGP',   # Egypt
}

DEFAULT_CURRENCY = 'USD'

CURRENCY_SYMBOLS = {
    'USD': '$',
    'NGN': '₦',
    'KES': 'KSh',
    'GHS': 'GH₵',
    'ZAR': 'R',
    'EGP': 'E£',
}

# Fallback FX rates if Flutterwave's rate endpoint is unreachable.
# Keep this in sync with COUNTRY_CURRENCY.
FALLBACK_EXCHANGE_RATES = {
    'NGN': Decimal('850'),
    'KES': Decimal('150'),
    'GHS': Decimal('15'),
    'ZAR': Decimal('19'),
    'EGP': Decimal('48'),
}


def get_user_currency(user) -> str:
    """Single source of truth for resolving a user's currency."""
    country = getattr(user, 'country', None)
    return COUNTRY_CURRENCY.get(country, DEFAULT_CURRENCY)