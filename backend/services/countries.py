"""
Every country / territory with its ISO 3166-1 alpha-2 code and international dialling code,
plus helpers to work out an applicant's country from what they typed.

This file is the single source of truth: the apply page's picker data (country-picker.js)
is generated from it by `python tools/build_country_picker.py`.

  COUNTRIES          [(iso2, name, dial)], dial without '+'; shared codes list the primary first
  country_name(iso)  'IN' -> 'India'
  normalize_iso(v)   'in' / 'IN ' -> 'IN', unknown -> None
  country_from_phone(phone, strict=True)
  country_from_college(college)
  infer_country(phone, college) -> (iso2 | None, 'phone' | 'college' | None)
"""

from __future__ import annotations

import re

COUNTRIES: list[tuple[str, str, str]] = [
    ("AF", "Afghanistan", "93"),
    ("AX", "Åland Islands", "358"),
    ("AL", "Albania", "355"),
    ("DZ", "Algeria", "213"),
    ("AS", "American Samoa", "1684"),
    ("AD", "Andorra", "376"),
    ("AO", "Angola", "244"),
    ("AI", "Anguilla", "1264"),
    ("AG", "Antigua and Barbuda", "1268"),
    ("AR", "Argentina", "54"),
    ("AM", "Armenia", "374"),
    ("AW", "Aruba", "297"),
    ("AU", "Australia", "61"),
    ("AT", "Austria", "43"),
    ("AZ", "Azerbaijan", "994"),
    ("BS", "Bahamas", "1242"),
    ("BH", "Bahrain", "973"),
    ("BD", "Bangladesh", "880"),
    ("BB", "Barbados", "1246"),
    ("BY", "Belarus", "375"),
    ("BE", "Belgium", "32"),
    ("BZ", "Belize", "501"),
    ("BJ", "Benin", "229"),
    ("BM", "Bermuda", "1441"),
    ("BT", "Bhutan", "975"),
    ("BO", "Bolivia", "591"),
    ("BQ", "Caribbean Netherlands", "599"),
    ("BA", "Bosnia and Herzegovina", "387"),
    ("BW", "Botswana", "267"),
    ("BR", "Brazil", "55"),
    ("IO", "British Indian Ocean Territory", "246"),
    ("VG", "British Virgin Islands", "1284"),
    ("BN", "Brunei", "673"),
    ("BG", "Bulgaria", "359"),
    ("BF", "Burkina Faso", "226"),
    ("BI", "Burundi", "257"),
    ("KH", "Cambodia", "855"),
    ("CM", "Cameroon", "237"),
    ("CA", "Canada", "1"),
    ("CV", "Cape Verde", "238"),
    ("KY", "Cayman Islands", "1345"),
    ("CF", "Central African Republic", "236"),
    ("TD", "Chad", "235"),
    ("CL", "Chile", "56"),
    ("CN", "China", "86"),
    ("CX", "Christmas Island", "61"),
    ("CC", "Cocos (Keeling) Islands", "61"),
    ("CO", "Colombia", "57"),
    ("KM", "Comoros", "269"),
    ("CG", "Congo", "242"),
    ("CD", "Congo (DRC)", "243"),
    ("CK", "Cook Islands", "682"),
    ("CR", "Costa Rica", "506"),
    ("CI", "Côte d'Ivoire", "225"),
    ("HR", "Croatia", "385"),
    ("CU", "Cuba", "53"),
    ("CW", "Curaçao", "599"),
    ("CY", "Cyprus", "357"),
    ("CZ", "Czechia", "420"),
    ("DK", "Denmark", "45"),
    ("DJ", "Djibouti", "253"),
    ("DM", "Dominica", "1767"),
    ("DO", "Dominican Republic", "1809"),
    ("EC", "Ecuador", "593"),
    ("EG", "Egypt", "20"),
    ("SV", "El Salvador", "503"),
    ("GQ", "Equatorial Guinea", "240"),
    ("ER", "Eritrea", "291"),
    ("EE", "Estonia", "372"),
    ("SZ", "Eswatini", "268"),
    ("ET", "Ethiopia", "251"),
    ("FK", "Falkland Islands", "500"),
    ("FO", "Faroe Islands", "298"),
    ("FJ", "Fiji", "679"),
    ("FI", "Finland", "358"),
    ("FR", "France", "33"),
    ("GF", "French Guiana", "594"),
    ("PF", "French Polynesia", "689"),
    ("GA", "Gabon", "241"),
    ("GM", "Gambia", "220"),
    ("GE", "Georgia", "995"),
    ("DE", "Germany", "49"),
    ("GH", "Ghana", "233"),
    ("GI", "Gibraltar", "350"),
    ("GR", "Greece", "30"),
    ("GL", "Greenland", "299"),
    ("GD", "Grenada", "1473"),
    ("GP", "Guadeloupe", "590"),
    ("GU", "Guam", "1671"),
    ("GT", "Guatemala", "502"),
    ("GG", "Guernsey", "44"),
    ("GN", "Guinea", "224"),
    ("GW", "Guinea-Bissau", "245"),
    ("GY", "Guyana", "592"),
    ("HT", "Haiti", "509"),
    ("HN", "Honduras", "504"),
    ("HK", "Hong Kong", "852"),
    ("HU", "Hungary", "36"),
    ("IS", "Iceland", "354"),
    ("IN", "India", "91"),
    ("ID", "Indonesia", "62"),
    ("IR", "Iran", "98"),
    ("IQ", "Iraq", "964"),
    ("IE", "Ireland", "353"),
    ("IM", "Isle of Man", "44"),
    ("IL", "Israel", "972"),
    ("IT", "Italy", "39"),
    ("JM", "Jamaica", "1876"),
    ("JP", "Japan", "81"),
    ("JE", "Jersey", "44"),
    ("JO", "Jordan", "962"),
    ("KZ", "Kazakhstan", "7"),
    ("KE", "Kenya", "254"),
    ("KI", "Kiribati", "686"),
    ("XK", "Kosovo", "383"),
    ("KW", "Kuwait", "965"),
    ("KG", "Kyrgyzstan", "996"),
    ("LA", "Laos", "856"),
    ("LV", "Latvia", "371"),
    ("LB", "Lebanon", "961"),
    ("LS", "Lesotho", "266"),
    ("LR", "Liberia", "231"),
    ("LY", "Libya", "218"),
    ("LI", "Liechtenstein", "423"),
    ("LT", "Lithuania", "370"),
    ("LU", "Luxembourg", "352"),
    ("MO", "Macao", "853"),
    ("MG", "Madagascar", "261"),
    ("MW", "Malawi", "265"),
    ("MY", "Malaysia", "60"),
    ("MV", "Maldives", "960"),
    ("ML", "Mali", "223"),
    ("MT", "Malta", "356"),
    ("MH", "Marshall Islands", "692"),
    ("MQ", "Martinique", "596"),
    ("MR", "Mauritania", "222"),
    ("MU", "Mauritius", "230"),
    ("YT", "Mayotte", "262"),
    ("MX", "Mexico", "52"),
    ("FM", "Micronesia", "691"),
    ("MD", "Moldova", "373"),
    ("MC", "Monaco", "377"),
    ("MN", "Mongolia", "976"),
    ("ME", "Montenegro", "382"),
    ("MS", "Montserrat", "1664"),
    ("MA", "Morocco", "212"),
    ("MZ", "Mozambique", "258"),
    ("MM", "Myanmar", "95"),
    ("NA", "Namibia", "264"),
    ("NR", "Nauru", "674"),
    ("NP", "Nepal", "977"),
    ("NL", "Netherlands", "31"),
    ("NC", "New Caledonia", "687"),
    ("NZ", "New Zealand", "64"),
    ("NI", "Nicaragua", "505"),
    ("NE", "Niger", "227"),
    ("NG", "Nigeria", "234"),
    ("NU", "Niue", "683"),
    ("NF", "Norfolk Island", "672"),
    ("KP", "North Korea", "850"),
    ("MK", "North Macedonia", "389"),
    ("MP", "Northern Mariana Islands", "1670"),
    ("NO", "Norway", "47"),
    ("OM", "Oman", "968"),
    ("PK", "Pakistan", "92"),
    ("PW", "Palau", "680"),
    ("PS", "Palestine", "970"),
    ("PA", "Panama", "507"),
    ("PG", "Papua New Guinea", "675"),
    ("PY", "Paraguay", "595"),
    ("PE", "Peru", "51"),
    ("PH", "Philippines", "63"),
    ("PL", "Poland", "48"),
    ("PT", "Portugal", "351"),
    ("PR", "Puerto Rico", "1787"),
    ("QA", "Qatar", "974"),
    ("RE", "Réunion", "262"),
    ("RO", "Romania", "40"),
    ("RU", "Russia", "7"),
    ("RW", "Rwanda", "250"),
    ("BL", "Saint Barthélemy", "590"),
    ("SH", "Saint Helena", "290"),
    ("KN", "Saint Kitts and Nevis", "1869"),
    ("LC", "Saint Lucia", "1758"),
    ("MF", "Saint Martin", "590"),
    ("PM", "Saint Pierre and Miquelon", "508"),
    ("VC", "Saint Vincent and the Grenadines", "1784"),
    ("WS", "Samoa", "685"),
    ("SM", "San Marino", "378"),
    ("ST", "São Tomé and Príncipe", "239"),
    ("SA", "Saudi Arabia", "966"),
    ("SN", "Senegal", "221"),
    ("RS", "Serbia", "381"),
    ("SC", "Seychelles", "248"),
    ("SL", "Sierra Leone", "232"),
    ("SG", "Singapore", "65"),
    ("SX", "Sint Maarten", "1721"),
    ("SK", "Slovakia", "421"),
    ("SI", "Slovenia", "386"),
    ("SB", "Solomon Islands", "677"),
    ("SO", "Somalia", "252"),
    ("ZA", "South Africa", "27"),
    ("KR", "South Korea", "82"),
    ("SS", "South Sudan", "211"),
    ("ES", "Spain", "34"),
    ("LK", "Sri Lanka", "94"),
    ("SD", "Sudan", "249"),
    ("SR", "Suriname", "597"),
    ("SJ", "Svalbard and Jan Mayen", "47"),
    ("SE", "Sweden", "46"),
    ("CH", "Switzerland", "41"),
    ("SY", "Syria", "963"),
    ("TW", "Taiwan", "886"),
    ("TJ", "Tajikistan", "992"),
    ("TZ", "Tanzania", "255"),
    ("TH", "Thailand", "66"),
    ("TL", "Timor-Leste", "670"),
    ("TG", "Togo", "228"),
    ("TK", "Tokelau", "690"),
    ("TO", "Tonga", "676"),
    ("TT", "Trinidad and Tobago", "1868"),
    ("TN", "Tunisia", "216"),
    ("TR", "Türkiye", "90"),
    ("TM", "Turkmenistan", "993"),
    ("TC", "Turks and Caicos Islands", "1649"),
    ("TV", "Tuvalu", "688"),
    ("VI", "U.S. Virgin Islands", "1340"),
    ("UG", "Uganda", "256"),
    ("UA", "Ukraine", "380"),
    ("AE", "United Arab Emirates", "971"),
    ("GB", "United Kingdom", "44"),
    ("US", "United States", "1"),
    ("UY", "Uruguay", "598"),
    ("UZ", "Uzbekistan", "998"),
    ("VU", "Vanuatu", "678"),
    ("VA", "Vatican City", "39"),
    ("VE", "Venezuela", "58"),
    ("VN", "Vietnam", "84"),
    ("WF", "Wallis and Futuna", "681"),
    ("EH", "Western Sahara", "212"),
    ("YE", "Yemen", "967"),
    ("ZM", "Zambia", "260"),
    ("ZW", "Zimbabwe", "263"),
]

# Which country a shared dialling code means when nothing more specific matches.
PRIMARY_FOR_DIAL = {
    "1": "US", "7": "RU", "44": "GB", "39": "IT", "47": "NO", "61": "AU",
    "212": "MA", "262": "RE", "358": "FI", "590": "GP", "599": "CW",
}

# Longer number prefixes that pin a shared code to one place (detection only).
EXTRA_PREFIXES = {
    "KZ": ["76", "77"],
    "DO": ["1829", "1849"],
    "JM": ["1658"],
    "PR": ["1939"],
    "GG": ["441481"],
    "JE": ["441534"],
    "IM": ["441624"],
    "BQ": ["5993", "5994", "5997"],
    "VA": ["3906698"],
    "SJ": ["4779"],
    "AX": ["35818"],
    "CA": [f"1{a}" for a in (
        "204 226 236 249 250 263 289 306 343 354 365 367 368 382 403 416 418 428 431 437 438 450 "
        "468 474 506 514 519 548 579 581 584 587 604 613 639 647 672 683 705 709 742 753 778 780 "
        "782 807 819 825 867 873 879 902 905"
    ).split()],
}

# Extra words people search the picker with (frontend only).
ALIASES = {
    "US": "USA America United States of America", "GB": "UK Britain England Scotland Wales Great Britain",
    "AE": "UAE Emirates Dubai Abu Dhabi", "KR": "Korea", "KP": "Korea DPRK", "CZ": "Czech Republic",
    "CI": "Ivory Coast Cote d'Ivoire", "MM": "Burma", "NL": "Holland", "TR": "Turkey Turkiye",
    "CD": "Democratic Republic of the Congo DR Congo Kinshasa", "CG": "Republic of the Congo Brazzaville",
    "SZ": "Swaziland", "MK": "Macedonia", "TL": "East Timor", "CV": "Cabo Verde", "VA": "Holy See",
    "RU": "Russian Federation", "IR": "Persia", "SA": "KSA", "PS": "Palestinian Territories",
    "AX": "Aland", "CW": "Curacao", "RE": "Reunion", "ST": "Sao Tome", "BL": "St Barts",
    "KN": "St Kitts", "LC": "St Lucia", "VC": "St Vincent", "MF": "St Martin", "PM": "St Pierre",
    "SH": "St Helena", "IN": "Bharat Hindustan", "LK": "Ceylon",
}

_BY_ISO = {iso: (name, dial) for iso, name, dial in COUNTRIES}

# prefix -> iso, built once; longest prefix wins at lookup time.
_PREFIX_TO_ISO: dict[str, str] = {}
for _iso, _name, _dial in COUNTRIES:
    _PREFIX_TO_ISO.setdefault(_dial, _iso)
for _dial, _iso in PRIMARY_FOR_DIAL.items():
    _PREFIX_TO_ISO[_dial] = _iso
for _iso, _prefixes in EXTRA_PREFIXES.items():
    for _p in _prefixes:
        _PREFIX_TO_ISO[_p] = _iso
_MAX_PREFIX = max(len(p) for p in _PREFIX_TO_ISO)


def normalize_iso(value: str | None) -> str | None:
    code = (value or "").strip().upper()
    return code if code in _BY_ISO else None


def country_name(iso: str | None) -> str | None:
    entry = _BY_ISO.get((iso or "").upper())
    return entry[0] if entry else None


def dial_code(iso: str | None) -> str | None:
    entry = _BY_ISO.get((iso or "").upper())
    return entry[1] if entry else None


def _match_prefix(digits: str) -> str | None:
    for n in range(min(_MAX_PREFIX, len(digits)), 0, -1):
        iso = _PREFIX_TO_ISO.get(digits[:n])
        if iso:
            return iso
    return None


def country_from_phone(phone: str | None, strict: bool = True) -> str | None:
    """Country implied by a phone number.

    strict=True only trusts clear cases: an explicit +/00 international prefix, or a bare
    Indian mobile (10 digits starting 6-9, optionally led by 91). A leading 0 is not enough:
    Nigerian local numbers (0813…) look the same.
    strict=False also reads a bare number that starts with a dialling code and is long
    enough to be international (e.g. '2347010968937' -> NG). Weaker; use after other signals.
    """
    raw = (phone or "").strip()
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7:
        return None
    if raw.startswith("+") or raw.startswith("00"):
        if raw.startswith("00"):
            digits = digits[2:]
        return _match_prefix(digits)
    if re.fullmatch(r"(?:91)?[6-9]\d{9}", digits):
        return "IN"
    if strict:
        return None
    if len(digits) >= 11:
        return _match_prefix(digits)
    return None


# ── College name → country ────────────────────────────────────────────────────
# Cities, regions, demonyms and well-known institutions. Checked as whole words,
# case-insensitively; country names themselves are added automatically below.
_COLLEGE_HINTS: dict[str, list[str]] = {
    "IN": [
        "iit", "iits", "nit", "iiit", "iiitm", "iim", "bits", "bits pilani", "vit", "srm", "kiit", "lpu",
        "amity", "manipal", "anna university", "aktu", "vtu", "jntu", "jntuh", "jntuk", "rgpv", "mdu",
        "gtu", "sppu", "mumbai university", "delhi university", "ipu", "ggsipu", "dtu", "nsut",
        "iisc", "iiser", "nift", "aiims", "symbiosis", "christ university", "chandigarh university",
        "thapar", "pes", "pesu", "rvce", "bmsce", "msrit", "sastra", "vellore", "galgotias", "sharda",
        "bennett", "jamia", "aligarh", "amu", "bhu", "banaras", "jadavpur", "osmania", "presidency",
        "nirma", "dypatil", "dy patil", "mit wpu", "vjti", "coep", "cusat", "kluniversity", "kl university",
        "mahavidyalaya", "vidyapeeth", "vidyapith", "vishwavidyalaya", "polytechnic", "aicte",
        "delhi", "new delhi", "mumbai", "bombay", "bangalore", "bengaluru", "chennai", "madras", "kolkata",
        "calcutta", "hyderabad", "pune", "ahmedabad", "jaipur", "lucknow", "kanpur", "noida",
        "greater noida", "gurgaon", "gurugram", "ghaziabad", "indore", "bhopal", "nagpur", "patna",
        "surat", "vadodara", "coimbatore", "madurai", "trichy", "tiruchirappalli", "kochi", "cochin",
        "thiruvananthapuram", "trivandrum", "visakhapatnam", "vizag", "vijayawada", "guntur", "warangal",
        "mysore", "mysuru", "mangalore", "dehradun", "roorkee", "kharagpur", "guwahati", "bhubaneswar",
        "ranchi", "raipur", "jodhpur", "udaipur", "kota", "agra", "meerut", "varanasi", "prayagraj",
        "allahabad", "amritsar", "ludhiana", "jalandhar", "mohali", "chandigarh", "srinagar", "jammu",
        "shimla", "nashik", "aurangabad", "kolhapur", "solapur", "rajkot", "gwalior", "jabalpur",
        "uttar pradesh", "maharashtra", "karnataka", "tamil nadu", "tamilnadu", "kerala", "telangana",
        "andhra", "andhra pradesh", "gujarat", "rajasthan", "madhya pradesh", "punjab university",
        "haryana", "bihar", "odisha", "orissa", "west bengal", "assam", "jharkhand", "chhattisgarh",
        "uttarakhand", "himachal", "goa", "indian",
    ],
    "PK": ["comsats", "nust", "lums", "fast nuces", "nuces", "uet", "punjab university lahore", "lahore",
           "karachi", "islamabad", "rawalpindi", "peshawar", "quetta", "faisalabad", "multan",
           "hyderabad sindh", "sindh", "khyber", "pakistani"],
    "BD": ["dhaka", "chittagong", "chattogram", "buet", "khulna", "rajshahi", "sylhet", "bangladeshi"],
    "NP": ["kathmandu", "tribhuvan", "pokhara", "lalitpur", "nepali", "nepalese"],
    "LK": ["colombo", "kandy", "moratuwa", "peradeniya", "sri lankan"],
    "NG": ["lagos", "abuja", "ibadan", "osun", "ogun", "oyo", "kano", "kaduna", "enugu", "nsukka",
           "unilag", "unn", "covenant university", "obafemi awolowo", "ife", "benin city", "port harcourt",
           "ilorin", "akure", "futa", "nigerian", "ekiti", "anambra", "abia", "delta state", "rivers state"],
    "KE": ["nairobi", "mombasa", "kenyatta", "jkuat", "egerton", "kisumu", "kenyan", "moi university"],
    "GH": ["accra", "kumasi", "knust", "legon", "ghanaian", "cape coast"],
    "UG": ["kampala", "makerere", "ugandan"],
    "TZ": ["dar es salaam", "dodoma", "tanzanian", "udsm"],
    "RW": ["kigali", "rwandan"],
    "ET": ["addis ababa", "ethiopian", "bahir dar"],
    "EG": ["cairo", "alexandria", "giza", "ain shams", "mansoura", "egyptian", "assiut", "helwan"],
    "MA": ["rabat", "casablanca", "marrakech", "tetouan", "tangier", "fes", "agadir", "ensa", "moroccan",
           "oujda", "kenitra", "meknes"],
    "DZ": ["algiers", "oran", "constantine", "algerian", "usthb"],
    "TN": ["tunis", "sfax", "sousse", "tunisian"],
    "PH": ["quezon", "manila", "cebu", "davao", "makati", "pasig", "filipino", "ateneo", "la salle manila",
           "mindanao", "luzon", "visayas"],
    "ID": ["jakarta", "bandung", "surabaya", "yogyakarta", "indonesian", "universitas"],
    "MY": ["kuala lumpur", "selangor", "penang", "johor", "malaysian", "universiti"],
    "KZ": ["kazakh", "almaty", "astana", "nur-sultan", "al-farabi", "shymkent"],
    "UZ": ["tashkent", "samarkand", "uzbek", "bukhara"],
    "AZ": ["baku", "azerbaijani", "ada university"],
    "AM": ["yerevan", "armenian", "npua"],
    "GE": ["tbilisi", "georgian"],
    "TR": ["istanbul", "ankara", "izmir", "turkish"],
    "SA": ["riyadh", "jeddah", "dammam", "saudi", "kfupm", "king saud", "king abdulaziz", "mecca", "medina"],
    "AE": ["dubai", "abu dhabi", "sharjah", "emirati"],
    "QA": ["doha", "qatari"],
    "IQ": ["baghdad", "basra", "mosul", "erbil", "iraqi", "kurdistan"],
    "YE": ["sanaa", "sana'a", "aden", "yemeni", "taiz"],
    "JO": ["amman", "jordanian", "yarmouk"],
    "SY": ["damascus", "aleppo", "syrian"],
    "IR": ["tehran", "iranian", "isfahan", "shiraz"],
    "AF": ["kabul", "afghan", "herat"],
    "CN": ["beijing", "shanghai", "tsinghua", "peking", "chinese", "wuhan", "shenzhen", "guangzhou"],
    "VN": ["hanoi", "ho chi minh", "vietnamese", "da nang"],
    "US": ["usa", "new mexico", "new jersey", "stanford", "harvard", "california", "texas", "new york", "american",
           "massachusetts", "florida", "illinois", "georgia tech"],
    "GB": ["london", "oxford", "cambridge", "manchester", "birmingham", "edinburgh", "glasgow",
           "british", "england", "scotland", "wales"],
    "CA": ["toronto", "montreal", "vancouver", "waterloo", "ontario", "quebec", "québec", "mcgill", "ubc",
           "british columbia", "alberta", "canadian"],
    "AU": ["new south wales", "sydney", "melbourne", "brisbane", "perth", "adelaide", "australian", "monash", "unsw"],
    "DE": ["berlin", "munich", "hamburg", "german", "tu munich", "rwth", "aachen"],
    "BR": ["são paulo", "sao paulo", "rio de janeiro", "brazilian", "cruzeiro do sul", "unicamp", "usp"],
    "PE": ["lima", "peruvian", "pucp"],
    "XK": ["pristina", "prishtina", "kosovar", "ubt"],
    "SE": ["stockholm", "malmö", "malmo", "gothenburg", "uppsala", "lund", "swedish", "kth"],
    "ES": ["madrid", "barcelona", "valencia", "alicante", "seville", "spanish"],
    "RO": ["bucharest", "romanian", "cluj"],
    "RU": ["moscow", "saint petersburg", "st petersburg", "russian", "novosibirsk"],
    "UA": ["kyiv", "kiev", "kharkiv", "lviv", "odesa", "ukrainian"],
    "ZW": ["harare", "bulawayo", "zimbabwean"],
    "ZA": ["johannesburg", "cape town", "pretoria", "durban", "south african", "wits"],
    "CM": ["yaounde", "yaoundé", "douala", "cameroonian", "buea"],
    "SO": ["mogadishu", "somali", "hargeisa"],
    "SD": ["khartoum", "sudanese"],
    "MN": ["ulaanbaatar", "mongolian"],
    "KH": ["phnom penh", "cambodian"],
    "MR": ["nouakchott", "mauritanian"],
}

# Country names that are also common US/UK place names; only their hint words count.
_AMBIGUOUS = {"georgia", "jersey"}


def _build_college_patterns() -> list[tuple[re.Pattern, str, int]]:
    pairs: list[tuple[str, str]] = []
    for iso, name, _ in COUNTRIES:
        if name.lower() not in _AMBIGUOUS:
            pairs.append((name.lower(), iso))
    for iso, words in _COLLEGE_HINTS.items():
        pairs.extend((w.lower(), iso) for w in words)
    # Longer phrases first, so 'hyderabad sindh' beats 'hyderabad' and 'south africa' beats 'africa'.
    pairs.sort(key=lambda p: -len(p[0]))
    return [(re.compile(r"(?<![\w])" + re.escape(w) + r"(?![\w])", re.IGNORECASE), iso, len(w)) for w, iso in pairs]


_COLLEGE_PATTERNS = _build_college_patterns()


def country_from_college(college: str | None) -> str | None:
    """Country named or strongly implied by a college name, or None if unclear/conflicting."""
    text = (college or "").strip()
    if len(text) < 2:
        return None
    hits: dict[str, int] = {}
    consumed: list[tuple[int, int]] = []
    for pattern, iso, _ in _COLLEGE_PATTERNS:
        for m in pattern.finditer(text):
            span = m.span()
            if any(s < span[1] and span[0] < e for s, e in consumed):
                continue  # already covered by a longer phrase
            consumed.append(span)
            hits[iso] = hits.get(iso, 0) + 1
    if not hits:
        return None
    ranked = sorted(hits.items(), key=lambda kv: -kv[1])
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return None  # e.g. 'London School of ... Delhi': can't tell
    return ranked[0][0]


def infer_country(phone: str | None, college: str | None) -> tuple[str | None, str | None]:
    """Best guess for an existing applicant: (iso2, source).

    Order: a clear phone code, then the college name, then a looser read of the phone digits.
    The college outranks the loose phone read because a bare number like '94100097704'
    (an Indian mobile with a typo) would otherwise read as Sri Lanka.
    """
    iso = country_from_phone(phone, strict=True)
    if iso:
        return iso, "phone"
    iso = country_from_college(college)
    if iso:
        return iso, "college"
    iso = country_from_phone(phone, strict=False)
    if iso:
        return iso, "phone"
    return None, None
