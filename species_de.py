"""Deutsche Namen fuer haeufige Garten- und Futterhausvoegel.

Schluessel: lateinischer Name, wie er in der Labeldatei des Artmodells
(iNaturalist-Vogelmodell von Google Coral) steht. Arten, die hier fehlen,
werden mit dem englischen Namen aus der Labeldatei angezeigt.
"""

GERMAN_NAMES = {
    'Parus major': 'Kohlmeise',
    'Cyanistes caeruleus': 'Blaumeise',
    'Periparus ater': 'Tannenmeise',
    'Lophophanes cristatus': 'Haubenmeise',
    'Poecile montanus': 'Weidenmeise',
    'Aegithalos caudatus': 'Schwanzmeise',
    'Erithacus rubecula': 'Rotkehlchen',
    'Turdus merula': 'Amsel',
    'Turdus philomelos': 'Singdrossel',
    'Turdus pilaris': 'Wacholderdrossel',
    'Passer domesticus': 'Haussperling',
    'Passer montanus': 'Feldsperling',
    'Fringilla coelebs': 'Buchfink',
    'Fringilla montifringilla': 'Bergfink',
    'Chloris chloris': 'Grünfink',
    'Carduelis carduelis': 'Stieglitz',
    'Spinus spinus': 'Erlenzeisig',
    'Pyrrhula pyrrhula': 'Gimpel',
    'Coccothraustes coccothraustes': 'Kernbeißer',
    'Emberiza citrinella': 'Goldammer',
    'Sitta europaea': 'Kleiber',
    'Certhia brachydactyla': 'Gartenbaumläufer',
    'Troglodytes troglodytes': 'Zaunkönig',
    'Prunella modularis': 'Heckenbraunelle',
    'Phoenicurus ochruros': 'Hausrotschwanz',
    'Phoenicurus phoenicurus': 'Gartenrotschwanz',
    'Sturnus vulgaris': 'Star',
    'Dendrocopos major': 'Buntspecht',
    'Dryobates minor': 'Kleinspecht',
    'Picus viridis': 'Grünspecht',
    'Garrulus glandarius': 'Eichelhäher',
    'Pica pica': 'Elster',
    'Corvus monedula': 'Dohle',
    'Corvus corone': 'Rabenkrähe',
    'Columba palumbus': 'Ringeltaube',
    'Streptopelia decaocto': 'Türkentaube',
    'Sylvia atricapilla': 'Mönchsgrasmücke',
    'Motacilla alba': 'Bachstelze',
    'Regulus regulus': 'Wintergoldhähnchen',
}

# Englische Namen (fuer language = "en"); gleiche Schluessel wie GERMAN_NAMES.
ENGLISH_NAMES = {
    'Parus major': 'Great Tit',
    'Cyanistes caeruleus': 'Eurasian Blue Tit',
    'Periparus ater': 'Coal Tit',
    'Lophophanes cristatus': 'Crested Tit',
    'Poecile montanus': 'Willow Tit',
    'Aegithalos caudatus': 'Long-tailed Tit',
    'Erithacus rubecula': 'European Robin',
    'Turdus merula': 'Common Blackbird',
    'Turdus philomelos': 'Song Thrush',
    'Turdus pilaris': 'Fieldfare',
    'Passer domesticus': 'House Sparrow',
    'Passer montanus': 'Eurasian Tree Sparrow',
    'Fringilla coelebs': 'Common Chaffinch',
    'Fringilla montifringilla': 'Brambling',
    'Chloris chloris': 'European Greenfinch',
    'Carduelis carduelis': 'European Goldfinch',
    'Spinus spinus': 'Eurasian Siskin',
    'Pyrrhula pyrrhula': 'Eurasian Bullfinch',
    'Coccothraustes coccothraustes': 'Hawfinch',
    'Emberiza citrinella': 'Yellowhammer',
    'Sitta europaea': 'Eurasian Nuthatch',
    'Certhia brachydactyla': 'Short-toed Treecreeper',
    'Troglodytes troglodytes': 'Eurasian Wren',
    'Prunella modularis': 'Dunnock',
    'Phoenicurus ochruros': 'Black Redstart',
    'Phoenicurus phoenicurus': 'Common Redstart',
    'Sturnus vulgaris': 'Common Starling',
    'Dendrocopos major': 'Great Spotted Woodpecker',
    'Dryobates minor': 'Lesser Spotted Woodpecker',
    'Picus viridis': 'European Green Woodpecker',
    'Garrulus glandarius': 'Eurasian Jay',
    'Pica pica': 'Eurasian Magpie',
    'Corvus monedula': 'Western Jackdaw',
    'Corvus corone': 'Carrion Crow',
    'Columba palumbus': 'Common Wood Pigeon',
    'Streptopelia decaocto': 'Eurasian Collared Dove',
    'Sylvia atricapilla': 'Eurasian Blackcap',
    'Motacilla alba': 'White Wagtail',
    'Regulus regulus': 'Goldcrest',
}

NAMES = {'de': GERMAN_NAMES, 'en': ENGLISH_NAMES}


def bird_name(latin, lang='de', fallback=None):
    """Vogelname in der gewaehlten Sprache ('de' oder 'en'). Unbekannte Arten:
    fallback (z. B. englischer Name aus der Labeldatei), sonst der lateinische Name."""
    if latin == 'unbekannt':
        return 'unbekannt' if lang == 'de' else 'unknown'
    return NAMES.get(lang, GERMAN_NAMES).get(latin) or fallback or latin
