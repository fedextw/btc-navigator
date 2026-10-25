"""Pure standard-library syntax check for requested USDT symbol names.

This checks the string format only; it does NOT attest to Binance listing status.
"""
def valid_symbol(symbol):
    return (isinstance(symbol, str) and symbol.endswith("USDT") and
            1 <= len(symbol[:-4]) <= 40 and symbol[:-4].isalnum())
