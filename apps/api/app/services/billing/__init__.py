"""Provider-agnostic billing.

`base.py` defines the interface every payment backend implements; `manual.py`
and `stripe_provider.py` are the two shipped backends; `registry.py` picks one
from config. The router never imports a concrete provider — add a new backend by
dropping in a `BillingProvider` subclass and wiring it into `registry.py`.
"""
