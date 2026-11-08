"""Constants for salary period conversion.

Only conventions live here, never tax parameters that have not been confirmed against a
primary source. UoP gross-to-net needs the 2026 ZUS/PIT parameters; as of 2026-11-08 the
employee contribution rates, the PIT scale and the employee KUP could not be opened in a
primary source (ISAP served a captcha, the podatki.gov.pl page 404'd), so no gross-to-net
conversion is implemented yet. See DEVIATIONS.md (DEV-004).
"""

from typing import Final

# Period factors. These are a calculation convention, not a statutory value: the
# Polish working-time norm changes month by month with the number of working days, so a
# real month can have more or fewer hours than this. Board "per hour" B2B rates are
# usually quoted against the same 8 h x 21 days convention, which is why it is used here
# (and why the original filter used 168 h and 21 days).
HOURS_PER_DAY: Final = 8
WORKING_DAYS_PER_MONTH: Final = 21
HOURS_PER_MONTH: Final = HOURS_PER_DAY * WORKING_DAYS_PER_MONTH  # 168
MONTHS_PER_YEAR: Final = 12

# Tolerance for the round-trip invariant (hour -> month -> year -> month), in currency units.
ROUND_TRIP_TOLERANCE: Final = 0.01
