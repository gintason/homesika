# Markets: cities and countries

Where Homesika runs is configured in one place, `backend/apps/core/markets.py`, and served to the apps
at `GET /api/v1/markets/`.

## Switches

| Setting | Default | Meaning |
|---|---|---|
| `MARKETS_COUNTRIES` | `NG` | Countries switched on. Organizations can only be created in these. |
| `MARKETS_CITIES` | `lagos,abuja,accra` | Cities offered in forms. A city shows only when its country is on, so Accra stays hidden while Ghana is off. |

## Nigeria: Lagos and Abuja (on)

* **Lagos:** 18 areas (Lekki, Yaba, Ikeja, Surulere…). Electricity companies: Ikeja Electric and Eko
  Electric.
* **Abuja:** 20 areas (Wuse 2, Maitama, Garki, Gwarinpa, Jabi…). Electricity company: AEDC
  (`abuja-electric`, already in the bills catalogue with its prepaid and postpaid plans).
* Nothing else changes per city. Same currency, time zone, payment gateways, bills, ID checks and the
  112 emergency number.
* **To add a city:** add a `City(...)` to `CITIES` with its areas and DisCo codes, and add its slug to
  `MARKETS_CITIES`. No migration is needed.

## Ghana (built, off)

What is ready:
* the country: GHS, +233, Africa/Accra;
* local numbers read as Ghanaian inside a Ghana organization (024 123 4567 → +233 24 123 4567);
* organizations get GHS and the Accra time zone automatically;
* Accra areas.

Bills (VTU) are marked unavailable there, and artisan ID checks are manual.

**Before setting `MARKETS_COUNTRIES=NG,GH`, all of these must be done:**
1. **Payments:** Paystack/Flutterwave settlement in GHS, and mobile money, confirmed in writing for split
   payments. The payment code passes the organization's currency, but GHS hasn't been tested.
2. **Bills:** a Ghana bills provider (airtime, data, ECG electricity), or keep bills off for Ghana.
3. **Artisan ID check:** Ghana Card through a licensed provider. Until then, Homesika staff review IDs
   by hand.
4. **Messaging:** an SMS sender ID registered for Ghana, and WhatsApp templates approved for Ghana
   numbers.
5. **Emergency numbers:** 112, with police 191, fire 192 and ambulance 193, confirmed
   (`TODO(verify)`). The apps say "call 112".
6. **Data protection:** register with Ghana's Data Protection Commission (Data Protection Act 2012),
   and update the privacy notice.
7. **Legal:** a lawyer reviews the terms, rent collection and the estate security wording for Ghana.
8. **Languages:** decide on Twi (today it's English and Nigerian Pidgin only).
